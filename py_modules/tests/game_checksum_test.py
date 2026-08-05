from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("DECKY_PLUGIN_RUNTIME_DIR", tempfile.gettempdir())

from py_modules.files import Files
from py_modules.game_resolution.checksum import GameChecksumCoordinator
from py_modules.game_resolution.coordinator import GameResolutionCoordinator
from py_modules.game_resolution.models import BatchResolutionResult, ResolutionResult


def direct_request(payload: Path) -> dict[str, object]:
    path = str(payload)
    shortcut_exe = f'"{path}"' if " " in path else path
    return {
        "launcherKind": "direct",
        "classificationStatus": "recognized",
        "normalized": {
            "flatpakAppId": None,
            "shortcutExe": shortcut_exe,
            "shortcutLaunchOptions": None,
            "shortcutStartDir": None,
            "executableTokens": [path],
            "launchOptionTokens": [],
            "startDirTokens": [],
            "commandTokens": [path],
        },
        "metadataCandidates": [],
    }


class StaticResolver:
    def __init__(self, result: ResolutionResult) -> None:
        self.result = result
        self.entries: list[object] = []

    def resolve_batch(self, entries: object) -> BatchResolutionResult:
        self.entries.append(entries)
        return BatchResolutionResult((self.result,))


class SequencedResolver:
    def __init__(self, results: list[ResolutionResult]) -> None:
        self.results = results

    def resolve_batch(self, _entries: object) -> BatchResolutionResult:
        return BatchResolutionResult((self.results.pop(0),))


class RecordingFiles:
    def __init__(self, checksum: str | None = "digest", error: Exception | None = None):
        self.checksum = checksum
        self.error = error
        self.paths: list[str] = []

    def get_file_sha256(self, path: str) -> str | None:
        self.paths.append(path)
        if self.error is not None:
            raise self.error
        return self.checksum


