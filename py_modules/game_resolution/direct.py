from __future__ import annotations

from collections.abc import Callable
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Literal

from .filesystem import FilesystemProbe
from .models import (
    RequestValidationError,
    ResolutionRequest,
    ResolutionResult,
)

_SHARED_OR_LAUNCHER_BINARIES = frozenset(
    {
        "bottles",
        "bottles.appimage",
        "bottles-cli",
        "cartridges",
        "flatpak",
        "gamescope",
        "gamehub",
        "heroic",
        "heroic.appimage",
        "itch",
        "legendary",
        "lutris",
        "minigalaxy",
        "proton",
        "rpcs3",
        "rpcs3.appimage",
        "retroarch",
        "ryujinx",
        "ryujinx.appimage",
        "steam",
        "wine",
        "wine64",
    }
)
_KNOWN_LAUNCHER_STEMS = frozenset(
    {
        "bottles",
        "cartridges",
        "gamehub",
        "heroic",
        "itch",
        "legendary",
        "lutris",
        "minigalaxy",
        "playnite",
        "proton",
        "steam",
        "ubisoftconnect",
        "wine",
    }
)
_KNOWN_EMULATOR_STEMS = frozenset(
    {
        "cemu",
        "dolphin",
        "duckstation",
        "pcsx2",
        "ppsspp",
        "retroarch",
        "rpcs3",
        "ryujinx",
    }
)
_KNOWN_SHELL_STEMS = frozenset(
    {
        "ash",
        "bash",
        "busybox",
        "cmd",
        "csh",
        "dash",
        "fish",
        "ksh",
        "mksh",
        "nu",
        "pdksh",
        "powershell",
        "pwsh",
        "rbash",
        "sh",
        "tcsh",
        "xonsh",
        "zsh",
    }
)
_UNSAFE_LITERAL_CHARACTERS = frozenset("?*[]{}|&;<>")
_WRAPPER_SUFFIXES = (".desktop", ".py", ".sh")
_NATIVE_SUFFIXES = frozenset({".x86", ".x86_64"})
_FLATPAK_APP_ID_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._+"
)
_FLATPAK_INFO_TIMEOUT_SECONDS = 0.25
_ENVIRONMENT_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
DirectPayloadType = Literal["windows", "appimage", "native"]


def _direct_launch_options_accepted(tokens: tuple[str, ...]) -> bool:
    """Return True for zero or more env assignments, then one %command%, then any args.

    An empty tuple is accepted: a shortcut with no launch options at all is the
    pre-existing supported shape.
    """
    if not tokens:
        return True
    index = 0
    while index < len(tokens) and _ENVIRONMENT_ASSIGNMENT.match(tokens[index]):
        index += 1
    if index >= len(tokens) or tokens[index] != "%command%":
        return False
    return "%command%" not in tokens[index + 1 :]


def host_subprocess_env() -> dict[str, str]:
    """
    Environment for host binaries we shell out to.

    Decky Loader ships as a PyInstaller bundle and puts its own extracted library
    directory on `LD_LIBRARY_PATH` for everything the plugin spawns. System
    binaries then link Decky's bundled OpenSSL instead of `/usr/lib`, and fail to
    start with a bare non-zero exit and no output. PyInstaller stashes the
    pre-launch value in `LD_LIBRARY_PATH_ORIG`, so restore that when present and
    drop the variable entirely otherwise.
    """
    env = dict(os.environ)
    original = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if original:
        env["LD_LIBRARY_PATH"] = original
    else:
        env.pop("LD_LIBRARY_PATH", None)
    return env


def _run_flatpak_info(app_id: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("flatpak", "info", "--show-location", app_id),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=_FLATPAK_INFO_TIMEOUT_SECONDS,
        text=True,
        env=host_subprocess_env(),
    )


def _is_flatpak_app_id(value: str | None) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 255
        and all(character in _FLATPAK_APP_ID_CHARACTERS for character in value)
    )


def _basename(path: str) -> str:
    return Path(path).name.casefold()


def _stem(path: str) -> str:
    return re.sub(r"\.(?:appimage|exe|x86|x86_64)$", "", _basename(path))


