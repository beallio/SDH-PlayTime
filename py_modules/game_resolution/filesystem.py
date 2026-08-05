from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .models import ReasonCode


@dataclass(frozen=True, slots=True)
class MountEntry:
    mount_point: Path


@dataclass(frozen=True, slots=True)
class FilesystemProbeResult:
    payload_path: str | None
    reason_code: ReasonCode | None


MountTableProvider = Callable[[], tuple[MountEntry, ...] | None]
StatFunction = Callable[[Path], os.stat_result]


def _unescape_mount_path(value: str) -> str:
    for escaped, character in (("\\040", " "), ("\\011", "\t"), ("\\134", "\\")):
        value = value.replace(escaped, character)
    return value


def read_mount_table() -> tuple[MountEntry, ...] | None:
    """Read Linux mountinfo without spawning a command or mounting anything."""

    try:
        contents = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    except OSError:
        return None

    entries: list[MountEntry] = []
    for line in contents.splitlines():
        fields = line.split(" - ", maxsplit=1)[0].split()
        if len(fields) < 5:
            continue
        entries.append(MountEntry(Path(_unescape_mount_path(fields[4]))))
    return tuple(entries)


class FilesystemProbe:
    def __init__(
        self,
        mount_entries: MountTableProvider = read_mount_table,
        stat_func: StatFunction = Path.stat,
    ) -> None:
        self._mount_entries = mount_entries
        self._stat_func = stat_func

    def probe_regular_file(self, candidate: Path) -> FilesystemProbeResult:
        """Probe one explicit candidate path without walking parent directories."""

        try:
            file_status = self._stat_func(candidate)
            if not stat.S_ISREG(file_status.st_mode):
                return FilesystemProbeResult(None, "kind_mismatch")
            resolved = candidate.resolve(strict=True)
            resolved_status = self._stat_func(resolved)
            if not stat.S_ISREG(resolved_status.st_mode):
                return FilesystemProbeResult(None, "kind_mismatch")
            return FilesystemProbeResult(str(resolved), None)
        except FileNotFoundError:
            return FilesystemProbeResult(None, self._missing_reason(candidate))
        except NotADirectoryError:
            return FilesystemProbeResult(None, "kind_mismatch")
        except PermissionError:
            return FilesystemProbeResult(None, "permission_denied")
        except OSError:
            return FilesystemProbeResult(None, "probe_failure")

    def _missing_reason(self, candidate: Path) -> ReasonCode:
        expected_volume = self._expected_removable_volume(candidate)
        if expected_volume is None:
            return "payload_missing"
        try:
            mounts = self._mount_entries()
        except OSError:
            return "payload_missing"
        if mounts is None:
            return "payload_missing"
        if not any(entry.mount_point == expected_volume for entry in mounts):
            return "drive_disconnected"
        return "payload_missing"

    @staticmethod
    def _expected_removable_volume(candidate: Path) -> Path | None:
        try:
            parts = candidate.relative_to("/run/media").parts
        except ValueError:
            return None
        if len(parts) < 2:
            return None
        return Path("/run/media") / parts[0] / parts[1]
