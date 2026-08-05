import json
import stat
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

from py_modules.game_resolution import FilesystemProbe, GameResolutionCoordinator
from py_modules.game_resolution.filesystem import FilesystemProbeResult
from py_modules.game_resolution import heroic as heroic_module
from py_modules.game_resolution.heroic import HeroicAdapter, HeroicConfigRoots


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "heroic_game_resolution.json"


def load_fixture(root: Path) -> dict[str, object]:
    return json.loads(
        FIXTURE_PATH.read_text(encoding="utf-8").replace("{root}", str(root))
    )


def heroic_entry(
    *,
    executable: str,
    launch_options: tuple[str, ...],
    flatpak_app_id: str | None = None,
) -> dict[str, object]:
    return {
        "launcherKind": "heroic",
        "classificationStatus": "recognized",
        "normalized": {
            "shortcutExe": executable,
            "shortcutLaunchOptions": " ".join(launch_options),
            "shortcutStartDir": None,
            "flatpakAppId": flatpak_app_id,
            "executableTokens": [executable],
            "launchOptionTokens": list(launch_options),
            "startDirTokens": [],
            "commandTokens": [executable, *launch_options],
        },
        "metadataCandidates": [],
    }


class TogglePayloadProbe:
    def __init__(self, payload: Path) -> None:
        self.connected = False
        self.payload = payload

    def probe_regular_file(self, candidate: Path) -> FilesystemProbeResult:
        if not self.connected:
            return FilesystemProbeResult(None, "drive_disconnected")
        return FilesystemProbeResult(
            str(self.payload),
            None,
            stat.S_IRUSR | stat.S_IXUSR,
            b"MZ\x90\x00",
        )


class HeroicGameResolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.heroic_root = self.root / "heroic"
        self.fixtures = load_fixture(self.root)

    @property
    def roots(self) -> HeroicConfigRoots:
        return HeroicConfigRoots(self.heroic_root, self.heroic_root)

    def coordinator(
        self,
        probe: FilesystemProbe | None = None,
        *,
        roots: HeroicConfigRoots | None = None,
        read_text: Callable[[Path], str] | None = None,
    ) -> GameResolutionCoordinator:
        adapter_roots = roots or self.roots
        adapter_probe = probe or FilesystemProbe()
        adapter = (
            HeroicAdapter(adapter_probe, config_roots=adapter_roots)
            if read_text is None
            else HeroicAdapter(
                adapter_probe,
                config_roots=adapter_roots,
                read_text=read_text,
            )
        )
        return GameResolutionCoordinator(adapters=[adapter])

    def write_json(self, relative_path: str, value: object) -> None:
        self.write_json_at(self.heroic_root, relative_path, value)

    @staticmethod
    def write_json_at(root: Path, relative_path: str, value: object) -> None:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def write_payload(
        self, relative_path: str, contents: bytes = b"MZ\x90\x00"
    ) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        return path

    def installed(self) -> dict[str, object]:
        return self.fixtures["metadata"]["legendaryInstalled"]  # type: ignore[index, no-any-return]

    def test_resolves_native_current_uri_to_the_actual_normal_payload(self) -> None:
        shortcut = self.fixtures["shortcuts"]["native_current_query"]  # type: ignore[index]
        self.write_json("legendaryConfig/legendary/installed.json", self.installed())
        payload = self.write_payload("Games/Normal Game/Binaries/NormalGame.exe")

        result = (
            self.coordinator()
            .resolve_batch(
                [
                    heroic_entry(
                        executable=shortcut["shortcutExe"],  # type: ignore[index]
                        launch_options=(shortcut["shortcutLaunchOptions"],),  # type: ignore[index]
                    )
                ]
            )
            .results[0]
        )

        self.assertEqual(result.metadata_status, "resolved")
        self.assertEqual(result.payload_status, "reachable")
        self.assertEqual(result.provenance, "heroic_metadata")
        self.assertEqual(result.payload_path, str(payload))

    def test_resolves_flatpak_legacy_uri_without_returning_the_flatpak_binary(
        self,
    ) -> None:
        shortcut = self.fixtures["shortcuts"]["flatpak_legacy_path"]  # type: ignore[index]
        self.write_json("legendaryConfig/legendary/installed.json", self.installed())
        payload = self.write_payload("Games/Legacy Game/LegacyGame.exe")

        result = (
            self.coordinator()
            .resolve_batch(
                [
                    heroic_entry(
                        executable=shortcut["shortcutExe"],  # type: ignore[index]
                        launch_options=tuple(shortcut["shortcutLaunchOptions"].split()),  # type: ignore[index]
                        flatpak_app_id=shortcut["flatpakAppId"],  # type: ignore[index]
                    )
                ]
            )
            .results[0]
        )

        self.assertEqual(result.payload_status, "reachable")
        self.assertEqual(result.payload_path, str(payload))
        self.assertNotEqual(result.payload_path, "/usr/bin/flatpak")

    def test_native_metadata_does_not_read_an_irrelevant_flatpak_root(self) -> None:
        native_root = self.root / "native-heroic"
        flatpak_root = self.root / "flatpak-heroic"
        self.write_json_at(
            native_root,
            "legendaryConfig/legendary/installed.json",
            self.installed(),
        )
        payload = self.write_payload("Games/Normal Game/Binaries/NormalGame.exe")

        def deny_flatpak(path: Path) -> str:
            if path.is_relative_to(flatpak_root):
                raise PermissionError
            return path.read_text(encoding="utf-8")

        result = (
            self.coordinator(
                roots=HeroicConfigRoots(native_root, flatpak_root),
                read_text=deny_flatpak,
            )
            .resolve_batch(
                [
                    heroic_entry(
                        executable="/opt/Heroic/heroic",
                        launch_options=(
                            "heroic://launch?appName=normal-game&runner=legendary",
                        ),
                    )
                ]
            )
            .results[0]
        )

        self.assertEqual(result.payload_status, "reachable")
        self.assertEqual(result.payload_path, str(payload))

    def test_flatpak_metadata_does_not_fall_back_to_the_native_root(self) -> None:
        native_root = self.root / "native-heroic"
        flatpak_root = self.root / "flatpak-heroic"
        self.write_json_at(
            native_root,
            "legendaryConfig/legendary/installed.json",
            self.installed(),
        )
        shortcut = self.fixtures["shortcuts"]["flatpak_legacy_path"]  # type: ignore[index]

        result = (
            self.coordinator(roots=HeroicConfigRoots(native_root, flatpak_root))
            .resolve_batch(
                [
                    heroic_entry(
                        executable=shortcut["shortcutExe"],  # type: ignore[index]
                        launch_options=tuple(shortcut["shortcutLaunchOptions"].split()),  # type: ignore[index]
                        flatpak_app_id=shortcut["flatpakAppId"],  # type: ignore[index]
                    )
                ]
            )
            .results[0]
        )

        self.assertEqual(result.metadata_status, "not_found")
        self.assertEqual(result.reason_code, "missing")

    def test_sideload_rom_is_resolved_from_library_without_using_heroic_or_prefix(
        self,
    ) -> None:
        shortcut = self.fixtures["shortcuts"]["sideload_query"]  # type: ignore[index]
        sideload_library = self.fixtures["metadata"]["sideloadLibrary"]  # type: ignore[index]
        self.write_json("sideload_apps/library.json", sideload_library)
        payload = self.write_payload("ROMs/rom-game.chd", b"CHD\x00")

        result = (
            self.coordinator()
            .resolve_batch(
                [
                    heroic_entry(
                        executable=shortcut["shortcutExe"],  # type: ignore[index]
                        launch_options=(shortcut["shortcutLaunchOptions"],),  # type: ignore[index]
                    )
                ]
            )
            .results[0]
        )

        self.assertEqual(result.payload_status, "reachable")
        self.assertEqual(result.payload_path, str(payload))
        self.assertNotIn("Prefixes", result.payload_path or "")

    def test_uri_alternate_executable_wins_over_stored_alternate_and_decodes_once_more(
        self,
    ) -> None:
        self.write_json("legendaryConfig/legendary/installed.json", self.installed())
        settings = self.fixtures["metadata"]["settings"]["alternate-game"]  # type: ignore[index]
        self.write_json("GamesConfig/alternate-game.json", {"alternate-game": settings})
        self.write_payload("Games/Alternate Game/Default.exe")
        self.write_payload("Games/Alternate Game/Binaries/StoredAlternate.exe")
        uri_payload = self.write_payload(
            "Games/Alternate Game/Binaries/UriAlternate.exe"
        )
        encoded_uri_payload = quote(quote(str(uri_payload), safe=""), safe="")

        result = (
            self.coordinator()
            .resolve_batch(
                [
                    heroic_entry(
                        executable="/home/deck/Applications/Heroic-2.16.1.AppImage",
                        launch_options=(
                            "heroic://launch?appName=alternate-game&runner=legendary"
                            f"&altExe={encoded_uri_payload}",
                        ),
                    )
                ]
            )
            .results[0]
        )

        self.assertEqual(result.payload_status, "reachable")
        self.assertEqual(result.payload_path, str(uri_payload))

    def test_stored_alternate_executable_is_payload_evidence_but_prefix_is_not(
        self,
    ) -> None:
        shortcut = self.fixtures["shortcuts"]["appimage_current_query"]  # type: ignore[index]
        self.write_json("legendaryConfig/legendary/installed.json", self.installed())
        settings = self.fixtures["metadata"]["settings"]["alternate-game"]  # type: ignore[index]
        self.write_json("GamesConfig/alternate-game.json", {"alternate-game": settings})
        self.write_payload("Games/Alternate Game/Default.exe")
        payload = self.write_payload(
            "Games/Alternate Game/Binaries/StoredAlternate.exe"
        )

        result = (
            self.coordinator()
            .resolve_batch(
                [
                    heroic_entry(
                        executable=shortcut["shortcutExe"],  # type: ignore[index]
                        launch_options=(shortcut["shortcutLaunchOptions"],),  # type: ignore[index]
                    )
                ]
            )
            .results[0]
        )

        self.assertEqual(result.payload_status, "reachable")
        self.assertEqual(result.payload_path, str(payload))

    def test_runnerless_duplicate_metadata_is_ambiguous_but_runner_disambiguates(
        self,
    ) -> None:
        self.write_json("legendaryConfig/legendary/installed.json", self.installed())
        self.write_json(
            "gog_store/installed.json",
            {
                "installed": [
                    {
                        "appName": "normal-game",
                        "install_path": str(self.root / "Gog"),
                        "executable": "GogGame.exe",
                    }
                ]
            },
        )
        payload = self.write_payload("Games/Normal Game/Binaries/NormalGame.exe")

        ambiguous = (
            self.coordinator()
            .resolve_batch(
                [
                    heroic_entry(
                        executable="/opt/Heroic/heroic",
                        launch_options=("heroic://launch?appName=normal-game",),
                    )
                ]
            )
            .results[0]
        )
        resolved = (
            self.coordinator()
            .resolve_batch(
                [
                    heroic_entry(
                        executable="/opt/Heroic/heroic",
                        launch_options=(
                            "heroic://launch?appName=normal-game&runner=legendary",
                        ),
                    )
                ]
            )
            .results[0]
        )

        self.assertEqual(ambiguous.metadata_status, "resolved")
        self.assertEqual(ambiguous.reason_code, "ambiguous")
        self.assertEqual(resolved.payload_path, str(payload))

    def test_malformed_metadata_traversal_and_permission_fail_closed(self) -> None:
        entry = heroic_entry(
            executable="/opt/Heroic/heroic",
            launch_options=("heroic://launch?appName=normal-game&runner=legendary",),
        )
        missing = self.coordinator().resolve_batch([entry]).results[0]
        malformed_path = self.heroic_root / "legendaryConfig/legendary/installed.json"
        malformed_path.parent.mkdir(parents=True)
        malformed_path.write_text("{", encoding="utf-8")
        malformed = self.coordinator().resolve_batch([entry]).results[0]

        traversal = (
            self.coordinator()
            .resolve_batch(
                [
                    heroic_entry(
                        executable="/opt/Heroic/heroic",
                        launch_options=(
                            "heroic://launch?appName=..%2Fescape&runner=legendary",
                        ),
                    )
                ]
            )
            .results[0]
        )

        def deny_read(_: Path) -> str:
            raise PermissionError

        denied = (
            GameResolutionCoordinator(
                adapters=[
                    HeroicAdapter(
                        FilesystemProbe(), config_roots=self.roots, read_text=deny_read
                    )
                ]
            )
            .resolve_batch([entry])
            .results[0]
        )

        self.assertEqual(missing.metadata_status, "not_found")
        self.assertEqual(malformed.metadata_status, "invalid")
        self.assertEqual(malformed.reason_code, "malformed")
        self.assertEqual(traversal.reason_code, "malformed")
        self.assertEqual(denied.reason_code, "permission_denied")

    def test_multiple_payload_candidates_for_one_runner_are_ambiguous(self) -> None:
        self.write_json(
            "gog_store/installed.json",
            {
                "installed": [
                    {
                        "appName": "normal-game",
                        "install_path": str(self.root / "Gog One"),
                        "executable": "Game.exe",
                    },
                    {
                        "appName": "normal-game",
                        "install_path": str(self.root / "Gog Two"),
                        "executable": "Game.exe",
                    },
                ]
            },
        )

        result = (
            self.coordinator()
            .resolve_batch(
                [
                    heroic_entry(
                        executable="/opt/Heroic/heroic",
                        launch_options=(
                            "heroic://launch?appName=normal-game&runner=gog",
                        ),
                    )
                ]
            )
            .results[0]
        )

        self.assertEqual(result.metadata_status, "resolved")
        self.assertEqual(result.reason_code, "ambiguous")

    def test_identical_metadata_records_are_deduplicated(self) -> None:
        payload = self.write_payload("Gog/Game.exe")
        record = {
            "appName": "normal-game",
            "install_path": str(self.root / "Gog"),
            "executable": "Game.exe",
        }
        self.write_json("gog_store/installed.json", {"installed": [record, record]})

        result = (
            self.coordinator()
            .resolve_batch(
                [
                    heroic_entry(
                        executable="/opt/Heroic/heroic",
                        launch_options=(
                            "heroic://launch?appName=normal-game&runner=gog",
                        ),
                    )
                ]
            )
            .results[0]
        )

        self.assertEqual(result.payload_status, "reachable")
        self.assertEqual(result.payload_path, str(payload))

    def test_conflicting_metadata_identity_aliases_and_runner_are_ambiguous(
        self,
    ) -> None:
        entry = heroic_entry(
            executable="/opt/Heroic/heroic",
            launch_options=("heroic://launch?appName=normal-game&runner=legendary",),
        )
        conflicts = (
            {"appName": "different-game"},
            {"appID": "different-game"},
            {"runner": "gog"},
            {"source": "gog"},
        )
        for conflict in conflicts:
            with self.subTest(conflict=conflict):
                record = dict(self.installed()["normal-game"])  # type: ignore[index]
                record.update(conflict)
                self.write_json(
                    "legendaryConfig/legendary/installed.json",
                    {"normal-game": record},
                )

                result = self.coordinator().resolve_batch([entry]).results[0]

                self.assertEqual(result.metadata_status, "invalid")
                self.assertEqual(result.reason_code, "ambiguous")

        self.write_json(
            "legendaryConfig/legendary/installed.json",
            {"different-key": self.installed()["normal-game"]},  # type: ignore[index]
        )
        mapping_key_conflict = self.coordinator().resolve_batch([entry]).results[0]

        self.assertEqual(mapping_key_conflict.metadata_status, "invalid")
        self.assertEqual(mapping_key_conflict.reason_code, "ambiguous")

    def test_metadata_resource_bounds_fail_closed(self) -> None:
        entry = heroic_entry(
            executable="/opt/Heroic/heroic",
            launch_options=("heroic://launch?appName=normal-game&runner=gog",),
        )
        oversized_path = self.heroic_root / "gog_store/installed.json"
        oversized_path.parent.mkdir(parents=True, exist_ok=True)
        oversized_path.write_text(
            json.dumps("x" * (heroic_module._MAX_METADATA_BYTES + 1)),
            encoding="utf-8",
        )
        oversized = self.coordinator().resolve_batch([entry]).results[0]

        nested: object = {}
        for _ in range(heroic_module._MAX_METADATA_JSON_DEPTH + 1):
            nested = {"next": nested}
        self.write_json("gog_store/installed.json", nested)
        too_deep = self.coordinator().resolve_batch([entry]).results[0]

        self.write_json(
            "gog_store/installed.json",
            {
                "installed": [
                    {"appName": f"other-{index}"}
                    for index in range(heroic_module._MAX_METADATA_RECORDS + 1)
                ]
            },
        )
        too_many_records = self.coordinator().resolve_batch([entry]).results[0]

        self.write_json(
            "gog_store/installed.json",
            {
                "installed": [
                    {
                        "appName": "normal-game",
                        "install_path": str(self.root / f"Gog {index}"),
                        "executable": "Game.exe",
                    }
                    for index in range(heroic_module.MAX_METADATA_CANDIDATES + 1)
                ]
            },
        )
        too_many_candidates = self.coordinator().resolve_batch([entry]).results[0]

        self.write_json(
            "gog_store/installed.json",
            {
                "installed": [
                    {
                        "appName": "normal-game",
                        "install_path": str(self.root / "Gog"),
                        "executable": "Game.exe",
                        "title": "x" * (heroic_module._MAX_METADATA_FIELD_LENGTH + 1),
                    }
                ]
            },
        )
        oversized_field = self.coordinator().resolve_batch([entry]).results[0]

        for result in (
            oversized,
            too_deep,
            too_many_records,
            too_many_candidates,
            oversized_field,
        ):
            with self.subTest(result=result):
                self.assertEqual(result.metadata_status, "invalid")
                self.assertEqual(result.payload_status, "unknown")
                self.assertEqual(result.reason_code, "malformed")

    def test_launcher_metadata_can_survive_missing_and_disconnected_payloads(
        self,
    ) -> None:
        self.write_json("legendaryConfig/legendary/installed.json", self.installed())
        entry = heroic_entry(
            executable="/opt/Heroic/heroic",
            launch_options=("heroic://launch?appName=normal-game&runner=legendary",),
        )
        missing = self.coordinator().resolve_batch([entry]).results[0]

        payload = self.write_payload("Games/Normal Game/Binaries/NormalGame.exe")
        toggle_probe = TogglePayloadProbe(payload)
        coordinator = GameResolutionCoordinator(
            adapters=[HeroicAdapter(toggle_probe, config_roots=self.roots)]
        )
        disconnected = coordinator.resolve_batch([entry]).results[0]
        toggle_probe.connected = True
        reconnected = coordinator.resolve_batch([entry]).results[0]

        self.assertEqual(missing.metadata_status, "resolved")
        self.assertEqual(missing.reason_code, "payload_missing")
        self.assertEqual(disconnected.reason_code, "drive_disconnected")
        self.assertEqual(reconnected.payload_status, "reachable")
        self.assertEqual(reconnected.payload_path, str(payload))

    def test_default_registry_includes_heroic_and_rejects_unverified_custom_roots(
        self,
    ) -> None:
        entry = heroic_entry(
            executable="/opt/Heroic/heroic",
            launch_options=("heroic://launch?appName=normal-game&runner=legendary",),
        )

        custom_entry = {**entry, "metadataCandidates": ["custom-root"]}
        result = GameResolutionCoordinator().resolve_batch([custom_entry]).results[0]
        custom_root = self.coordinator().resolve_batch([custom_entry]).results[0]

        self.assertEqual(result.launcher_kind, "heroic")
        self.assertEqual(result.reason_code, "malformed")
        self.assertEqual(custom_root.reason_code, "malformed")


if __name__ == "__main__":
    unittest.main()