def _has_stem_variant(stem: str, known_stems: frozenset[str]) -> bool:
    return any(
        stem == known
        or (
            stem.startswith(known)
            and stem[len(known) : len(known) + 1] in {"-", "_", "."}
        )
        for known in known_stems
    )


def _is_known_shared_or_launcher(path: str) -> bool:
    name = _basename(path)
    stem = _stem(path)
    return (
        name in _SHARED_OR_LAUNCHER_BINARIES
        or _has_stem_variant(stem, _SHARED_OR_LAUNCHER_BINARIES)
        or _has_stem_variant(stem, _KNOWN_LAUNCHER_STEMS)
        or _has_stem_variant(stem, _KNOWN_EMULATOR_STEMS)
        or _has_stem_variant(stem, _KNOWN_SHELL_STEMS)
        or "launcher" in name
        or "emulator" in name
    )


def _parse_single_literal_path(value: str | None) -> str:
    if value is None:
        raise RequestValidationError("missing")
    if value[0] in {"'", '"'}:
        quote = value[0]
        if len(value) < 2 or value[-1] != quote:
            raise RequestValidationError("malformed")
        candidate = value[1:-1]
        if quote in candidate:
            raise RequestValidationError("malformed")
    else:
        candidate = value
        if any(character.isspace() for character in candidate):
            raise RequestValidationError("malformed")
    if (
        not candidate
        or not candidate.startswith("/")
        or "$" in candidate
        or "`" in candidate
        or any(character in _UNSAFE_LITERAL_CHARACTERS for character in candidate)
        or re.search(r"%[a-z][a-z0-9_]*%", candidate, re.IGNORECASE) is not None
        or re.search(r"[!+@]\(", candidate) is not None
    ):
        raise RequestValidationError("malformed")
    return candidate


def _direct_payload_type(path: str) -> DirectPayloadType | None:
    suffix = Path(path).suffix.casefold()
    if suffix == ".exe":
        return "windows"
    if suffix == ".appimage":
        return "appimage"
    if not suffix or suffix in _NATIVE_SUFFIXES:
        return "native"
    return None


