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
    file_mode: int | None = None
    file_header: bytes | None = None


MountTableProvider = Callable[[], tuple[MountEntry, ...] | None]
StatFunction = Callable[[Path], os.stat_result]
LstatFunction = Callable[[Path], os.stat_result]
ReadlinkFunction = Callable[[Path], str]
ReadPrefixFunction = Callable[[Path, int], bytes]
MAX_SYMLINK_EVIDENCE_HOPS = 8
PAYLOAD_FORMAT_PREFIX_LENGTH = 4


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


def read_file_prefix(path: Path, length: int) -> bytes:
    with path.open("rb") as file:
        return file.read(length)


class FilesystemProbe:
    def __init__(
        self,
        mount_entries: MountTableProvider = read_mount_table,
        stat_func: StatFunction = Path.stat,
        lstat_func: LstatFunction = Path.lstat,
        readlink_func: ReadlinkFunction = os.readlink,
        read_prefix_func: ReadPrefixFunction = read_file_prefix,
    ) -> None:
        self._mount_entries = mount_entries
        self._stat_func = stat_func
        self._lstat_func = lstat_func
        self._readlink_func = readlink_func
        self._read_prefix_func = read_prefix_func

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
            return FilesystemProbeResult(
                str(resolved),
                None,
                resolved_status.st_mode,
                self._read_prefix_func(resolved, PAYLOAD_FORMAT_PREFIX_LENGTH),
            )
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
            link_target = self._link_target_evidence(candidate)
            if link_target is not None:
                expected_volume = self._expected_removable_volume(link_target)
        if expected_volume is None:
            return "payload_missing"
        try:
            mounts = self._mount_entries()
        except Exception:
            return "probe_failure"
        if mounts is None:
            return "probe_failure"
        if not any(entry.mount_point == expected_volume for entry in mounts):
            return "drive_disconnected"
        return "payload_missing"

    def _link_target_evidence(self, candidate: Path) -> Path | None:
        """Follow a bounded leaf-or-ancestor symlink chain for volume evidence."""

        current = candidate
        for _ in range(MAX_SYMLINK_EVIDENCE_HOPS):
            link = self._first_symlink_component(current)
            if link is None:
                return current
            try:
                target = Path(self._readlink_func(link))
            except OSError:
                return None
            if target.is_absolute():
                resolved_target = target
            else:
                resolved_target = Path(os.path.abspath(link.parent / target))
            try:
                suffix = current.relative_to(link)
            except ValueError:
                return None
            current = resolved_target / suffix
        return None

    def _first_symlink_component(self, candidate: Path) -> Path | None:
        if not candidate.is_absolute():
            return None
        current = Path(candidate.anchor)
        for component in candidate.parts[1:]:
            current /= component
            try:
                status = self._lstat_func(current)
            except OSError:
                return None
            if stat.S_ISLNK(status.st_mode):
                return current
        return None

    @staticmethod
    def _expected_removable_volume(candidate: Path) -> Path | None:
        try:
            parts = candidate.relative_to("/run/media").parts
        except ValueError:
            return None
        if len(parts) < 2:
            return None
        return Path("/run/media") / parts[0] / parts[1]
