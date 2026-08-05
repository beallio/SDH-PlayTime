#!/usr/bin/env python3
"""Build and validate canonical SDH-PlayTime release archives.

This script packages an already-built checkout.  It deliberately does not run
the frontend build or modify the checkout, so release automation can choose an
exact stable or nightly version without creating a dirty worktree.
"""

from __future__ import annotations

import argparse
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import zipfile


ARCHIVE_ROOT = "SDH-PlayTime"
PLUGIN_NAME = "PlayTime"
VENDORED_REQUIREMENTS_FILE = "requirements-vendored.txt"
VENDORED_PYYAML_NAME = "PyYAML"
VENDORED_PYYAML_DIST_INFO_PREFIX = "pyyaml-"
VENDORED_PYYAML_REQUIRED_DIST_INFO_FILES = frozenset(
    {"METADATA", "licenses/LICENSE"}
)
VENDORED_PYYAML_DEVELOPMENT_FILES = frozenset(
    {"INSTALLER", "REQUESTED", "direct_url.json"}
)
VENDORED_PYYAML_COMPILED_SUFFIXES = frozenset({".dll", ".dylib", ".pyd", ".so"})
REQUIRED_FILES = (
    "LICENSE",
    "main.py",
    "package.json",
    "plugin.json",
    "README.md",
    VENDORED_REQUIREMENTS_FILE,
)
REQUIRED_DIRECTORIES = ("dist", "py_modules")
REQUIRED_RUNTIME_FILES = (
    "dist/index.js",
    "py_modules/__init__.py",
    "py_modules/safe_yaml.py",
    "py_modules/yaml/__init__.py",
)
_EXCLUDED_DIRECTORY_NAMES = {"__pycache__", ".pytest_cache"}
_EXCLUDED_FILE_SUFFIXES = {".pyc", ".pyo"}


class ArchiveValidationError(ValueError):
    """Raised when an archive does not meet the release contract."""


def _archive_name(relative_path: Path, is_directory: bool = False) -> str:
    suffix = "/" if is_directory else ""
    return f"{ARCHIVE_ROOT}/{relative_path.as_posix()}{suffix}"


def _is_excluded(path: Path) -> bool:
    if any(part in _EXCLUDED_DIRECTORY_NAMES for part in path.parts):
        return True
    return (
        path.name.startswith("test_")
        or path.name.endswith("_test.py")
        or path.suffix in _EXCLUDED_FILE_SUFFIXES
    )


def _parse_vendored_pyyaml_pin(contents: str) -> str:
    lines = contents.splitlines()
    if len(lines) != 1:
        raise ArchiveValidationError(
            f"{VENDORED_REQUIREMENTS_FILE} must declare exactly one dependency pin"
        )
    name, separator, version = lines[0].partition("==")
    if name != VENDORED_PYYAML_NAME or separator != "==" or not version:
        raise ArchiveValidationError(
            f"{VENDORED_REQUIREMENTS_FILE} must pin {VENDORED_PYYAML_NAME}"
        )
    return version


def _pyyaml_dist_info_name(version: str) -> str:
    return f"{VENDORED_PYYAML_DIST_INFO_PREFIX}{version}.dist-info"


def _validate_vendored_pyyaml_metadata(metadata: bytes, version: str) -> None:
    parsed = BytesParser().parsebytes(metadata)
    if parsed.get_all("Name") != [VENDORED_PYYAML_NAME] or parsed.get_all(
        "Version"
    ) != [version]:
        raise ArchiveValidationError(
            "vendored PyYAML metadata must match the declared dependency pin"
        )


def _is_forbidden_vendored_pyyaml_path(path: PurePosixPath) -> bool:
    return (
        any(part in _EXCLUDED_DIRECTORY_NAMES | {"tests"} for part in path.parts)
        or path.name.startswith("test_")
        or path.name.endswith("_test.py")
        or path.name in VENDORED_PYYAML_DEVELOPMENT_FILES
        or path.suffix in _EXCLUDED_FILE_SUFFIXES | VENDORED_PYYAML_COMPILED_SUFFIXES
    )


