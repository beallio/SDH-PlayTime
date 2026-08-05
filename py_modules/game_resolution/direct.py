from __future__ import annotations

import re
import stat
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
_UNSAFE_LITERAL_CHARACTERS = frozenset("?*[]{}|&;<>")
_WRAPPER_SUFFIXES = (".desktop", ".py", ".sh")
_NATIVE_SUFFIXES = frozenset({".x86", ".x86_64"})
DirectPayloadType = Literal["windows", "appimage", "native"]


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
            or normalized.command_tokens != (candidate,)
            or normalized.launch_option_tokens
            or normalized.shortcut_launch_options is not None
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
