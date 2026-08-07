from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast
import zlib

from .models import (
    MAX_SHORTCUT_FIELD_LENGTH,
    NormalizedShortcutEvidence,
    ReasonCode,
    ResolutionRequest,
)


_STEAM_ID64_BASE: Final = 76_561_197_960_265_728
_MAX_SHORTCUTS_FILE_BYTES: Final = 8 * 1024 * 1024
_MAX_SHORTCUTS_RECORDS: Final = 4_096
_MAX_VDF_DEPTH: Final = 16
_HEROIC_FLATPAK_APP_ID: Final = "com.heroicgameslauncher.hgl"
_FLATPAK_APP_ID_CHARACTERS: Final = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._+"
)


class ShortcutParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ShortcutCatalogOutcome:
    """The only shortcut evidence a checksum coordinator may use."""

    request: ResolutionRequest | None
    reason_code: ReasonCode | None = None


def shortcut_app_id(executable: str, app_name: str) -> int:
    """Return Steam's unsigned 32-bit shortcut app ID for a VDF record."""
    digest = zlib.crc32(f"{executable}{app_name}".encode("utf-8"))
    return digest | 0x80000000


def _read_cstring(data: bytes, offset: int) -> tuple[str, int]:
    end = data.find(b"\x00", offset, offset + MAX_SHORTCUT_FIELD_LENGTH + 1)
    if end < 0:
        raise ShortcutParseError("unterminated or oversized VDF string")
    try:
        return data[offset:end].decode("utf-8"), end + 1
    except UnicodeDecodeError as error:
        raise ShortcutParseError("invalid VDF string") from error


@dataclass(slots=True)
class _ParseState:
    shortcut_records: int = 0


def _parse_object(
    data: bytes,
    offset: int,
    state: _ParseState,
    depth: int = 0,
    *,
    counts_shortcut_records: bool = False,
) -> tuple[dict[str, object], int]:
    if depth > _MAX_VDF_DEPTH:
        raise ShortcutParseError("nested VDF object is too deep")

    result: dict[str, object] = {}
    while True:
        if offset >= len(data):
            raise ShortcutParseError("unterminated VDF object")
        value_type = data[offset]
        offset += 1
        if value_type == 8:
            return result, offset

        key, offset = _read_cstring(data, offset)
        normalized_key = key.casefold()
        if value_type == 0 and counts_shortcut_records:
            state.shortcut_records += 1
            if state.shortcut_records > _MAX_SHORTCUTS_RECORDS:
                raise ShortcutParseError("shortcuts VDF has too many records")
        if normalized_key in result:
            raise ShortcutParseError("duplicate VDF key")
        if value_type == 0:
            value, offset = _parse_object(
                data,
                offset,
                state,
                depth + 1,
                counts_shortcut_records=(depth == 0 and normalized_key == "shortcuts"),
            )
        elif value_type == 1:
            value, offset = _read_cstring(data, offset)
        elif value_type == 2:
            if offset + 4 > len(data):
                raise ShortcutParseError("truncated VDF integer")
            value = int.from_bytes(data[offset : offset + 4], "little", signed=True)
            offset += 4
        else:
            raise ShortcutParseError("unsupported VDF field type")
        result[normalized_key] = value


def _parse_shortcuts(data: bytes) -> tuple[Mapping[str, object], ...]:
    if len(data) > _MAX_SHORTCUTS_FILE_BYTES:
        raise ShortcutParseError("shortcuts VDF exceeds the size limit")
    root, offset = _parse_object(data, 0, _ParseState())
    if offset != len(data):
        raise ShortcutParseError("trailing data in shortcuts VDF")
    shortcuts = root.get("shortcuts")
    if not isinstance(shortcuts, Mapping):
        raise ShortcutParseError("invalid shortcuts VDF root")
    if not all(isinstance(entry, Mapping) for entry in shortcuts.values()):
        raise ShortcutParseError("invalid shortcuts VDF record")
    return tuple(cast(Mapping[str, object], entry) for entry in shortcuts.values())


