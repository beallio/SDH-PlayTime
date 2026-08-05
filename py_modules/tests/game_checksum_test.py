from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("DECKY_PLUGIN_RUNTIME_DIR", tempfile.gettempdir())

from py_modules.files import Files
from py_modules.game_resolution.checksum import GameChecksumCoordinator
from py_modules.game_resolution.coordinator import GameResolutionCoordinator
from py_modules.game_resolution.filesystem import FilesystemProbe
from py_modules.game_resolution.heroic import HeroicAdapter, HeroicConfigRoots
from py_modules.game_resolution.models import (
    BatchResolutionResult,
    ResolutionRequest,
    ResolutionResult,
)
from py_modules.game_resolution.steam_shortcuts import (
    ShortcutCatalogOutcome,
    SteamShortcutCatalog,
    shortcut_app_id,
)


def direct_request(payload: Path) -> ResolutionRequest:
    path = str(payload)
    shortcut_exe = f'"{path}"' if " " in path else path
    return ResolutionRequest.from_mapping(
        {
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
        },
    )


def checksum_request(app_id: int = 1) -> dict[str, int]:
    return {"appId": app_id}


class StaticShortcutSource:
    def __init__(
        self,
        request: ResolutionRequest | None,
        accepted_app_ids: set[int] | None = None,
    ) -> None:
        self.request = request
        self.accepted_app_ids = accepted_app_ids or {1}
        self.app_ids: list[int] = []

    def get_request(self, app_id: int) -> ShortcutCatalogOutcome:
        self.app_ids.append(app_id)
        if app_id not in self.accepted_app_ids:
            return ShortcutCatalogOutcome(None, "missing")
        return ShortcutCatalogOutcome(self.request, None if self.request else "missing")


