from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Literal, cast
from urllib.parse import parse_qsl, unquote, urlsplit

from .direct import (
    DirectExecutableAdapter,
    _direct_payload_type,
    _has_direct_payload_evidence,
)
from .filesystem import FilesystemProbe, FilesystemProbeResult
from .models import (
    MAX_METADATA_CANDIDATES,
    RequestValidationError,
    ResolutionRequest,
    ResolutionResult,
)


HEROIC_FLATPAK_APP_ID = "com.heroicgameslauncher.hgl"
_SUPPORTED_RUNNERS = frozenset({"legendary", "gog", "nile", "sideload"})
_UNSAFE_PATH_CHARACTERS = frozenset("$`?*[]{}|&;<>")
_MAX_HEROIC_IDENTIFIER_LENGTH = 256
_MAX_METADATA_BYTES = 256 * 1024
_MAX_METADATA_JSON_DEPTH = 32
_MAX_METADATA_JSON_NODES = 4096
_MAX_METADATA_RECORDS = 128
_MAX_METADATA_FIELD_LENGTH = 4096
_METADATA_PATHS = {
    "legendary": Path("legendaryConfig") / "legendary" / "installed.json",
    "gog": Path("gog_store") / "installed.json",
    "nile": Path("nile_store") / "installed.json",
    "sideload": Path("sideload_apps") / "library.json",
}


def _read_text(path: Path) -> str:
    with path.open("rb") as metadata_file:
        contents = metadata_file.read(_MAX_METADATA_BYTES + 1)
    if len(contents) > _MAX_METADATA_BYTES:
        raise ValueError("Heroic metadata exceeds the byte limit")
    return contents.decode("utf-8")


def _duplicate_aware_json_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result and result[key] != value:
            raise ValueError("Heroic metadata contains conflicting duplicate keys")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class HeroicConfigRoots:
    """Known Heroic configuration roots; callers may inject these for tests."""

    native: Path | None
    flatpak: Path | None

    @classmethod
    def discover(cls) -> "HeroicConfigRoots":
        home = Path.home()
        configured = os.environ.get("XDG_CONFIG_HOME")
        native_base = Path(configured) if configured else home / ".config"
        native = native_base / "heroic" if native_base.is_absolute() else None
        return cls(
            native=native,
            flatpak=home / ".var" / "app" / HEROIC_FLATPAK_APP_ID / "config" / "heroic",
        )

    def paths(
        self, source: Literal["native", "flatpak"] | None = None
    ) -> tuple[Path, ...]:
        roots = (
            (self.native, self.flatpak)
            if source is None
            else (self.native,)
            if source == "native"
            else (self.flatpak,)
        )
        paths: list[Path] = []
        for root in roots:
            if root is None or not root.is_absolute() or root in paths:
                continue
            paths.append(root)
        return tuple(paths)


@dataclass(frozen=True, slots=True)
class _HeroicIdentity:
    app_id: str
    runner: str | None
    alternate_executable: Path | None
    source: Literal["native", "flatpak"] = "native"


@dataclass(frozen=True, slots=True)
class _MetadataCandidate:
    runner: str
    payload_path: Path
    install_path: Path | None
    source_root: Path
    sideload: bool


@dataclass(frozen=True, slots=True)
class _MetadataLookup:
    candidates: tuple[_MetadataCandidate, ...]


