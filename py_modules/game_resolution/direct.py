from __future__ import annotations

import re
from pathlib import Path

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
_UNSAFE_LITERAL_CHARACTERS = frozenset("$`?*[]{}|&;<>")
_WRAPPER_SUFFIXES = (".desktop", ".py", ".sh")


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
        or any(character in _UNSAFE_LITERAL_CHARACTERS for character in candidate)
        or "!+(" in candidate
    ):
        raise RequestValidationError("malformed")
    return candidate


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
        if _is_known_shared_or_launcher(candidate) or self._is_wrapper_path(candidate):
            return ResolutionResult.unknown(
                request.launcher_kind, request.classification_status, "unsupported"
            )
        probe_result = self._probe.probe_regular_file(Path(candidate))
        if probe_result.reason_code is not None:
            return ResolutionResult.unknown(
                request.launcher_kind,
                request.classification_status,
                probe_result.reason_code,
            )
        assert probe_result.payload_path is not None
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
    def _is_wrapper_path(candidate: str) -> bool:
        lowercase = candidate.casefold()
        return (
            lowercase.startswith(
                ("/app/bin/", "/bin/", "/sbin/", "/usr/bin/", "/usr/local/bin/")
            )
            or "/emulation/tools/launchers/" in lowercase
            or "/proton " in lowercase
            or "/steam/steamapps/common/proton" in lowercase
            or lowercase.endswith(_WRAPPER_SUFFIXES)
        )