def _has_direct_payload_evidence(
    payload_type: DirectPayloadType,
    file_mode: int | None,
    file_header: bytes | None,
) -> bool:
    if payload_type == "windows":
        return file_header is not None and file_header.startswith(b"MZ")
    return (
        file_mode is not None
        and bool(file_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        and file_header == b"\x7fELF"
    )


class DirectExecutableAdapter:
    launcher_kind = "direct"

    def __init__(self, probe: FilesystemProbe) -> None:
        self._probe = probe

    def resolve(self, request: ResolutionRequest) -> ResolutionResult:
        if request.classification_status == "ambiguous":
            return ResolutionResult.unknown(
                request.launcher_kind, request.classification_status, "ambiguous"
            )
        if request.classification_status != "recognized":
            return ResolutionResult.unknown(
                request.launcher_kind, request.classification_status, "missing"
            )
        try:
            candidate = self._validated_candidate(request)
        except RequestValidationError as error:
            return ResolutionResult.unknown(
                request.launcher_kind,
                request.classification_status,
                error.reason_code,
            )
        if self._is_rejected_path(candidate) or _direct_payload_type(candidate) is None:
            return ResolutionResult.unknown(
                request.launcher_kind, request.classification_status, "unsupported"
            )
        probe_result = self._probe.probe_regular_file(Path(candidate))
        if probe_result.reason_code is not None:
            if probe_result.reason_code in {
                "drive_disconnected",
                "kind_mismatch",
                "payload_missing",
            }:
                return ResolutionResult.unreachable(request, probe_result.reason_code)
            return ResolutionResult.unknown(
                request.launcher_kind,
                request.classification_status,
                probe_result.reason_code,
            )
        assert probe_result.payload_path is not None
        if self._is_rejected_path(probe_result.payload_path):
            return ResolutionResult.unknown(
                request.launcher_kind, request.classification_status, "unsupported"
            )
        payload_type = _direct_payload_type(probe_result.payload_path)
        if payload_type is None or not _has_direct_payload_evidence(
            payload_type,
            probe_result.file_mode,
            probe_result.file_header,
        ):
            return ResolutionResult.unknown(
                request.launcher_kind, request.classification_status, "unsupported"
            )
        return ResolutionResult.reachable(request, probe_result.payload_path)

    @staticmethod
    def _validated_candidate(request: ResolutionRequest) -> str:
        normalized = request.normalized
        candidate = _parse_single_literal_path(normalized.shortcut_exe)
        start_directory = (
            _parse_single_literal_path(normalized.shortcut_start_dir)
            if normalized.shortcut_start_dir is not None
            else None
        )
        if (
            normalized.flatpak_app_id is not None
            or normalized.executable_tokens != (candidate,)
            or normalized.command_tokens
            != (candidate, *normalized.launch_option_tokens)
            or not _direct_launch_options_accepted(normalized.launch_option_tokens)
            or (
                normalized.shortcut_launch_options is None
                and normalized.launch_option_tokens
            )
            or (
                normalized.shortcut_launch_options
                and not normalized.launch_option_tokens
            )
            or normalized.start_dir_tokens
            != (() if start_directory is None else (start_directory,))
        ):
            raise RequestValidationError("malformed")
        return candidate

    @staticmethod
    def _is_rejected_path(candidate: str) -> bool:
        lowercase = candidate.casefold()
        return (
            _is_known_shared_or_launcher(candidate)
            or lowercase.startswith(
                ("/app/bin/", "/bin/", "/sbin/", "/usr/bin/", "/usr/local/bin/")
            )
            or "/emulation/tools/launchers/" in lowercase
            or "/proton " in lowercase
            or "/steam/steamapps/common/proton" in lowercase
            or lowercase.endswith(_WRAPPER_SUFFIXES)
        )


class FlatpakExecutableAdapter:
    launcher_kind = "flatpak"

    def __init__(
        self,
        run_info: Callable[[str], subprocess.CompletedProcess[str]] = _run_flatpak_info,
    ) -> None:
        self._run_info = run_info

    def resolve(self, request: ResolutionRequest) -> ResolutionResult:
        if request.classification_status == "ambiguous":
            return ResolutionResult.unknown(
                request.launcher_kind, request.classification_status, "ambiguous"
            )
        if request.classification_status != "recognized":
            return ResolutionResult.unknown(
                request.launcher_kind, request.classification_status, "missing"
            )
        try:
            app_id = self._validated_candidate(request)
        except RequestValidationError as error:
            return ResolutionResult.unknown(
                request.launcher_kind,
                request.classification_status,
                error.reason_code,
            )

        try:
            payload_path = self.installed_payload_path(app_id, self._run_info)
        except RequestValidationError as error:
            return ResolutionResult.unknown(
                request.launcher_kind, request.classification_status, error.reason_code
            )

        if payload_path is None:
            return ResolutionResult.unreachable(request, "payload_missing")

        return ResolutionResult(
            launcher_kind=request.launcher_kind,
            classification_status=request.classification_status,
            metadata_status="not_requested",
            payload_status="reachable",
            payload_kind="directory",
            provenance="untrusted_hint",
            reason_code=None,
            payload_path=payload_path,
        )

    @staticmethod
    def installed_payload_path(
        app_id: str,
        run_info: Callable[[str], subprocess.CompletedProcess[str]] = _run_flatpak_info,
    ) -> str | None:
        if not _is_flatpak_app_id(app_id):
            return None

        try:
            result = run_info(app_id)
        except TimeoutError as error:
            raise RequestValidationError("probe_failure") from error
        except OSError as error:
            raise RequestValidationError("probe_failure") from error

        if result.returncode != 0:
            return None
        location = result.stdout.strip()
        if not location:
            return None
        return location

    @staticmethod
    def _validated_candidate(request: ResolutionRequest) -> str:
        app_id = request.normalized.flatpak_app_id
        if app_id is None:
            raise RequestValidationError("malformed")
        if not _is_flatpak_app_id(app_id):
            raise RequestValidationError("malformed")
        return app_id