class HeroicAdapter:
    launcher_kind = "heroic"

    def __init__(
        self,
        probe: FilesystemProbe,
        *,
        config_roots: HeroicConfigRoots | None = None,
        read_text: Callable[[Path], str] = _read_text,
    ) -> None:
        self._probe = probe
        self._config_roots = config_roots or HeroicConfigRoots.discover()
        self._read_text = read_text

    def resolve(self, request: ResolutionRequest) -> ResolutionResult:
        if request.classification_status == "ambiguous":
            return self._unknown(request, "ambiguous")
        if request.classification_status != "recognized":
            return self._unknown(request, "missing")
        try:
            identity = self._validated_identity(request)
        except RequestValidationError as error:
            return self._unknown(request, error.reason_code)

        try:
            lookup = self._lookup_metadata(identity)
        except RequestValidationError as error:
            return self._unknown(
                request,
                error.reason_code,
                metadata_status="invalid",
            )

        if not lookup.candidates:
            return self._unknown(
                request,
                "missing",
                metadata_status="not_found",
            )
        if len(lookup.candidates) != 1:
            return self._unknown(
                request,
                "ambiguous",
                metadata_status="resolved",
            )
        return self._probe_payload(request, lookup.candidates[0])

    @staticmethod
    def _unknown(
        request: ResolutionRequest,
        reason_code: Literal[
            "missing",
            "ambiguous",
            "unsupported",
            "permission_denied",
            "malformed",
            "drive_disconnected",
            "payload_missing",
            "kind_mismatch",
            "probe_failure",
            "timeout",
        ],
        *,
        metadata_status: Literal[
            "not_requested", "not_found", "resolved", "invalid"
        ] = "not_requested",
    ) -> ResolutionResult:
        return ResolutionResult(
            launcher_kind=request.launcher_kind,
            classification_status=request.classification_status,
            metadata_status=metadata_status,
            payload_status="unknown",
            payload_kind="unknown",
            provenance="untrusted_hint",
            reason_code=reason_code,
            payload_path=None,
        )

    def _validated_identity(self, request: ResolutionRequest) -> _HeroicIdentity:
        normalized = request.normalized
        if request.metadata_candidates:
            raise RequestValidationError("malformed")
        if normalized.command_tokens != (
            normalized.executable_tokens + normalized.launch_option_tokens
        ):
            raise RequestValidationError("malformed")
        executable = _single_literal_absolute_path(normalized.shortcut_exe)
        if normalized.executable_tokens != (str(executable),):
            raise RequestValidationError("malformed")
        if normalized.shortcut_start_dir is None:
            if normalized.start_dir_tokens:
                raise RequestValidationError("malformed")
        else:
            start_directory = _single_literal_absolute_path(
                normalized.shortcut_start_dir
            )
            if normalized.start_dir_tokens != (str(start_directory),):
                raise RequestValidationError("malformed")

        is_flatpak = (
            executable.name.casefold() == "flatpak"
            and normalized.flatpak_app_id is not None
            and normalized.flatpak_app_id.casefold() == HEROIC_FLATPAK_APP_ID
        )
        if is_flatpak:
            launch_options = normalized.launch_option_tokens
            if len(launch_options) == 4 and launch_options[2] == "--":
                uri = launch_options[3]
            elif len(launch_options) == 3:
                uri = launch_options[2]
            else:
                raise RequestValidationError("malformed")
            if (
                launch_options[0] != "run"
                or launch_options[1].casefold() != HEROIC_FLATPAK_APP_ID
            ):
                raise RequestValidationError("malformed")
            return replace(_parse_heroic_uri(uri), source="flatpak")

        if normalized.flatpak_app_id is not None or not _is_heroic_executable(
            executable
        ):
            raise RequestValidationError("malformed")
        if len(normalized.launch_option_tokens) != 1:
            raise RequestValidationError("malformed")
        return _parse_heroic_uri(normalized.launch_option_tokens[0])

    def _lookup_metadata(self, identity: _HeroicIdentity) -> _MetadataLookup:
        candidates: list[_MetadataCandidate] = []
        runners = (identity.runner,) if identity.runner else tuple(_SUPPORTED_RUNNERS)
        for root in self._config_roots.paths(identity.source):
            for runner in runners:
                assert runner is not None
                data, _ = self._read_metadata_file(root / _METADATA_PATHS[runner])
                if data is None:
                    continue
                records = self._candidates_from_data(root, runner, identity, data)
                candidates.extend(records)
                candidates = list(_deduplicate_candidates(candidates))
                if len(candidates) > MAX_METADATA_CANDIDATES:
                    raise RequestValidationError("malformed")
        return _MetadataLookup(tuple(candidates))

    def _read_metadata_file(self, path: Path) -> tuple[object | None, bool]:
        try:
            contents = self._read_text(path)
        except FileNotFoundError:
            return None, False
        except PermissionError as error:
            raise RequestValidationError("permission_denied") from error
        except OSError as error:
            raise RequestValidationError("probe_failure") from error
        except (TypeError, UnicodeError, ValueError) as error:
            raise RequestValidationError("malformed") from error
        if not isinstance(contents, str):
            raise RequestValidationError("malformed")
        try:
            if len(contents.encode("utf-8")) > _MAX_METADATA_BYTES:
                raise ValueError("Heroic metadata exceeds the byte limit")
            data = json.loads(contents, object_pairs_hook=_duplicate_aware_json_object)
            _validate_metadata_shape(data)
        except (TypeError, UnicodeError, ValueError, RecursionError) as error:
            raise RequestValidationError("malformed") from error
        return data, True

    def _candidates_from_data(
        self,
        root: Path,
        runner: str,
        identity: _HeroicIdentity,
        data: object,
    ) -> tuple[_MetadataCandidate, ...]:
        records = _matching_records(data, identity.app_id, runner)
        candidates: list[_MetadataCandidate] = []
        for record in records:
            if runner == "sideload":
                payload = _sideload_payload(record)
                candidates.append(_MetadataCandidate(runner, payload, None, root, True))
                continue
            install_path, executable = _installed_payload(record)
            payload = install_path / executable
            settings = self._read_settings(root, identity.app_id)
            selected = _select_payload(
                payload,
                install_path,
                settings,
                alternate_executable=identity.alternate_executable,
            )
            candidates.append(
                _MetadataCandidate(runner, selected, install_path, root, False)
            )
        return tuple(candidates)

    def _read_settings(self, root: Path, app_id: str) -> Path | None:
        data, exists = self._read_metadata_file(root / "GamesConfig" / f"{app_id}.json")
        if not exists:
            return None
        if not isinstance(data, Mapping):
            raise RequestValidationError("malformed")
        settings = data.get(app_id)
        if settings is None:
            return None
        if not isinstance(settings, Mapping):
            raise RequestValidationError("malformed")
        target = settings.get("targetExe")
        if target is None:
            return None
        return _absolute_payload_path(target)

    def _probe_payload(
        self,
        request: ResolutionRequest,
        candidate: _MetadataCandidate,
    ) -> ResolutionResult:
        try:
            probe_result = self._probe.probe_regular_file(candidate.payload_path)
        except Exception:
            return self._unknown(request, "probe_failure", metadata_status="resolved")
        if probe_result.reason_code is not None:
            return self._result_from_probe_failure(request, probe_result)
        assert probe_result.payload_path is not None
        if DirectExecutableAdapter._is_rejected_path(probe_result.payload_path):
            return self._unknown(request, "unsupported", metadata_status="resolved")
        if not candidate.sideload:
            payload_type = _direct_payload_type(probe_result.payload_path)
            if payload_type is None or not _has_direct_payload_evidence(
                payload_type,
                probe_result.file_mode,
                probe_result.file_header,
            ):
                return self._unknown(request, "unsupported", metadata_status="resolved")
        return ResolutionResult(
            launcher_kind=request.launcher_kind,
            classification_status=request.classification_status,
            metadata_status="resolved",
            payload_status="reachable",
            payload_kind="file",
            provenance="heroic_metadata",
            reason_code=None,
            payload_path=probe_result.payload_path,
        )

    def _result_from_probe_failure(
        self,
        request: ResolutionRequest,
        probe_result: FilesystemProbeResult,
    ) -> ResolutionResult:
        assert probe_result.reason_code is not None
        if probe_result.reason_code in {
            "drive_disconnected",
            "kind_mismatch",
            "payload_missing",
        }:
            return ResolutionResult(
                launcher_kind=request.launcher_kind,
                classification_status=request.classification_status,
                metadata_status="resolved",
                payload_status="unreachable",
                payload_kind="unknown",
                provenance="heroic_metadata",
                reason_code=probe_result.reason_code,
                payload_path=None,
            )
        return self._unknown(
            request,
            probe_result.reason_code,
            metadata_status="resolved",
        )