def _read_shortcuts_bytes(path: Path) -> bytes:
    with path.open("rb") as source:
        data = source.read(_MAX_SHORTCUTS_FILE_BYTES + 1)
    if len(data) > _MAX_SHORTCUTS_FILE_BYTES:
        raise ShortcutParseError("shortcuts VDF exceeds the size limit")
    return data


def _normalized_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > MAX_SHORTCUT_FIELD_LENGTH
        or "\x00" in normalized
    ):
        return None
    return normalized


def _parse_tokens(value: str | None) -> tuple[str, ...] | None:
    if value is None:
        return ()

    tokens: list[str] = []
    token = ""
    quote: str | None = None
    index = 0
    while index < len(value):
        character = value[index]
        if character == "\\":
            next_character = value[index + 1] if index + 1 < len(value) else None
            if next_character in {"\\", '"', "'", " ", "\t"}:
                token += next_character
                index += 2
                continue
            token += character
            index += 1
            continue
        if quote is not None:
            if character == quote:
                quote = None
            else:
                token += character
            index += 1
            continue
        if character in {'"', "'"}:
            quote = character
            index += 1
            continue
        if character.isspace():
            if token:
                tokens.append(token)
                token = ""
            index += 1
            continue
        token += character
        index += 1

    if quote is not None:
        return None
    if token:
        tokens.append(token)
    if any(len(item) > MAX_SHORTCUT_FIELD_LENGTH or "\x00" in item for item in tokens):
        return None
    return tuple(tokens)


def _heroic_stem(value: str) -> bool:
    name = Path(value).name.casefold()
    for suffix in (".appimage", ".exe", ".x86", ".x86_64"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name == "heroic" or (
        name.startswith("heroic")
        and name[len("heroic") : len("heroic") + 1] in {"-", "_", "."}
    )


def _is_heroic_shortcut(
    normalized: NormalizedShortcutEvidence,
) -> bool:
    executable = normalized.executable_tokens
    options = normalized.launch_option_tokens
    flatpak_app_id = (
        _parse_flatpak_app_id(options)
        if executable and Path(executable[0]).name.casefold() == "flatpak"
        else None
    )
    if len(executable) != 1:
        return False
    is_native = _heroic_stem(executable[0])
    is_flatpak = (
        flatpak_app_id is not None
        and flatpak_app_id.casefold() == _HEROIC_FLATPAK_APP_ID
    )
    return (is_native or is_flatpak) and any(
        option.casefold().startswith("heroic://launch") for option in options
    )


def _flatpak_application_id(value: str | None) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= MAX_SHORTCUT_FIELD_LENGTH
        and all(character in _FLATPAK_APP_ID_CHARACTERS for character in value)
    )


def _parse_flatpak_app_id(tokens: tuple[str, ...]) -> str | None:
    for index, token in enumerate(tokens):
        if token != "run":
            continue
        for candidate in tokens[index + 1 :]:
            if candidate == "--":
                break
            if candidate.startswith("-"):
                continue
            if candidate and "." in candidate and _flatpak_application_id(candidate):
                return candidate
    return None


def _request_from_record(record: Mapping[str, object]) -> ResolutionRequest | None:
    executable = _normalized_text(record.get("exe"))
    if executable is None or _normalized_text(record.get("appname")) is None:
        return None
    launch_options = _normalized_text(record.get("launchoptions"))
    start_dir = _normalized_text(record.get("startdir"))
    flatpak_app_id = _normalized_text(record.get("flatpakappid"))
    executable_tokens = _parse_tokens(executable)
    launch_tokens = _parse_tokens(launch_options)
    start_dir_tokens = _parse_tokens(start_dir)
    if executable_tokens is None or launch_tokens is None or start_dir_tokens is None:
        return None

    normalized = NormalizedShortcutEvidence(
        flatpak_app_id=flatpak_app_id,
        shortcut_exe=executable,
        shortcut_launch_options=launch_options,
        shortcut_start_dir=start_dir,
        executable_tokens=executable_tokens,
        launch_option_tokens=launch_tokens,
        start_dir_tokens=start_dir_tokens,
        command_tokens=executable_tokens + launch_tokens,
    )
    if _is_heroic_shortcut(normalized):
        return ResolutionRequest("heroic", "recognized", normalized, ())
    if (
        flatpak_app_id is None
        and _parse_flatpak_app_id(normalized.launch_option_tokens) is not None
    ):
        return ResolutionRequest("flatpak", "recognized", normalized, ())
    if (
        flatpak_app_id is None
        and len(executable_tokens) == 1
        and not launch_tokens
        and len(start_dir_tokens) <= 1
    ):
        return ResolutionRequest("direct", "recognized", normalized, ())
    return None


