"""Focused tests for the canonical release archive contract."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
import warnings
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "release_archive", ROOT / "tools" / "release_archive.py"
)
assert SPEC and SPEC.loader
release_archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_archive)


class ReleaseArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.workdir = Path(self.temporary_directory.name)
        self.source = self.workdir / "renamed-checkout"
        self.source.mkdir()
        (self.source / "LICENSE").write_text("license\n")
        (self.source / "main.py").write_text("print('main')\n")
        (self.source / "README.md").write_text("readme\n")
        for name in ("package.json", "plugin.json"):
            (self.source / name).write_text(
                json.dumps({"name": "PlayTime", "version": "old"})
            )
        (self.source / "dist").mkdir()
        (self.source / "dist" / "index.js").write_text("bundle\n")
        (self.source / "py_modules").mkdir()
        (self.source / "py_modules" / "__init__.py").write_text("")
        (self.source / "py_modules" / "runtime.py").write_text("runtime\n")
        (self.source / "py_modules" / "__pycache__").mkdir()
        (self.source / "py_modules" / "__pycache__" / "runtime.pyc").write_bytes(
            b"cache"
        )
        (self.source / "py_modules" / "test_runtime.py").write_text("test tooling\n")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _build(self, version: str) -> Path:
        output = self.workdir / f"PlayTime-{version}.zip"
        return release_archive.build_archive(self.source, version, output)

    def _recompute_checksum(self, archive: Path) -> None:
        checksum = archive.with_name(f"{archive.name}.sha256")
        checksum.write_text(
            f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n",
            encoding="ascii",
        )

    def _append_member(
        self, archive: Path, name: str, data: bytes, external_attr: int | None = None
    ) -> None:
        member = zipfile.ZipInfo(name)
        member.create_system = 3
        if external_attr is not None:
            member.external_attr = external_attr
        with zipfile.ZipFile(archive, "a") as zip_file:
            zip_file.writestr(member, data)
        self._recompute_checksum(archive)

    def test_stable_archive_has_canonical_payload_checksum_and_root(self) -> None:
        version = "3.3.0+beallio.1"
        archive = self._build(version)
        checksum = archive.with_name(f"{archive.name}.sha256")
        self.assertEqual(
            hashlib.sha256(archive.read_bytes()).hexdigest(),
            checksum.read_text().split()[0],
        )
        release_archive.validate_archive(archive, version)

        with zipfile.ZipFile(archive) as zip_file:
            names = set(zip_file.namelist())
            self.assertTrue(all(name.startswith("SDH-PlayTime/") for name in names))
            self.assertIn("SDH-PlayTime/", names)
            for path in (
                "LICENSE",
                "main.py",
                "package.json",
                "plugin.json",
                "README.md",
                "dist/",
                "py_modules/",
            ):
                self.assertIn(f"SDH-PlayTime/{path}", names)
            self.assertNotIn("SDH-PlayTime/py_modules/test_runtime.py", names)
            self.assertNotIn("SDH-PlayTime/py_modules/__pycache__/runtime.pyc", names)
            for manifest_name in ("package.json", "plugin.json"):
                manifest = json.loads(zip_file.read(f"SDH-PlayTime/{manifest_name}"))
                self.assertEqual(
                    {"name": manifest["name"], "version": manifest["version"]},
                    {"name": "PlayTime", "version": version},
                )

    def test_custom_nightly_version_does_not_modify_checkout(self) -> None:
        archive = self._build("3.3.0+beallio.gabcdef0")
        self.assertEqual(
            json.loads((self.source / "package.json").read_text())["version"], "old"
        )
        self.assertEqual(
            json.loads((self.source / "plugin.json").read_text())["version"], "old"
        )
        release_archive.validate_archive(archive, "3.3.0+beallio.gabcdef0")

    def test_validation_rejects_tampered_checksum_and_unsafe_members(self) -> None:
        archive = self._build("3.3.0+beallio.1")
        archive.write_bytes(archive.read_bytes() + b"tamper")
        with self.assertRaises(release_archive.ArchiveValidationError):
            release_archive.validate_archive(archive, "3.3.0+beallio.1")

        for member_name in (
            "SDH-PlayTime/dist//index.js",
            "SDH-PlayTime/dist/./index.js",
            "SDH-PlayTime/../escape",
        ):
            archive = self._build("3.3.0+beallio.1")
            self._append_member(archive, member_name, b"noncanonical")
            with (
                self.subTest(member_name=member_name),
                self.assertRaisesRegex(
                    release_archive.ArchiveValidationError, "unsafe archive member"
                ),
            ):
                release_archive.validate_archive(archive, "3.3.0+beallio.1")

    def test_validation_rejects_symlink_directory_member(self) -> None:
        archive = self._build("3.3.0+beallio.1")
        self._append_member(
            archive,
            "SDH-PlayTime/dist/link/",
            b"target",
            (stat.S_IFLNK | 0o777) << 16,
        )
        with self.assertRaisesRegex(
            release_archive.ArchiveValidationError, "symbolic link"
        ):
            release_archive.validate_archive(archive, "3.3.0+beallio.1")

    def test_validation_requires_runtime_entries(self) -> None:
        archive = self._build("3.3.0+beallio.1")
        for missing_name in (
            "SDH-PlayTime/dist/index.js",
            "SDH-PlayTime/py_modules/__init__.py",
        ):
            incomplete = self.workdir / f"without-{Path(missing_name).name}.zip"
            with (
                zipfile.ZipFile(archive) as source,
                zipfile.ZipFile(incomplete, "w") as target,
            ):
                for member in source.infolist():
                    if member.filename != missing_name:
                        target.writestr(member, source.read(member.filename))
            self._recompute_checksum(incomplete)
            with (
                self.subTest(missing_name=missing_name),
                self.assertRaisesRegex(
                    release_archive.ArchiveValidationError, "missing required payload"
                ),
            ):
                release_archive.validate_archive(incomplete, "3.3.0+beallio.1")

    def test_validation_rejects_duplicate_paths(self) -> None:
        archive = self._build("3.3.0+beallio.1")
        duplicate = self.workdir / "duplicate.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with (
                zipfile.ZipFile(archive) as source,
                zipfile.ZipFile(duplicate, "w") as target,
            ):
                for member in source.infolist():
                    target.writestr(member, source.read(member.filename))
                target.writestr("SDH-PlayTime/main.py", "duplicate")
        checksum = duplicate.with_name(f"{duplicate.name}.sha256")
        checksum.write_text(
            f"{hashlib.sha256(duplicate.read_bytes()).hexdigest()}  {duplicate.name}\n"
        )
        with self.assertRaises(release_archive.ArchiveValidationError):
            release_archive.validate_archive(duplicate, "3.3.0+beallio.1")


if __name__ == "__main__":
    unittest.main()