def write_shortcuts(path: Path, entries: list[dict[str, str | int]]) -> None:
    def string(key: str, value: str) -> bytes:
        return b"\x01" + key.encode() + b"\x00" + value.encode() + b"\x00"

    def integer(key: str, value: int) -> bytes:
        return (
            b"\x02" + key.encode() + b"\x00" + value.to_bytes(4, "little", signed=True)
        )

    contents = bytearray(b"\x00shortcuts\x00")
    for index, entry in enumerate(entries):
        contents.extend(b"\x00" + str(index).encode() + b"\x00")
        fields = dict(entry)
        if "appid" not in fields:
            executable = fields.get("exe")
            app_name = fields.get("appname")
            assert isinstance(executable, str)
            assert isinstance(app_name, str)
            app_id = shortcut_app_id(executable, app_name)
            fields["appid"] = app_id - 0x100000000
        for key, value in fields.items():
            if isinstance(value, int):
                contents.extend(integer(key, value))
            else:
                contents.extend(string(key, value))
        contents.extend(b"\x08")
    contents.extend(b"\x08\x08")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)


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
    def test_hashes_only_the_backend_bound_shortcut_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "Game.exe"
            payload.write_bytes(b"MZ game payload")
            app_name = "Verified Game"
            executable = str(payload)
            app_id = shortcut_app_id(executable, app_name)
            user_home = root / "home"
            write_shortcuts(
                user_home / ".local/share/Steam/userdata/123/config/shortcuts.vdf",
                [{"appname": app_name, "exe": executable}],
            )

            response = GameChecksumCoordinator(
                GameResolutionCoordinator(),
                Files(),
                SteamShortcutCatalog(user_home, lambda: "123"),
            ).get_checksum(checksum_request(app_id))

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
            coordinator = GameChecksumCoordinator(
                GameResolutionCoordinator(),
                Files(),
                StaticShortcutSource(direct_request(payload)),
            )
            old = coordinator.get_checksum(checksum_request())

            payload.write_bytes(b"MZ updated payload")
            updated = coordinator.get_checksum(checksum_request())

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

            linked = GameChecksumCoordinator(
                GameResolutionCoordinator(),
                Files(),
                StaticShortcutSource(direct_request(symlink)),
            ).get_checksum(checksum_request())
            directory_result = GameChecksumCoordinator(
                GameResolutionCoordinator(),
                Files(),
                StaticShortcutSource(direct_request(root)),
            ).get_checksum(checksum_request())

        self.assertEqual(linked.status, "ready")
        self.assertEqual(directory_result.status, "payload_unavailable")
        self.assertEqual(directory_result.reason_code, "kind_mismatch")

    def test_rejects_forged_or_unbound_checksum_requests_without_hashing(self) -> None:
        files = RecordingFiles()
        verified = Path("/games/Verified.exe")
        coordinator = GameChecksumCoordinator(
            GameResolutionCoordinator(),
            files,
            StaticShortcutSource(direct_request(verified)),
        )
        arbitrary = "/games/Attacker.exe"
        forged_normalized = {
            "flatpakAppId": None,
            "shortcutExe": arbitrary,
            "shortcutLaunchOptions": None,
            "shortcutStartDir": None,
            "executableTokens": [arbitrary],
            "launchOptionTokens": [],
            "startDirTokens": [],
            "commandTokens": [arbitrary],
        }
        rejected = [
            coordinator.get_checksum({"filePath": arbitrary}),
            coordinator.get_checksum(
                {
                    "appId": 1,
                    "launcherKind": "direct",
                    "classificationStatus": "recognized",
                    "normalized": forged_normalized,
                    "metadataCandidates": [],
                }
            ),
            coordinator.get_checksum({"appId": 2}),
            coordinator.get_checksum(
                {"appId": 1, "shortcutIdentity": "unrelated-shortcut"}
            ),
            coordinator.get_checksum({"appId": 1, "payloadPath": arbitrary}),
        ]

        self.assertTrue(all(result.checksum is None for result in rejected))
        self.assertTrue(
            all(result.status == "unsupported_shortcut" for result in rejected)
        )
        self.assertEqual(files.paths, [])

    def test_ambiguous_catalog_records_do_not_reach_resolver_or_hasher(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            user_home = root / "home"
            executable = "/games/Verified Game.exe"
            app_name = "Verified Game"
            write_shortcuts(
                user_home / ".local/share/Steam/userdata/123/config/shortcuts.vdf",
                [
                    {"appname": app_name, "exe": executable},
                    {
                        "appname": app_name,
                        "exe": executable,
                        "launchoptions": "--alternate-launch-data",
                    },
                ],
            )
            resolver = StaticResolver(ResolutionResult.unknown())
            files = RecordingFiles()
            response = GameChecksumCoordinator(
                resolver,
                files,
                SteamShortcutCatalog(user_home, lambda: "123"),
            ).get_checksum(checksum_request(shortcut_app_id(executable, app_name)))

        self.assertIsNone(response.checksum)
        self.assertEqual(response.status, "unsupported_shortcut")
        self.assertEqual(response.reason_code, "ambiguous")
        self.assertEqual(resolver.entries, [])
        self.assertEqual(files.paths, [])

    def test_unsupported_sources_fail_closed_without_hashing(self) -> None:
        files = RecordingFiles()
        for launcher_kind in ("lutris", "bottles", "emudeck-srm"):
            with self.subTest(launcher_kind=launcher_kind):
                request = ResolutionRequest.from_mapping(
                    {
                        "launcherKind": launcher_kind,
                        "classificationStatus": "recognized",
                        "normalized": {
                            "flatpakAppId": None,
                            "shortcutExe": "/games/Game.exe",
                            "shortcutLaunchOptions": None,
                            "shortcutStartDir": None,
                            "executableTokens": ["/games/Game.exe"],
                            "launchOptionTokens": [],
                            "startDirTokens": [],
                            "commandTokens": ["/games/Game.exe"],
                        },
                        "metadataCandidates": [],
                    }
                )
                result = GameChecksumCoordinator(
                    GameResolutionCoordinator(), files, StaticShortcutSource(request)
                ).get_checksum(checksum_request())
                self.assertEqual(result.status, "unsupported_shortcut")
                self.assertEqual(result.reason_code, "unsupported")
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
                    StaticResolver(result),
                    files,
                    StaticShortcutSource(direct_request(Path("/games/Game.exe"))),
                ).get_checksum(checksum_request())

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
        coordinator = GameChecksumCoordinator(
            resolver,
            files,
            StaticShortcutSource(direct_request(Path("/games/Game.exe"))),
        )

        disconnected = coordinator.get_checksum(checksum_request())
        reconnected = coordinator.get_checksum(checksum_request())

        self.assertEqual(disconnected.status, "payload_unavailable")
        self.assertEqual(disconnected.reason_code, "drive_disconnected")
        self.assertEqual(reconnected.status, "ready")
        self.assertEqual(files.paths, ["/run/media/deck/SD Card/Games/Game.exe"])

    def test_hashes_reachable_heroic_metadata_and_rejects_ambiguous_metadata(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            user_home = root / "home"
            heroic_root = root / "heroic"
            payload = root / "Games/Normal Game/Binaries/NormalGame.exe"
            payload.parent.mkdir(parents=True)
            payload.write_bytes(b"MZ Heroic payload")
            installed = {
                "normal-game": {
                    "app_name": "normal-game",
                    "install_path": str(payload.parents[1]),
                    "executable": "Binaries/NormalGame.exe",
                }
            }
            installed_path = heroic_root / "legendaryConfig/legendary/installed.json"
            installed_path.parent.mkdir(parents=True)
            installed_path.write_text(json.dumps(installed), encoding="utf-8")
            (heroic_root / "gog_store").mkdir()
            (heroic_root / "gog_store/installed.json").write_text(
                json.dumps(
                    {
                        "installed": [
                            {
                                "appName": "normal-game",
                                "install_path": str(root / "Gog Game"),
                                "executable": "GogGame.exe",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            resolved_executable = "/opt/Heroic/heroic"
            resolved_options = "heroic://launch?appName=normal-game&runner=legendary"
            ambiguous_options = "heroic://launch?appName=normal-game"
            resolved_name = "Heroic Resolved"
            ambiguous_name = "Heroic Ambiguous"
            write_shortcuts(
                user_home / ".local/share/Steam/userdata/123/config/shortcuts.vdf",
                [
                    {
                        "appname": resolved_name,
                        "exe": resolved_executable,
                        "launchoptions": resolved_options,
                    },
                    {
                        "appname": ambiguous_name,
                        "exe": resolved_executable,
                        "launchoptions": ambiguous_options,
                    },
                ],
            )
            source = SteamShortcutCatalog(user_home, lambda: "123")
            files = RecordingFiles(checksum="heroic-digest")
            coordinator = GameChecksumCoordinator(
                GameResolutionCoordinator(
                    adapters=[
                        HeroicAdapter(
                            FilesystemProbe(),
                            config_roots=HeroicConfigRoots(heroic_root, heroic_root),
                        )
                    ]
                ),
                files,
                source,
            )
            resolved = coordinator.get_checksum(
                checksum_request(shortcut_app_id(resolved_executable, resolved_name))
            )
            ambiguous = coordinator.get_checksum(
                checksum_request(shortcut_app_id(resolved_executable, ambiguous_name))
            )

        self.assertEqual(resolved.status, "ready")
        self.assertEqual(resolved.checksum, "heroic-digest")
        self.assertEqual(ambiguous.status, "unsupported_shortcut")
        self.assertEqual(ambiguous.reason_code, "ambiguous")
        self.assertEqual(files.paths, [str(payload)])

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
        response = GameChecksumCoordinator(
            StaticResolver(result),
            files,
            StaticShortcutSource(direct_request(Path("/games/Game.exe"))),
        ).get_checksum(checksum_request())

        self.assertEqual(response.status, "hash_failure")
        self.assertEqual(response.reason_code, "hash_failure")
        self.assertEqual(files.paths, ["/games/HeroicPayload.exe"])
        self.assertNotIn("payloadPath", response.to_dict())


if __name__ == "__main__":
    unittest.main()
