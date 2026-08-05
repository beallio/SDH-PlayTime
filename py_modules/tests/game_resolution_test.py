import os
import stat
import tempfile
import threading
import unittest
from pathlib import Path

from py_modules.game_resolution import (
    DirectExecutableAdapter,
    FilesystemProbe,
    GameResolutionCoordinator,
    MountEntry,
    MAX_RESOLUTION_BATCH_SIZE,
)
from py_modules.game_resolution.models import ResolutionRequest, ResolutionResult


def direct_entry(path: str, **overrides: object) -> dict[str, object]:
    normalized = {
        "shortcutExe": f'"{path}"' if " " in path else path,
        "shortcutLaunchOptions": None,
        "shortcutStartDir": None,
        "flatpakAppId": None,
        "executableTokens": [path],
        "launchOptionTokens": [],
        "startDirTokens": [],
        "commandTokens": [path],
    }
    entry: dict[str, object] = {
        "launcherKind": "direct",
        "classificationStatus": "recognized",
        "normalized": normalized,
        "metadataCandidates": [],
    }
    entry.update(overrides)
    return entry


class GameResolutionCoordinatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def coordinator(
        self, probe: FilesystemProbe | None = None
    ) -> GameResolutionCoordinator:
        return GameResolutionCoordinator(
            adapters=[DirectExecutableAdapter(probe or FilesystemProbe())]
        )

    def test_resolves_regular_native_appimage_and_windows_payload_files(self) -> None:
        coordinator = self.coordinator()
        payloads = [
            self.root / "NativeGame",
            self.root / "Space Game.AppImage",
            self.root / "WindowsGame.exe",
        ]
        for payload in payloads:
            payload.write_bytes(
                b"MZ" if payload.suffix.casefold() == ".exe" else b"\x7fELF"
            )
        for payload in payloads[:2]:
            payload.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

        result = coordinator.resolve_batch(
            [direct_entry(str(path)) for path in payloads]
        )

        self.assertIsNone(result.error)
        self.assertEqual(
            [item.payload_status for item in result.results], ["reachable"] * 3
        )
        self.assertEqual([item.payload_kind for item in result.results], ["file"] * 3)
        self.assertEqual(
            [item.payload_path for item in result.results],
            [str(path) for path in payloads],
        )
        self.assertEqual(
            [item.provenance for item in result.results],
            ["direct_executable"] * 3,
        )

    def test_resolves_a_safe_symlink_to_its_actual_payload(self) -> None:
        target = self.root / "Games" / "Game.exe"
        target.parent.mkdir()
        target.write_bytes(b"MZ")
        link = self.root / "GameLink.exe"
        link.symlink_to(target)

        result = self.coordinator().resolve_batch([direct_entry(str(link))]).results[0]

        self.assertEqual(result.payload_status, "reachable")
        self.assertEqual(result.payload_path, str(target.resolve()))

    def test_rejects_shared_runner_without_probing_a_payload(self) -> None:
        def unexpected_stat(_: Path) -> os.stat_result:
            self.fail("shared runners must not reach the filesystem probe")

        probe = FilesystemProbe(stat_func=unexpected_stat)
        result = (
            self.coordinator(probe)
            .resolve_batch([direct_entry("/usr/bin/wine")])
            .results[0]
        )

        self.assertEqual(result.payload_status, "unknown")
        self.assertEqual(result.reason_code, "unsupported")

    def test_rejects_shell_fragments_and_metadata_traversal_without_probing(
        self,
    ) -> None:
        def unexpected_stat(_: Path) -> os.stat_result:
            self.fail("malformed input must not reach the filesystem probe")

        coordinator = self.coordinator(FilesystemProbe(stat_func=unexpected_stat))
        shell_result = coordinator.resolve_batch(
            [direct_entry("/games/Game.exe; /usr/bin/id")]
        ).results[0]
        traversal_result = coordinator.resolve_batch(
            [direct_entry("/games/Game.exe", metadataCandidates=["../../private"])]
        ).results[0]

        self.assertEqual(shell_result.reason_code, "malformed")
        self.assertEqual(traversal_result.reason_code, "malformed")

    def test_rejects_backend_shell_syntax_and_data_files_before_probing(self) -> None:
        def unexpected_stat(_: Path) -> os.stat_result:
            self.fail("untrusted non-payload candidates must not reach the probe")

        coordinator = self.coordinator(FilesystemProbe(stat_func=unexpected_stat))
        malformed_paths = (
            "/games/%GAME%.exe",
            "/games/@(Game.exe)",
            "/games/+(Game.exe)",
            "/games/!(Game.exe)",
            "/games/Game.exe; /usr/bin/id",
        )
        for path in malformed_paths:
            with self.subTest(path=path):
                result = coordinator.resolve_batch([direct_entry(path)]).results[0]
                self.assertEqual(result.payload_status, "unknown")
                self.assertEqual(result.reason_code, "malformed")

        data_file = coordinator.resolve_batch(
            [direct_entry("/games/notes.txt")]
        ).results[0]
        self.assertEqual(data_file.payload_status, "unknown")
        self.assertEqual(data_file.reason_code, "unsupported")

    def test_rejects_renamed_data_files_without_executable_format_evidence(
        self,
    ) -> None:
        data_file = self.root / "notes.exe"
        data_file.write_text("plain text, not a Windows executable")

        result = self.coordinator().resolve_batch([direct_entry(str(data_file))])
        item = result.results[0]

        self.assertEqual(item.payload_status, "unknown")
        self.assertEqual(item.reason_code, "unsupported")

    def test_rejects_flatpak_claims_that_try_to_pose_as_direct_payloads(self) -> None:
        def unexpected_stat(_: Path) -> os.stat_result:
            self.fail(
                "a Flatpak launcher signature must not reach the filesystem probe"
            )

        entry = direct_entry("/games/Game.exe")
        normalized = entry["normalized"]
        assert isinstance(normalized, dict)
        normalized["flatpakAppId"] = "com.example.Launcher"

        result = (
            self.coordinator(FilesystemProbe(stat_func=unexpected_stat))
            .resolve_batch([entry])
            .results[0]
        )

        self.assertEqual(result.reason_code, "malformed")

    def test_rejects_malformed_start_directories_without_probing(self) -> None:
        def unexpected_stat(_: Path) -> os.stat_result:
            self.fail("malformed path syntax must not reach the filesystem probe")

        entry = direct_entry("/games/Game.exe")
        normalized = entry["normalized"]
        assert isinstance(normalized, dict)
        normalized["shortcutStartDir"] = "$(pwd)"
        normalized["startDirTokens"] = ["$(pwd)"]

        result = (
            self.coordinator(FilesystemProbe(stat_func=unexpected_stat))
            .resolve_batch([entry])
            .results[0]
        )

        self.assertEqual(result.reason_code, "malformed")

    def test_distinguishes_directory_missing_permission_and_probe_failures(
        self,
    ) -> None:
        directory = self.root / "NotAFile"
        directory.mkdir()
        mismatch = (
            self.coordinator().resolve_batch([direct_entry(str(directory))]).results[0]
        )

        def denied(_: Path) -> os.stat_result:
            raise PermissionError()

        def broken(_: Path) -> os.stat_result:
            raise OSError("unexpected filesystem problem")

        permission = (
            self.coordinator(FilesystemProbe(stat_func=denied))
            .resolve_batch([direct_entry("/games/Game.exe")])
            .results[0]
        )
        failure = (
            self.coordinator(FilesystemProbe(stat_func=broken))
            .resolve_batch([direct_entry("/games/Game.exe")])
            .results[0]
        )

        self.assertEqual(mismatch.reason_code, "kind_mismatch")
        self.assertEqual(permission.reason_code, "permission_denied")
        self.assertEqual(failure.reason_code, "probe_failure")
        self.assertEqual(mismatch.payload_status, "unreachable")
        self.assertEqual(permission.payload_status, "unknown")
        self.assertEqual(failure.payload_status, "unknown")

    def test_distinguishes_disconnected_volume_from_missing_payload_on_a_mount(
        self,
    ) -> None:
        candidate = "/run/media/deck/SDCARD/Games/Game.exe"
        disconnected_probe = FilesystemProbe(mount_entries=lambda: ())
        mounted_probe = FilesystemProbe(
            mount_entries=lambda: (MountEntry(Path("/run/media/deck/SDCARD")),)
        )

        disconnected = (
            self.coordinator(disconnected_probe)
            .resolve_batch([direct_entry(candidate)])
            .results[0]
        )
        missing = (
            self.coordinator(mounted_probe)
            .resolve_batch([direct_entry(candidate)])
            .results[0]
        )

        self.assertEqual(disconnected.reason_code, "drive_disconnected")
        self.assertEqual(missing.reason_code, "payload_missing")
        self.assertEqual(disconnected.payload_status, "unreachable")
        self.assertEqual(missing.payload_status, "unreachable")

    def test_broken_symlink_preserves_disconnected_volume_evidence(self) -> None:
        target = Path("/run/media/deck/SDCARD/Games/Game.exe")
        link = self.root / "Game.exe"
        link.symlink_to(target)

        result = (
            self.coordinator(FilesystemProbe(mount_entries=lambda: ()))
            .resolve_batch([direct_entry(str(link))])
            .results[0]
        )

        self.assertEqual(result.payload_status, "unreachable")
        self.assertEqual(result.reason_code, "drive_disconnected")

    def test_revalidates_resolved_symlink_targets_against_wrapper_policy(self) -> None:
        for target_name in ("wine", "proton", "Heroic.AppImage", "Game.sh"):
            with self.subTest(target_name=target_name):
                target = self.root / target_name
                target.touch()
                target.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
                link = self.root / f"Game-{target_name}.exe"
                link.symlink_to(target)

                result = (
                    self.coordinator()
                    .resolve_batch([direct_entry(str(link))])
                    .results[0]
                )

                self.assertEqual(result.payload_status, "unknown")
                self.assertEqual(result.reason_code, "unsupported")

    def test_unknown_launchers_and_non_list_batches_are_structured_unknown_results(
        self,
    ) -> None:
        unknown = (
            self.coordinator()
            .resolve_batch([direct_entry("/games/Game.exe", launcherKind="heroic")])
            .results[0]
        )
        malformed_batch = self.coordinator().resolve_batch({"entries": []})

        self.assertEqual(unknown.reason_code, "unsupported")
        self.assertEqual(malformed_batch.results, ())
        self.assertEqual(malformed_batch.error, "malformed")

    def test_batch_limits_and_response_order_are_deterministic_without_probe_work(
        self,
    ) -> None:
        def unexpected_stat(_: Path) -> os.stat_result:
            self.fail("an oversized batch must not probe files")

        oversized = self.coordinator(
            FilesystemProbe(stat_func=unexpected_stat)
        ).resolve_batch(
            [direct_entry("/games/Game.exe")] * (MAX_RESOLUTION_BATCH_SIZE + 1)
        )
        ordered = self.coordinator().resolve_batch(
            [
                direct_entry("/missing/Game.exe"),
                direct_entry("/usr/bin/flatpak"),
            ]
        )

        self.assertEqual(oversized.results, ())
        self.assertEqual(oversized.error, "malformed")
        self.assertEqual(
            [item.reason_code for item in ordered.results],
            ["payload_missing", "unsupported"],
        )
        self.assertEqual(ordered.results[0].payload_status, "unreachable")

    def test_deadlines_and_exceptions_are_isolated_per_entry(self) -> None:
        release = threading.Event()

        class FaultInjectingAdapter:
            launcher_kind = "direct"

            def resolve(self, request: ResolutionRequest) -> ResolutionResult:
                candidate = request.normalized.shortcut_exe
                if candidate == "/games/Slow.exe":
                    release.wait()
                if candidate == "/games/Broken.exe":
                    raise RuntimeError("simulated resolver failure")
                assert candidate is not None
                return ResolutionResult.reachable(request, candidate)

        coordinator = GameResolutionCoordinator(
            adapters=[FaultInjectingAdapter()],
            entry_timeout_seconds=0.01,
            batch_timeout_seconds=0.1,
        )
        try:
            result = coordinator.resolve_batch(
                [
                    direct_entry("/games/Slow.exe"),
                    direct_entry("/games/Broken.exe"),
                    direct_entry("/games/Working.exe"),
                ]
            )
        finally:
            release.set()

        self.assertIsNone(result.error)
        self.assertEqual(len(result.results), 3)
        self.assertEqual(
            [item.reason_code for item in result.results],
            ["timeout", "probe_failure", None],
        )
        self.assertEqual(
            [item.payload_status for item in result.results],
            ["unknown", "unknown", "reachable"],
        )

    def test_mount_probe_uses_expected_kind_not_mode_bits(self) -> None:
        payload = self.root / "WindowsGame.exe"
        payload.write_bytes(b"MZ")
        payload.chmod(stat.S_IRUSR | stat.S_IWUSR)

        result = (
            self.coordinator().resolve_batch([direct_entry(str(payload))]).results[0]
        )

        self.assertEqual(result.payload_status, "reachable")
        self.assertEqual(result.metadata_status, "not_requested")
