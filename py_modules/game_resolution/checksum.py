from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from .models import BatchResolutionResult, ReasonCode, ResolutionResult


ChecksumStatus = Literal[
    "ready",
    "unsupported_shortcut",
    "missing_metadata",
    "payload_unavailable",
    "hash_failure",
]
ChecksumReasonCode = ReasonCode | Literal["hash_failure"]


class ChecksumResolver(Protocol):
    def resolve_batch(self, entries: object) -> BatchResolutionResult: ...


class FileHasher(Protocol):
    def get_file_sha256(self, file_path: str) -> str | None: ...


@dataclass(frozen=True, slots=True)
class GameChecksumResult:
    checksum: str | None
    status: ChecksumStatus
    reason_code: ChecksumReasonCode | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "checksum": self.checksum,
            "status": self.status,
            "reason_code": self.reason_code,
        }


class GameChecksumCoordinator:
    """Resolve untrusted shortcut evidence before hashing its verified payload."""

    def __init__(self, resolver: ChecksumResolver, files: FileHasher) -> None:
        self._resolver = resolver
        self._files = files

    def get_checksum(self, shortcut_evidence: object) -> GameChecksumResult:
        resolution = self._single_resolution(shortcut_evidence)
        if isinstance(resolution, GameChecksumResult):
            return resolution
        if (
            resolution.payload_status != "reachable"
            or resolution.payload_kind != "file"
            or resolution.payload_path is None
        ):
            return self._resolution_failure(resolution)

        try:
            checksum = self._files.get_file_sha256(resolution.payload_path)
        except Exception:
            return GameChecksumResult(None, "hash_failure", "hash_failure")
        if checksum is None:
            return GameChecksumResult(None, "payload_unavailable", "payload_missing")
        return GameChecksumResult(checksum, "ready", None)

    def _single_resolution(
        self, shortcut_evidence: object
    ) -> ResolutionResult | GameChecksumResult:
        batch = self._resolver.resolve_batch([shortcut_evidence])
        if batch.error is not None or len(batch.results) != 1:
            return GameChecksumResult(None, "unsupported_shortcut", "malformed")
        return batch.results[0]

    @staticmethod
    def _resolution_failure(result: ResolutionResult) -> GameChecksumResult:
        if result.launcher_kind == "heroic" and result.metadata_status in {
            "not_found",
            "invalid",
        }:
            return GameChecksumResult(None, "missing_metadata", result.reason_code)
        if result.reason_code in {"unsupported", "ambiguous", "malformed"}:
            return GameChecksumResult(None, "unsupported_shortcut", result.reason_code)
        return GameChecksumResult(None, "payload_unavailable", result.reason_code)