class GameChecksumCoordinatorTest(unittest.TestCase):
    def test_hashes_only_the_resolver_confirmed_direct_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "Game.exe"
            payload.write_bytes(b"MZ game payload")
            attacker_path = root / "wine"
            attacker_path.write_bytes(b"not the game")

            response = GameChecksumCoordinator(
                GameResolutionCoordinator(), Files()
            ).get_checksum({**direct_request(payload), "filePath": str(attacker_path)})

        self.assertEqual(response.status, "ready")
        self.assertEqual(
            response.checksum,
            hashlib.sha256(b"MZ game payload").hexdigest(),
        )
        self.assertIsNone(response.reason_code)
        self.assertNotIn("payloadPath", response.to_dict())

    def test_revalidates_the_payload_for_every_checksum_after_game_updates(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory) / "Game.exe"
            payload.write_bytes(b"MZ old payload")
            coordinator = GameChecksumCoordinator(GameResolutionCoordinator(), Files())
            old = coordinator.get_checksum(direct_request(payload))

            payload.write_bytes(b"MZ updated payload")
            updated = coordinator.get_checksum(direct_request(payload))

        self.assertEqual(old.status, "ready")
        self.assertEqual(updated.status, "ready")
        self.assertNotEqual(old.checksum, updated.checksum)

    def test_hashes_a_resolved_symlink_target_but_not_a_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "Game.exe"
            payload.write_bytes(b"MZ game payload")
            symlink = root / "Game Link.exe"
            symlink.symlink_to(payload)

            coordinator = GameChecksumCoordinator(GameResolutionCoordinator(), Files())
            linked = coordinator.get_checksum(direct_request(symlink))
            directory_result = coordinator.get_checksum(direct_request(root))

        self.assertEqual(linked.status, "ready")
        self.assertEqual(directory_result.status, "payload_unavailable")
        self.assertEqual(directory_result.reason_code, "kind_mismatch")

    def test_rejects_malformed_and_unsupported_launcher_evidence_without_hashing(
        self,
    ) -> None:
        files = RecordingFiles()
        coordinator = GameChecksumCoordinator(GameResolutionCoordinator(), files)

        malformed = coordinator.get_checksum({"filePath": "/arbitrary/path"})
        unsupported = [
            coordinator.get_checksum(
                {
                    **direct_request(Path("/games/Game.exe")),
                    "launcherKind": launcher_kind,
                }
            )
            for launcher_kind in ("lutris", "bottles", "emudeck-srm")
        ]

        self.assertEqual(malformed.status, "unsupported_shortcut")
        self.assertEqual(malformed.reason_code, "malformed")
        self.assertTrue(
            all(result.status == "unsupported_shortcut" for result in unsupported)
        )
        self.assertTrue(
            all(result.reason_code == "unsupported" for result in unsupported)
        )
        self.assertEqual(files.paths, [])

    def test_maps_resolver_diagnostics_without_exposing_a_payload_path(self) -> None:
        outcomes = {
            "missing_metadata": ResolutionResult(
                "heroic",
                "recognized",
                "not_found",
                "unknown",
                "unknown",
                "none",
                "missing",
                None,
            ),
            "ambiguous": ResolutionResult.unknown("heroic", "ambiguous", "ambiguous"),
            "drive_disconnected": ResolutionResult(
                "direct",
                "recognized",
                "not_requested",
                "unreachable",
                "unknown",
                "direct_executable",
                "drive_disconnected",
                None,
            ),
            "permission_denied": ResolutionResult.unknown(
                "direct", "recognized", "permission_denied"
            ),
            "probe_failure": ResolutionResult.unknown(
                "direct", "recognized", "probe_failure"
            ),
        }

        expected = {
            "missing_metadata": "missing_metadata",
            "ambiguous": "unsupported_shortcut",
            "drive_disconnected": "payload_unavailable",
            "permission_denied": "payload_unavailable",
            "probe_failure": "payload_unavailable",
        }
        for name, result in outcomes.items():
            with self.subTest(name=name):
                files = RecordingFiles()
                response = GameChecksumCoordinator(
                    StaticResolver(result), files
                ).get_checksum(direct_request(Path("/games/Game.exe")))

                self.assertEqual(response.status, expected[name])
                self.assertEqual(response.reason_code, result.reason_code)
                self.assertEqual(files.paths, [])
                self.assertNotIn("payloadPath", response.to_dict())

    def test_resumes_hashing_only_after_the_resolver_confirms_reconnected_payload(
        self,
    ) -> None:
        resolver = SequencedResolver(
            [
                ResolutionResult(
                    "direct",
                    "recognized",
                    "not_requested",
                    "unreachable",
                    "unknown",
                    "direct_executable",
                    "drive_disconnected",
                    None,
                ),
                ResolutionResult(
                    "direct",
                    "recognized",
                    "not_requested",
                    "reachable",
                    "file",
                    "direct_executable",
                    None,
                    "/run/media/deck/SD Card/Games/Game.exe",
                ),
            ]
        )
        files = RecordingFiles()
        coordinator = GameChecksumCoordinator(resolver, files)

        disconnected = coordinator.get_checksum(direct_request(Path("/games/Game.exe")))
        reconnected = coordinator.get_checksum(direct_request(Path("/games/Game.exe")))

        self.assertEqual(disconnected.status, "payload_unavailable")
        self.assertEqual(disconnected.reason_code, "drive_disconnected")
        self.assertEqual(reconnected.status, "ready")
        self.assertEqual(files.paths, ["/run/media/deck/SD Card/Games/Game.exe"])

    def test_hash_failure_is_structured_and_never_returns_a_path(self) -> None:
        result = ResolutionResult(
            "heroic",
            "recognized",
            "resolved",
            "reachable",
            "file",
            "heroic_metadata",
            None,
            "/games/HeroicPayload.exe",
        )
        files = RecordingFiles(error=OSError("hash failed"))

        response = GameChecksumCoordinator(StaticResolver(result), files).get_checksum(
            direct_request(Path("/games/Game.exe"))
        )

        self.assertEqual(response.status, "hash_failure")
        self.assertEqual(response.reason_code, "hash_failure")
        self.assertEqual(files.paths, ["/games/HeroicPayload.exe"])
        self.assertNotIn("payloadPath", response.to_dict())


if __name__ == "__main__":
    unittest.main()
