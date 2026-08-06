from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal, Mapping, cast

MAX_RESOLUTION_BATCH_SIZE = 32
MAX_METADATA_CANDIDATES = 8
MAX_SHORTCUT_FIELD_LENGTH = 4096
MAX_METADATA_CANDIDATE_LENGTH = 512
MAX_SHORTCUT_TOKENS = 32

LauncherKind = Literal[
    "direct", "heroic", "lutris", "bottles", "emudeck-srm", "flatpak", "unknown"
]
ClassificationStatus = Literal["recognized", "unknown", "ambiguous"]
MetadataStatus = Literal["not_requested", "not_found", "resolved", "invalid"]
PayloadStatus = Literal["reachable", "unreachable", "unknown"]
PayloadKind = Literal["file", "directory", "unknown"]
Provenance = Literal["direct_executable", "heroic_metadata", "untrusted_hint", "none"]
ReasonCode = Literal[
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
]

_LAUNCHER_KINDS = frozenset(
    {"direct", "heroic", "lutris", "bottles", "emudeck-srm", "flatpak", "unknown"}
)
_CLASSIFICATION_STATUSES = frozenset({"recognized", "unknown", "ambiguous"})


class RequestValidationError(ValueError):
    def __init__(self, reason_code: ReasonCode) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _bounded_optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RequestValidationError("malformed")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > MAX_SHORTCUT_FIELD_LENGTH or "\x00" in normalized:
        raise RequestValidationError("malformed")
    return normalized


def _bounded_token_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > MAX_SHORTCUT_TOKENS:
        raise RequestValidationError("malformed")
    tokens: list[str] = []
    for token in value:
        if (
            not isinstance(token, str)
            or not token
            or len(token) > MAX_SHORTCUT_FIELD_LENGTH
        ):
            raise RequestValidationError("malformed")
        if "\x00" in token:
            raise RequestValidationError("malformed")
        tokens.append(token)
    return tuple(tokens)


def _metadata_candidates(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > MAX_METADATA_CANDIDATES:
        raise RequestValidationError("malformed")
    candidates: list[str] = []
    for candidate in value:
        if (
            not isinstance(candidate, str)
            or not candidate
            or len(candidate) > MAX_METADATA_CANDIDATE_LENGTH
            or "\x00" in candidate
        ):
            raise RequestValidationError("malformed")
        path = PurePosixPath(candidate)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise RequestValidationError("malformed")
        candidates.append(candidate)
    return tuple(candidates)


@dataclass(frozen=True, slots=True)
class NormalizedShortcutEvidence:
    flatpak_app_id: str | None
    shortcut_exe: str | None
    shortcut_launch_options: str | None
    shortcut_start_dir: str | None
    executable_tokens: tuple[str, ...]
    launch_option_tokens: tuple[str, ...]
    start_dir_tokens: tuple[str, ...]
    command_tokens: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: object) -> "NormalizedShortcutEvidence":
        if not isinstance(value, Mapping):
            raise RequestValidationError("malformed")
        return cls(
            flatpak_app_id=_bounded_optional_string(value.get("flatpakAppId")),
            shortcut_exe=_bounded_optional_string(value.get("shortcutExe")),
            shortcut_launch_options=_bounded_optional_string(
                value.get("shortcutLaunchOptions")
            ),
            shortcut_start_dir=_bounded_optional_string(value.get("shortcutStartDir")),
            executable_tokens=_bounded_token_tuple(value.get("executableTokens")),
            launch_option_tokens=_bounded_token_tuple(value.get("launchOptionTokens")),
            start_dir_tokens=_bounded_token_tuple(value.get("startDirTokens")),
            command_tokens=_bounded_token_tuple(value.get("commandTokens")),
        )


@dataclass(frozen=True, slots=True)
class ResolutionRequest:
    launcher_kind: LauncherKind
    classification_status: ClassificationStatus
    normalized: NormalizedShortcutEvidence
    metadata_candidates: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: object) -> "ResolutionRequest":
        if not isinstance(value, Mapping):
            raise RequestValidationError("malformed")
        launcher_kind = value.get("launcherKind")
        classification_status = value.get("classificationStatus")
        if launcher_kind not in _LAUNCHER_KINDS:
            raise RequestValidationError("malformed")
        if classification_status not in _CLASSIFICATION_STATUSES:
            raise RequestValidationError("malformed")
        return cls(
            launcher_kind=cast(LauncherKind, launcher_kind),
            classification_status=cast(ClassificationStatus, classification_status),
            normalized=NormalizedShortcutEvidence.from_mapping(value.get("normalized")),
            metadata_candidates=_metadata_candidates(value.get("metadataCandidates")),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "launcherKind": self.launcher_kind,
            "classificationStatus": self.classification_status,
            "normalized": {
                "flatpakAppId": self.normalized.flatpak_app_id,
                "shortcutExe": self.normalized.shortcut_exe,
                "shortcutLaunchOptions": self.normalized.shortcut_launch_options,
                "shortcutStartDir": self.normalized.shortcut_start_dir,
                "executableTokens": list(self.normalized.executable_tokens),
                "launchOptionTokens": list(self.normalized.launch_option_tokens),
                "startDirTokens": list(self.normalized.start_dir_tokens),
                "commandTokens": list(self.normalized.command_tokens),
            },
            "metadataCandidates": list(self.metadata_candidates),
        }


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    launcher_kind: LauncherKind
    classification_status: ClassificationStatus
    metadata_status: MetadataStatus
    payload_status: PayloadStatus
    payload_kind: PayloadKind
    provenance: Provenance
    reason_code: ReasonCode | None
    payload_path: str | None

    @classmethod
    def unknown(
        cls,
        launcher_kind: LauncherKind = "unknown",
        classification_status: ClassificationStatus = "unknown",
        reason_code: ReasonCode = "malformed",
        metadata_status: MetadataStatus = "not_requested",
    ) -> "ResolutionResult":
        return cls(
            launcher_kind=launcher_kind,
            classification_status=classification_status,
            metadata_status=metadata_status,
            payload_status="unknown",
            payload_kind="unknown",
            provenance="untrusted_hint",
            reason_code=reason_code,
            payload_path=None,
        )

    @classmethod
    def reachable(
        cls, request: ResolutionRequest, payload_path: str
    ) -> "ResolutionResult":
        return cls(
            launcher_kind=request.launcher_kind,
            classification_status=request.classification_status,
            metadata_status="not_requested",
            payload_status="reachable",
            payload_kind="file",
            provenance="direct_executable",
            reason_code=None,
            payload_path=payload_path,
        )

    @classmethod
    def unreachable(
        cls, request: ResolutionRequest, reason_code: ReasonCode
    ) -> "ResolutionResult":
        return cls(
            launcher_kind=request.launcher_kind,
            classification_status=request.classification_status,
            metadata_status="not_requested",
            payload_status="unreachable",
            payload_kind="unknown",
            provenance="direct_executable",
            reason_code=reason_code,
            payload_path=None,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "launcher_kind": self.launcher_kind,
            "classification_status": self.classification_status,
            "metadata_status": self.metadata_status,
            "payload_status": self.payload_status,
            "payload_kind": self.payload_kind,
            "provenance": self.provenance,
            "reason_code": self.reason_code,
            "payload_path": self.payload_path,
        }


@dataclass(frozen=True, slots=True)
class BatchResolutionResult:
    results: tuple[ResolutionResult, ...]
    error: ReasonCode | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "results": [result.to_dict() for result in self.results],
            "error": self.error,
        }