def _matching_records(
    data: object, app_id: str, runner: str
) -> tuple[Mapping[str, object], ...]:
    if not isinstance(data, Mapping):
        raise RequestValidationError("malformed")
    if runner == "legendary":
        if len(data) > _MAX_METADATA_RECORDS:
            raise RequestValidationError("malformed")
        record = data.get(app_id)
        if record is not None:
            return (_mapping_record(record, app_id, runner, mapping_key=app_id),)
        for mapping_key, value in data.items():
            if not isinstance(value, Mapping):
                continue
            candidate = cast(Mapping[str, object], value)
            if app_id not in _record_identifiers(candidate):
                continue
            _validate_record_identity(candidate, app_id, runner)
            if mapping_key != app_id:
                raise RequestValidationError("ambiguous")
        return ()

    collection_name = "games" if runner == "sideload" else "installed"
    collection = data.get(collection_name)
    if collection is None:
        return ()
    if not isinstance(collection, Sequence) or isinstance(collection, (str, bytes)):
        raise RequestValidationError("malformed")
    if len(collection) > _MAX_METADATA_RECORDS:
        raise RequestValidationError("malformed")
    records: list[Mapping[str, object]] = []
    for item in collection:
        record = _mapping_record(item, app_id, runner)
        if app_id not in _record_identifiers(record):
            continue
        _validate_record_identity(record, app_id, runner)
        records.append(record)
    return tuple(records)


