"""End-to-end resolver fences for confirmed game-parent groups."""

from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from py_modules.db.dao import Dao
from py_modules.db.migration import DbMigration
from py_modules.game_resolution import (
    DirectExecutableAdapter,
    GameResolutionCoordinator,
)
from py_modules.game_resolution.checksum import GameChecksumCoordinator
from py_modules.game_resolution.filesystem import FilesystemProbeResult
from py_modules.game_resolution.heroic import HeroicAdapter, HeroicConfigRoots
from py_modules.game_resolution.models import ResolutionRequest
from py_modules.game_resolution.steam_shortcuts import ShortcutCatalogOutcome
from py_modules.tests.helpers import AbstractDatabaseTest


FIXTURES = Path(__file__).parent / "fixtures"
DIRECT_FIXTURE_PATH = FIXTURES / "direct_game_resolution.json"
HEROIC_FIXTURE_PATH = FIXTURES / "heroic_game_resolution.json"


class TogglePayloadProbe:
    """Model a removable volume without bypassing the real resolver adapters."""

    def __init__(self, payload: Path) -> None:
        self.connected = False
        self.payload = payload
        self.probed_paths: list[Path] = []

    def probe_regular_file(self, candidate: Path) -> FilesystemProbeResult:
        self.probed_paths.append(candidate)
        if not self.connected:
            return FilesystemProbeResult(None, "drive_disconnected")
        if candidate != self.payload or not candidate.is_file():
            return FilesystemProbeResult(None, "payload_missing")
        return FilesystemProbeResult(
            str(candidate),
            None,
            candidate.stat().st_mode,
            candidate.read_bytes()[:4],
        )


class RecordingHasher:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def get_file_sha256(self, path: str) -> str:
        self.paths.append(path)
        return "fixture-digest"


class FixtureShortcutSource:
    def __init__(self, app_id: int, request: ResolutionRequest) -> None:
        self.app_id = app_id
        self.request = request

    def get_request(self, app_id: int) -> ShortcutCatalogOutcome:
        if app_id != self.app_id:
            return ShortcutCatalogOutcome(None, "missing")
        return ShortcutCatalogOutcome(self.request)


class GameParentIntegrationTest(AbstractDatabaseTest):
    def setUp(self) -> None:
        super().setUp()
        DbMigration(db=self.database).migrate()
        self.dao = Dao(self.database)

    def _assert_disconnect_sequence(
        self,
        *,
        app_id: int,
        child_id: str,
        request: ResolutionRequest,
        coordinator: GameResolutionCoordinator,
        probe: TogglePayloadProbe,
        payload: Path,
    ) -> None:
        self.dao.save_game_dict(
            "explicit-zero-time-parent", "Explicit Zero-Time Parent"
        )
        self.dao.save_game_dict(child_id, "Shortcut Child")
        self.dao.create_game_association("explicit-zero-time-parent", child_id)
        associations_before = self.dao.get_all_game_associations()
        checksums_before = self.dao.get_games_checksum()

        disconnected_refresh = coordinator.resolve_batch([request.to_dict()]).results[0]
        self.assertEqual(disconnected_refresh.reason_code, "drive_disconnected")
        self.assertEqual(disconnected_refresh.payload_status, "unreachable")
        self.assertEqual(
            self.dao.get_game_identity_components()[child_id].canonical_id,
            "explicit-zero-time-parent",
        )
        self.assertEqual(self.dao.get_all_game_associations(), associations_before)
        self.assertEqual(self.dao.get_games_checksum(), checksums_before)

        hasher = RecordingHasher()
        checksums = GameChecksumCoordinator(
            coordinator, hasher, FixtureShortcutSource(app_id, request)
        )
        disconnected_checksum = checksums.get_checksum({"appId": app_id})
        self.assertEqual(disconnected_checksum.status, "payload_unavailable")
        self.assertEqual(disconnected_checksum.reason_code, "drive_disconnected")
        self.assertEqual(hasher.paths, [])

        probe.connected = True
        reconnected_refresh = coordinator.resolve_batch([request.to_dict()]).results[0]
        self.assertEqual(reconnected_refresh.payload_status, "reachable")
        self.assertEqual(reconnected_refresh.payload_kind, "file")
        self.assertEqual(reconnected_refresh.payload_path, str(payload))
        self.assertEqual(self.dao.get_all_game_associations(), associations_before)
        self.assertEqual(self.dao.get_games_checksum(), checksums_before)

        reconnected_checksum = checksums.get_checksum({"appId": app_id})
        self.assertEqual(reconnected_checksum.status, "ready")
        self.assertEqual(reconnected_checksum.checksum, "fixture-digest")
        self.assertEqual(hasher.paths, [str(payload)])

    def test_direct_fixture_refresh_and_checksum_preserve_confirmed_parent(
        self,
    ) -> None:
        fixture = json.loads(DIRECT_FIXTURE_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / fixture["payloadRelativePath"]
            payload.parent.mkdir(parents=True)
            payload.write_bytes(b"MZ\x90\x00 direct fixture")
            payload.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            request = ResolutionRequest.from_mapping(
                json.loads(
                    json.dumps(fixture["shortcut"]).replace("{payload}", str(payload))
                )
            )
            probe = TogglePayloadProbe(payload)
            coordinator = GameResolutionCoordinator(
                adapters=[DirectExecutableAdapter(probe)]
            )

            self._assert_disconnect_sequence(
                app_id=2_147_483_650,
                child_id="direct-shortcut-child",
                request=request,
                coordinator=coordinator,
                probe=probe,
                payload=payload,
            )

    def test_heroic_fixture_refresh_and_checksum_preserve_confirmed_parent(
        self,
    ) -> None:
        fixture = json.loads(HEROIC_FIXTURE_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            heroic_root = root / "heroic"
            metadata = fixture["metadata"]["legendaryInstalled"]
            metadata_path = heroic_root / "legendaryConfig/legendary/installed.json"
            metadata_path.parent.mkdir(parents=True)
            metadata_path.write_text(
                json.dumps(metadata).replace("{root}", str(root)), encoding="utf-8"
            )
            payload = root / "Games/Normal Game/Binaries/NormalGame.exe"
            payload.parent.mkdir(parents=True)
            payload.write_bytes(b"MZ\x90\x00 heroic fixture")
            payload.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            shortcut = fixture["shortcuts"]["native_current_query"]
            request = ResolutionRequest.from_mapping(
                {
                    "launcherKind": "heroic",
                    "classificationStatus": "recognized",
                    "normalized": {
                        "flatpakAppId": None,
                        "shortcutExe": shortcut["shortcutExe"],
                        "shortcutLaunchOptions": shortcut["shortcutLaunchOptions"],
                        "shortcutStartDir": None,
                        "executableTokens": [shortcut["shortcutExe"]],
                        "launchOptionTokens": [shortcut["shortcutLaunchOptions"]],
                        "startDirTokens": [],
                        "commandTokens": [
                            shortcut["shortcutExe"],
                            shortcut["shortcutLaunchOptions"],
                        ],
                    },
                    "metadataCandidates": [],
                }
            )
            probe = TogglePayloadProbe(payload)
            coordinator = GameResolutionCoordinator(
                adapters=[
                    HeroicAdapter(
                        probe,
                        config_roots=HeroicConfigRoots(heroic_root, heroic_root),
                    )
                ]
            )

            self._assert_disconnect_sequence(
                app_id=2_147_483_651,
                child_id="heroic-shortcut-child",
                request=request,
                coordinator=coordinator,
                probe=probe,
                payload=payload,
            )


if __name__ == "__main__":
    unittest.main()