def _record_for_app_id(
    record: Mapping[str, object], app_id: int
) -> tuple[tuple[tuple[str, object], ...], ResolutionRequest | None] | None:
    executable = _normalized_text(record.get("exe"))
    app_name = _normalized_text(record.get("appname"))
    stored_app_id = record.get("appid")
    stored_unsigned = (
        stored_app_id & 0xFFFFFFFF if isinstance(stored_app_id, int) else None
    )
    derived_app_id = (
        shortcut_app_id(executable, app_name)
        if executable is not None and app_name is not None
        else None
    )

    if app_id not in {stored_unsigned, derived_app_id}:
        return None
    if (
        executable is None
        or app_name is None
        or stored_unsigned != app_id
        or derived_app_id != app_id
    ):
        raise ShortcutParseError("shortcut record has an inconsistent app ID")

    return _record_evidence(record), _request_from_record(record)


def _record_evidence(record: Mapping[str, object]) -> tuple[tuple[str, object], ...]:
    """Return a stable, complete record identity for cross-catalog deduplication."""

    return tuple(
        sorted((key, _freeze_record_value(value)) for key, value in record.items())
    )


def _freeze_record_value(value: object) -> object:
    if isinstance(value, Mapping):
        return tuple(
            sorted(
                (key, _freeze_record_value(nested_value))
                for key, nested_value in value.items()
            )
        )
    return value


class SteamShortcutCatalog:
    """Build checksum-eligible requests from the active user's Steam VDF only."""

    def __init__(
        self,
        user_home: Path,
        current_user_id: Callable[[], str | None],
        *,
        read_bytes: Callable[[Path], bytes] | None = None,
    ) -> None:
        self._user_home = user_home
        self._current_user_id = current_user_id
        self._read_bytes = read_bytes or _read_shortcuts_bytes

    def get_request(self, app_id: int) -> ShortcutCatalogOutcome:
        seen_sources: set[Path] = set()
        seen_records: set[tuple[tuple[str, object], ...]] = set()
        matches: list[ResolutionRequest | None] = []
        for path in self._candidate_paths():
            source = path.resolve(strict=False)
            if source in seen_sources:
                continue
            seen_sources.add(source)
            try:
                records = _parse_shortcuts(self._read_bytes(path))
            except OSError:
                continue
            except ShortcutParseError:
                return ShortcutCatalogOutcome(None, "malformed")
            for record in records:
                try:
                    candidate = _record_for_app_id(record, app_id)
                except ShortcutParseError:
                    return ShortcutCatalogOutcome(None, "malformed")
                if candidate is None:
                    continue
                evidence, request = candidate
                if evidence not in seen_records:
                    seen_records.add(evidence)
                    matches.append(request)

        if not matches:
            return ShortcutCatalogOutcome(None, "missing")
        if len(matches) > 1:
            return ShortcutCatalogOutcome(None, "ambiguous")
        if matches[0] is None:
            return ShortcutCatalogOutcome(None, "unsupported")
        return ShortcutCatalogOutcome(matches[0])

    def _candidate_paths(self) -> tuple[Path, ...]:
        user_id = self._current_user_id()
        if not isinstance(user_id, str) or not user_id.strip().isdecimal():
            return ()
        parsed_user_id = int(user_id.strip())
        account_ids = [str(parsed_user_id)]
        if parsed_user_id >= _STEAM_ID64_BASE:
            account_id = parsed_user_id - _STEAM_ID64_BASE
            if 0 <= account_id <= 0xFFFFFFFF:
                account_ids.append(str(account_id))
        roots = (
            self._user_home / ".local/share/Steam/userdata",
            self._user_home / ".steam/steam/userdata",
            self._user_home / ".steam/root/userdata",
        )
        return tuple(
            root / account_id / "config/shortcuts.vdf"
            for root in roots
            for account_id in account_ids
        )