def _validate_vendored_pyyaml_paths(
    relative_paths: list[PurePosixPath], version: str
) -> None:
    """Validate the deliberately small pure-Python PyYAML payload."""
    dist_info = _pyyaml_dist_info_name(version)
    required_paths = {
        PurePosixPath("py_modules", "safe_yaml.py"),
        PurePosixPath("py_modules", "yaml", "__init__.py"),
        PurePosixPath("py_modules", dist_info, "METADATA"),
        PurePosixPath("py_modules", dist_info, "licenses", "LICENSE"),
    }
    available_paths = set(relative_paths)
    missing_paths = required_paths.difference(available_paths)
    if missing_paths:
        raise ArchiveValidationError(
            "vendored PyYAML payload is missing required files: "
            + ", ".join(path.as_posix() for path in sorted(missing_paths))
        )

    dist_infos = {
        path.parts[1]
        for path in relative_paths
        if len(path.parts) >= 2
        and path.parts[0] == "py_modules"
        and path.parts[1].lower().startswith(VENDORED_PYYAML_DIST_INFO_PREFIX)
        and path.parts[1].endswith(".dist-info")
    }
    if dist_infos != {dist_info}:
        raise ArchiveValidationError(
            "vendored PyYAML must contain exactly one matching dist-info directory"
        )

    dist_info_files = {
        PurePosixPath(*path.parts[2:]).as_posix()
        for path in relative_paths
        if len(path.parts) >= 3
        and path.parts[:2] == ("py_modules", dist_info)
    }
    if dist_info_files != VENDORED_PYYAML_REQUIRED_DIST_INFO_FILES:
        raise ArchiveValidationError(
            "vendored PyYAML dist-info contains missing or development-only files"
        )

    for path in relative_paths:
        if len(path.parts) < 2 or path.parts[0] != "py_modules":
            continue
        root = path.parts[1]
        if root == "_yaml":
            raise ArchiveValidationError(
                "vendored PyYAML payload may not include the native _yaml extension"
            )
        if root in {"yaml", dist_info} and _is_forbidden_vendored_pyyaml_path(
            PurePosixPath(*path.parts[2:])
        ):
            raise ArchiveValidationError(
                "vendored PyYAML payload may not include compiled, cache, or development files"
            )


def _validate_vendored_pyyaml_source(source: Path) -> None:
    pin_path = source / VENDORED_REQUIREMENTS_FILE
    if not pin_path.is_file() or pin_path.is_symlink():
        raise ArchiveValidationError(f"vendored dependency pin is missing or unsafe: {pin_path}")
    try:
        version = _parse_vendored_pyyaml_pin(pin_path.read_text(encoding="utf-8"))
        py_modules = source / "py_modules"
        relative_paths = [
            path.relative_to(source)
            for path in py_modules.rglob("*")
            if path.is_file() and not path.is_symlink()
        ]
        _validate_vendored_pyyaml_paths(relative_paths, version)
        metadata = (
            py_modules / _pyyaml_dist_info_name(version) / "METADATA"
        ).read_bytes()
    except (OSError, UnicodeDecodeError) as error:
        raise ArchiveValidationError(
            f"could not read vendored PyYAML payload from {source}: {error}"
        ) from error
    _validate_vendored_pyyaml_metadata(metadata, version)


def _validate_vendored_pyyaml_archive(
    zip_file: zipfile.ZipFile, paths: list[PurePosixPath]
) -> None:
    try:
        version = _parse_vendored_pyyaml_pin(
            zip_file.read(f"{ARCHIVE_ROOT}/{VENDORED_REQUIREMENTS_FILE}").decode("utf-8")
        )
        relative_paths = [
            PurePosixPath(*path.parts[1:]) for path in paths if len(path.parts) > 1
        ]
        _validate_vendored_pyyaml_paths(relative_paths, version)
        metadata = zip_file.read(
            f"{ARCHIVE_ROOT}/py_modules/{_pyyaml_dist_info_name(version)}/METADATA"
        )
    except (KeyError, UnicodeDecodeError) as error:
        raise ArchiveValidationError(
            f"could not read vendored PyYAML payload from archive: {error}"
        ) from error
    _validate_vendored_pyyaml_metadata(metadata, version)


