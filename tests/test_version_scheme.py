"""Executable SemVer precedence rules for remix release versions."""

from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def semver_precedence(a: str, b: str) -> int:
    """Return the SemVer 2.0 precedence of *a* relative to *b*."""

    def split_version(version: str) -> tuple[tuple[int, int, int], list[str] | None]:
        without_build_metadata = version.split("+", 1)[0]
        core, separator, prerelease = without_build_metadata.partition("-")
        major, minor, patch = (int(part) for part in core.split("."))
        return (major, minor, patch), prerelease.split(".") if separator else None

    a_core, a_prerelease = split_version(a)
    b_core, b_prerelease = split_version(b)
    if a_core != b_core:
        return (a_core > b_core) - (a_core < b_core)
    if a_prerelease is None or b_prerelease is None:
        if a_prerelease is None and b_prerelease is None:
            return 0
        return 1 if a_prerelease is None else -1

    for a_identifier, b_identifier in zip(a_prerelease, b_prerelease):
        if a_identifier == b_identifier:
            continue
        a_numeric = a_identifier.isdigit()
        b_numeric = b_identifier.isdigit()
        if a_numeric and b_numeric:
            return (int(a_identifier) > int(b_identifier)) - (
                int(a_identifier) < int(b_identifier)
            )
        if a_numeric != b_numeric:
            return -1 if a_numeric else 1
        return (a_identifier > b_identifier) - (a_identifier < b_identifier)
    return (len(a_prerelease) > len(b_prerelease)) - (
        len(a_prerelease) < len(b_prerelease)
    )


def manifest_version() -> str:
    package_version = json.loads(
        (ROOT / "package.json").read_text(encoding="utf-8")
    )["version"]
    plugin_version = json.loads(
        (ROOT / "plugin.json").read_text(encoding="utf-8")
    )["version"]
    if package_version != plugin_version:
        raise AssertionError("package.json and plugin.json versions must be identical")
    return package_version


class VersionSchemeTests(unittest.TestCase):
    def test_comparator_matches_compare_versions_6_1_1(self) -> None:
        cases = (
            ("3.3.1-beallio.11", "3.3.0", 1),
            ("3.3.1-beallio.11", "3.3.0+beallio.10", 1),
            ("3.3.1-beallio.12", "3.3.1-beallio.11", 1),
            ("3.3.1-beallio.2", "3.3.1-beallio.11", -1),
            ("3.3.1", "3.3.1-beallio.11", 1),
            (
                "3.3.1-beallio.11.dev.20260808.g1a2b3c4",
                "3.3.1-beallio.11",
                1,
            ),
            (
                "3.3.1-beallio.12",
                "3.3.1-beallio.11.dev.20260808.g1a2b3c4",
                1,
            ),
            (
                "3.3.1-beallio.11.dev.20260809.g9f8e7d6",
                "3.3.1-beallio.11.dev.20260808.g1a2b3c4",
                1,
            ),
            ("3.3.0+beallio.11", "3.3.0+beallio.10", 0),
        )
        for a, b, expected in cases:
            with self.subTest(a=a, b=b):
                self.assertEqual(semver_precedence(a, b), expected)

    def test_manifest_versions_agree(self) -> None:
        self.assertEqual(manifest_version(), "3.3.1-beallio.12")

    def test_manifest_version_carries_no_build_metadata(self) -> None:
        self.assertNotIn(
            "+",
            manifest_version(),
            "Decky's compare-versions ignores build metadata, so a + suffix can never trigger an update.",
        )

    def test_manifest_version_supersedes_every_published_remix_tag(self) -> None:
        version = manifest_version()
        for published in ("3.3.0", "3.3.0+beallio.1", "3.3.0+beallio.10"):
            with self.subTest(published=published):
                self.assertEqual(semver_precedence(version, published), 1)

    def test_derived_nightly_orders_between_this_release_and_the_next(self) -> None:
        version = manifest_version()
        nightly = f"{version}.dev.20260808.g1a2b3c4"
        self.assertEqual(semver_precedence(nightly, version), 1)
        self.assertEqual(semver_precedence("3.3.1-beallio.13", nightly), 1)


if __name__ == "__main__":
    unittest.main()