def _mapping_record(
    value: object,
    app_id: str,
    runner: str,
    *,
    mapping_key: str | None = None,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RequestValidationError("malformed")
    record = cast(Mapping[str, object], value)
    if mapping_key is not None and mapping_key != app_id:
        raise RequestValidationError("ambiguous")
    if mapping_key is not None:
        _validate_record_identity(record, app_id, runner)
    return record


def _record_identifiers(record: Mapping[str, object]) -> tuple[str, ...]:
    values: list[str] = []
    for field_name in ("app_name", "appName", "app_id", "appId", "appID"):
        if field_name not in record:
            continue
        value = record[field_name]
        if not isinstance(value, str):
            raise RequestValidationError("malformed")
        values.append(value)
    return tuple(values)


def _validate_record_identity(
    record: Mapping[str, object], app_id: str, runner: str
) -> None:
    identifiers = _record_identifiers(record)
    if any(value != app_id for value in identifiers):
        raise RequestValidationError("ambiguous")
    for field_name in ("runner", "source"):
        if field_name not in record:
            continue
        value = record[field_name]
        if not isinstance(value, str):
            raise RequestValidationError("malformed")
        if value != runner:
            raise RequestValidationError("ambiguous")


def _deduplicate_candidates(
    candidates: Sequence[_MetadataCandidate],
) -> tuple[_MetadataCandidate, ...]:
    unique: list[_MetadataCandidate] = []
    seen: set[tuple[str, Path, Path | None, bool]] = set()
    for candidate in candidates:
        key = (
            candidate.runner,
            candidate.payload_path,
            candidate.install_path,
            candidate.sideload,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return tuple(unique)


def _validate_metadata_shape(data: object) -> None:
    pending: list[tuple[object, int]] = [(data, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_METADATA_JSON_NODES or depth > _MAX_METADATA_JSON_DEPTH:
            raise ValueError("Heroic metadata exceeds structural limits")
        if isinstance(value, Mapping):
            for key, child in value.items():
                if not isinstance(key, str) or len(key) > _MAX_METADATA_FIELD_LENGTH:
                    raise ValueError("Heroic metadata has an invalid field name")
                pending.append((child, depth + 1))
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            pending.extend((child, depth + 1) for child in value)
        elif isinstance(value, str):
            if len(value) > _MAX_METADATA_FIELD_LENGTH:
                raise ValueError("Heroic metadata has an oversized field")
        elif value is not None and not isinstance(value, (bool, int, float)):
            raise ValueError("Heroic metadata has an unsupported value")


def _installed_payload(record: Mapping[str, object]) -> tuple[Path, PurePosixPath]:
    install_path = _absolute_payload_path(
        record.get("install_path", record.get("installPath"))
    )
    executable = record.get("executable")
    if not isinstance(executable, str) or not executable:
        raise RequestValidationError("malformed")
    relative = PurePosixPath(executable)
    if (
        relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or "\\" in executable
        or len(executable) > 4096
    ):
        raise RequestValidationError("malformed")
    return install_path, relative


def _sideload_payload(record: Mapping[str, object]) -> Path:
    install = record.get("install")
    if not isinstance(install, Mapping):
        raise RequestValidationError("malformed")
    return _absolute_payload_path(install.get("executable"))


def _select_payload(
    default_payload: Path,
    install_path: Path,
    stored_alternate: Path | None,
    alternate_executable: Path | None,
) -> Path:
    selected = alternate_executable or stored_alternate or default_payload
    try:
        selected.relative_to(install_path)
    except ValueError as error:
        raise RequestValidationError("ambiguous") from error
    return selected


def _single_literal_absolute_path(value: str | None) -> Path:
    if value is None:
        raise RequestValidationError("malformed")
    candidate = value
    if candidate.startswith(("'", '"')):
        quote_character = candidate[0]
        if len(candidate) < 2 or not candidate.endswith(quote_character):
            raise RequestValidationError("malformed")
        candidate = candidate[1:-1]
        if quote_character in candidate:
            raise RequestValidationError("malformed")
    elif any(character.isspace() for character in candidate):
        raise RequestValidationError("malformed")
    return _absolute_payload_path(candidate)


def _absolute_payload_path(value: object) -> Path:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise RequestValidationError("malformed")
    if "\x00" in value or any(
        character in _UNSAFE_PATH_CHARACTERS for character in value
    ):
        raise RequestValidationError("malformed")
    path = PurePosixPath(value)
    if not path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RequestValidationError("malformed")
    return Path(path)


def _is_heroic_executable(path: Path) -> bool:
    stem = re.sub(r"\.(?:appimage|exe|x86|x86_64)$", "", path.name.casefold())
    return stem == "heroic" or (
        stem.startswith("heroic") and stem[6:7] in {"-", "_", "."}
    )


def _parse_heroic_uri(value: str) -> _HeroicIdentity:
    if not value.startswith("heroic://"):
        raise RequestValidationError("malformed")
    try:
        parsed = urlsplit(value)
    except ValueError as error:
        raise RequestValidationError("malformed") from error
    if (
        parsed.scheme.casefold() != "heroic"
        or parsed.netloc.casefold() != "launch"
        or parsed.fragment
    ):
        raise RequestValidationError("malformed")

    path_segments = [segment for segment in parsed.path.split("/") if segment]
    if path_segments:
        if len(path_segments) not in {1, 2}:
            raise RequestValidationError("malformed")
        app_id = _heroic_identifier(_decode_percent_once(path_segments[-1]))
        runner = (
            _heroic_runner(_decode_percent_once(path_segments[0]))
            if len(path_segments) == 2
            else None
        )
        return _HeroicIdentity(app_id, runner, None)

    if not parsed.query:
        raise RequestValidationError("malformed")
    if re.search(r"%(?![0-9a-fA-F]{2})", parsed.query):
        raise RequestValidationError("malformed")
    values = parse_qsl(parsed.query, keep_blank_values=True)
    app_id = _unique_query_value(values, {"appName", "appId", "appID"})
    runner = _unique_query_value(values, {"runner"})
    alternate = _unique_query_value(values, {"altExe"})
    return _HeroicIdentity(
        _heroic_identifier(app_id),
        _heroic_runner(runner) if runner else None,
        _absolute_payload_path(_decode_percent_once(alternate)) if alternate else None,
    )


def _unique_query_value(
    values: Sequence[tuple[str, str]], names: set[str]
) -> str | None:
    selected = {value for name, value in values if name in names and value}
    if len(selected) > 1:
        raise RequestValidationError("ambiguous")
    return next(iter(selected), None)


def _decode_percent_once(value: str) -> str:
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        raise RequestValidationError("malformed")
    return unquote(value)


def _heroic_identifier(value: str | None) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > _MAX_HEROIC_IDENTIFIER_LENGTH
        or "\x00" in value
        or "/" in value
        or "\\" in value
        or value in {".", ".."}
    ):
        raise RequestValidationError("malformed")
    return value


def _heroic_runner(value: str) -> str:
    if value not in _SUPPORTED_RUNNERS:
        raise RequestValidationError("malformed")
    return value