def _iter_release_files(source: Path) -> list[tuple[Path, Path]]:
    """Return the archive-relative files selected from an already-built tree."""
    _validate_vendored_pyyaml_source(source)
    selected: list[tuple[Path, Path]] = []
    for filename in REQUIRED_FILES:
        path = source / filename
        if not path.is_file() or path.is_symlink():
            raise ArchiveValidationError(f"required release file is missing or unsafe: {path}")
        selected.append((path, Path(filename)))

    for directory in REQUIRED_DIRECTORIES:
        root = source / directory
        if not root.is_dir() or root.is_symlink():
            raise ArchiveValidationError(f"required release directory is missing or unsafe: {root}")
        for path in sorted(root.rglob("*")):
            relative_path = path.relative_to(source)
            if _is_excluded(relative_path):
                continue
            if path.is_symlink():
                raise ArchiveValidationError(f"release payload may not contain symlinks: {path}")
            if path.is_file():
                selected.append((path, relative_path))
            elif not path.is_dir():
                raise ArchiveValidationError(f"release payload contains an unsupported path: {path}")
    return selected


def _manifest_bytes(path: Path, version: str) -> bytes:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ArchiveValidationError(f"could not read manifest {path}: {error}") from error
    if manifest.get("name") != PLUGIN_NAME:
        raise ArchiveValidationError(f"manifest identity must remain {PLUGIN_NAME}: {path}")
    manifest["version"] = version
    return (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _write_checksum(archive: Path) -> Path:
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum_path = archive.with_name(f"{archive.name}.sha256")
    checksum_path.write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    return checksum_path


def _read_checksum(checksum_path: Path, archive: Path) -> str:
    try:
        line = checksum_path.read_text(encoding="ascii").strip()
        digest, filename = line.split(maxsplit=1)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ArchiveValidationError(f"invalid checksum file: {checksum_path}") from error
    if len(digest) != 64 or any(character not in "0123456789abcdefABCDEF" for character in digest):
        raise ArchiveValidationError(f"invalid SHA-256 digest in {checksum_path}")
    if filename.lstrip("*") != archive.name:
        raise ArchiveValidationError(f"checksum filename does not match archive: {checksum_path}")
    return digest.lower()


def _validate_member_name(name: str) -> PurePosixPath:
    if "\\" in name or name.startswith("/"):
        raise ArchiveValidationError(f"unsafe archive member: {name!r}")
    canonical_name = name[:-1] if name.endswith("/") else name
    if not canonical_name or any(
        part in {"", ".", ".."} for part in canonical_name.split("/")
    ):
        raise ArchiveValidationError(f"unsafe archive member: {name!r}")
    return PurePosixPath(canonical_name)


def validate_archive(archive: Path, version: str, checksum_path: Path | None = None) -> None:
    """Fail closed unless *archive* and its sidecar checksum meet the contract."""
    if not archive.is_file():
        raise ArchiveValidationError(f"archive does not exist: {archive}")
    checksum_path = checksum_path or archive.with_name(f"{archive.name}.sha256")
    expected_digest = _read_checksum(checksum_path, archive)
    actual_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual_digest != expected_digest:
        raise ArchiveValidationError(f"checksum does not match archive: {archive}")

    try:
        with zipfile.ZipFile(archive) as zip_file:
            corrupted_member = zip_file.testzip()
            if corrupted_member:
                raise ArchiveValidationError(f"ZIP CRC check failed for: {corrupted_member}")
            members = zip_file.infolist()
            names = [member.filename for member in members]
            if len(names) != len(set(names)):
                raise ArchiveValidationError("archive contains duplicate paths")
            paths = [_validate_member_name(name) for name in names]
            roots = {path.parts[0] for path in paths}
            if roots != {ARCHIVE_ROOT}:
                raise ArchiveValidationError(f"archive must have exactly one {ARCHIVE_ROOT}/ root")
            if any(stat.S_ISLNK(member.external_attr >> 16) for member in members):
                raise ArchiveValidationError("archive contains a symbolic link")

            required_paths = {f"{ARCHIVE_ROOT}/{name}" for name in REQUIRED_FILES}
            required_paths.update(f"{ARCHIVE_ROOT}/{name}/" for name in REQUIRED_DIRECTORIES)
            required_paths.update(f"{ARCHIVE_ROOT}/{name}" for name in REQUIRED_RUNTIME_FILES)
            missing = required_paths.difference(names)
            if missing:
                raise ArchiveValidationError(f"archive is missing required payload: {', '.join(sorted(missing))}")

            allowed_roots = set(REQUIRED_FILES) | set(REQUIRED_DIRECTORIES)
            for member, path in zip(members, paths, strict=True):
                if len(path.parts) == 1:
                    if not member.is_dir():
                        raise ArchiveValidationError("archive root must be a directory")
                    continue
                if path.parts[1] not in allowed_roots:
                    raise ArchiveValidationError(f"archive contains non-release payload: {path}")

            _validate_vendored_pyyaml_archive(zip_file, paths)

            package_manifest = json.loads(zip_file.read(f"{ARCHIVE_ROOT}/package.json"))
            plugin_manifest = json.loads(zip_file.read(f"{ARCHIVE_ROOT}/plugin.json"))
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise ArchiveValidationError(f"could not validate ZIP archive: {error}") from error

    for manifest_name, manifest in (("package.json", package_manifest), ("plugin.json", plugin_manifest)):
        if manifest.get("name") != PLUGIN_NAME or manifest.get("version") != version:
            raise ArchiveValidationError(f"{manifest_name} does not preserve {PLUGIN_NAME} at version {version}")


def build_archive(source: Path, version: str, output: Path) -> Path:
    """Create, checksum, and validate a canonical release archive."""
    if not version or version.strip() != version:
        raise ArchiveValidationError("version must be a non-empty, unpadded string")
    source = source.resolve()
    if not source.is_dir():
        raise ArchiveValidationError(f"source checkout does not exist: {source}")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    selected = _iter_release_files(source)
    manifests = {Path("package.json"): _manifest_bytes(source / "package.json", version), Path("plugin.json"): _manifest_bytes(source / "plugin.json", version)}

    with tempfile.TemporaryDirectory(dir=output.parent, prefix=f".{output.name}.") as temporary_directory:
        temporary_output = Path(temporary_directory) / output.name
        with zipfile.ZipFile(temporary_output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
            zip_file.writestr(f"{ARCHIVE_ROOT}/", b"")
            for directory in REQUIRED_DIRECTORIES:
                zip_file.writestr(_archive_name(Path(directory), is_directory=True), b"")
            for path, relative_path in selected:
                if relative_path in manifests:
                    zip_file.writestr(_archive_name(relative_path), manifests[relative_path])
                else:
                    zip_file.write(path, _archive_name(relative_path))
        temporary_checksum = _write_checksum(temporary_output)
        validate_archive(temporary_output, version, temporary_checksum)
        os.replace(temporary_output, output)
        os.replace(temporary_checksum, output.with_name(f"{output.name}.sha256"))
    return output


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    build = subcommands.add_parser("build", help="build, checksum, and validate an archive")
    build.add_argument("--source", type=Path, required=True, help="already-built checkout")
    build.add_argument("--version", required=True, help="version to embed in both manifests")
    build.add_argument("--output", type=Path, required=True, help="output .zip path")
    validate = subcommands.add_parser("validate", help="validate an archive and its checksum")
    validate.add_argument("--archive", type=Path, required=True)
    validate.add_argument("--version", required=True)
    validate.add_argument("--checksum", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if args.command == "build":
            build_archive(args.source, args.version, args.output)
        else:
            validate_archive(args.archive, args.version, args.checksum)
    except ArchiveValidationError as error:
        print(f"release archive validation failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
