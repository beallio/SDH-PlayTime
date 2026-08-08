import os
import stat
import tempfile
import subprocess
import threading
import time
import unittest
import unittest.mock
from pathlib import Path
from collections.abc import Callable

from py_modules.game_resolution import (
    DirectExecutableAdapter,
    FlatpakExecutableAdapter,
    FilesystemProbe,
    GameResolutionCoordinator,
    MountEntry,
    MAX_RESOLUTION_BATCH_SIZE,
)
from py_modules.game_resolution.direct import host_subprocess_env
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


def flatpak_entry(app_id: str, **overrides: object) -> dict[str, object]:
    normalized = {
        "shortcutExe": "/usr/bin/flatpak",
        "shortcutLaunchOptions": f"run {app_id}",
        "shortcutStartDir": None,
        "flatpakAppId": app_id,
        "executableTokens": ["/usr/bin/flatpak"],
        "launchOptionTokens": ["run", app_id],
        "startDirTokens": [],
        "commandTokens": ["/usr/bin/flatpak", "run", app_id],
    }
    entry: dict[str, object] = {
        "launcherKind": "flatpak",
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

    def flatpak_coordinator(
        self, run_info: Callable[[str], subprocess.CompletedProcess[str]] | None = None
    ) -> GameResolutionCoordinator:
        adapter = FlatpakExecutableAdapter() if run_info is None else FlatpakExecutableAdapter(run_info=run_info)
        return GameResolutionCoordinator(adapters=[adapter])

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

    def test_rejects_shell_basenames_and_variants_without_probing(self) -> None:
        def unexpected_stat(_: Path) -> os.stat_result:
            self.fail("known shell executables must not reach the filesystem probe")

        coordinator = self.coordinator(FilesystemProbe(stat_func=unexpected_stat))
        for name in ("sh", "bash", "bash.x86_64", "dash.exe", "Fish.AppImage"):
            with self.subTest(name=name):
                result = coordinator.resolve_batch(
                    [direct_entry(f"/home/deck/Games/{name}")]
                ).results[0]

                self.assertEqual(result.payload_status, "unknown")
                self.assertEqual(result.reason_code, "unsupported")

    def test_rejects_common_shell_variants_directly_and_after_symlink_resolution(
        self,
    ) -> None:
        def unexpected_stat(_: Path) -> os.stat_result:
            self.fail("known shell executables must not reach the filesystem probe")

        shell_variants = (
            "csh",
            "csh.exe",
            "csh.AppImage",
            "csh.x86_64",
            "pwsh",
            "pwsh.exe",
            "pwsh.AppImage",
            "pwsh.x86_64",
            "powershell",
            "powershell.exe",
            "powershell.AppImage",
            "powershell.x86_64",
            "cmd",
            "cmd.exe",
            "cmd.AppImage",
            "cmd.x86_64",
            "xonsh",
            "xonsh.exe",
            "xonsh.AppImage",
            "xonsh.x86_64",
            "nu",
            "nu.exe",
            "nu.AppImage",
            "nu.x86_64",
            "busybox",
            "busybox.exe",
            "busybox.AppImage",
            "busybox.x86_64",
        )
        direct_coordinator = self.coordinator(
            FilesystemProbe(stat_func=unexpected_stat)
        )

        for shell_name in shell_variants:
            with self.subTest(boundary="direct", shell_name=shell_name):
                result = direct_coordinator.resolve_batch(
                    [direct_entry(f"/home/deck/Games/{shell_name}")]
                ).results[0]

                self.assertEqual(result.payload_status, "unknown")
                self.assertEqual(result.reason_code, "unsupported")

            with self.subTest(boundary="symlink", shell_name=shell_name):
                target = self.root / shell_name
                target.write_bytes(
                    b"MZ" if target.suffix.casefold() == ".exe" else b"\x7fELF"
                )
                target.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
                link = self.root / f"game-looking-{shell_name}.exe"
                link.symlink_to(target)

                result = (
                    self.coordinator()
                    .resolve_batch([direct_entry(str(link))])
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

    def test_resolves_installed_flatpak_reference_to_a_directory_payload(self) -> None:
        app_id = "com.example.flatpak.game"

        def info(_: str) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=("flatpak", "info", "--show-location", app_id),
                returncode=0,
                stdout="/home/deck/.var/app/com.example.flatpak.game\n",
                stderr="",
            )

        result = (
            self.flatpak_coordinator(info)
            .resolve_batch([flatpak_entry(app_id)])
            .results[0]
        )

        self.assertEqual(result.payload_status, "reachable")
        self.assertEqual(result.payload_kind, "directory")
        self.assertEqual(
            result.payload_path, "/home/deck/.var/app/com.example.flatpak.game"
        )
        self.assertEqual(result.provenance, "untrusted_hint")

    def test_marks_uninstalled_flatpak_games_as_unreachable(self) -> None:
        app_id = "com.example.missing.flatpak"

        def info(_: str) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=("flatpak", "info", "--show-location", app_id),
                returncode=1,
                stdout="",
                stderr="",
            )

        result = (
            self.flatpak_coordinator(info)
            .resolve_batch([flatpak_entry(app_id)])
            .results[0]
        )

        self.assertEqual(result.payload_status, "unreachable")
        self.assertEqual(result.reason_code, "payload_missing")

    def test_rejects_flatpak_requests_with_invalid_app_id(self) -> None:
        result = (
            self.flatpak_coordinator()
            .resolve_batch([flatpak_entry("com.example bad id")])
            .results[0]
        )

        self.assertEqual(result.payload_status, "unknown")
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

    def test_mount_table_uncertainty_is_not_a_conclusive_missing_payload(self) -> None:
        candidate = "/run/media/deck/SDCARD/Games/Game.exe"

        def unavailable_mounts() -> tuple[MountEntry, ...] | None:
            return None

        def failed_mounts() -> tuple[MountEntry, ...] | None:
            raise OSError("mountinfo unavailable")

        for mount_entries in (unavailable_mounts, failed_mounts):
            with self.subTest(mount_entries=mount_entries.__name__):
                result = (
                    self.coordinator(FilesystemProbe(mount_entries=mount_entries))
                    .resolve_batch([direct_entry(candidate)])
                    .results[0]
                )

                self.assertEqual(result.payload_status, "unknown")
                self.assertEqual(result.reason_code, "probe_failure")

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

    def test_symlinked_ancestor_preserves_disconnected_volume_evidence(self) -> None:
        library = self.root / "Library"
        library.symlink_to("/run/media/deck/SDCARD")
        candidate = library / "Games" / "Game.exe"

        result = (
            self.coordinator(FilesystemProbe(mount_entries=lambda: ()))
            .resolve_batch([direct_entry(str(candidate))])
            .results[0]
        )

        self.assertEqual(result.payload_status, "unreachable")
        self.assertEqual(result.reason_code, "drive_disconnected")

    def test_symlinked_ancestor_evidence_allows_exactly_eight_hops(self) -> None:
        links = [self.root / f"link-{index}" for index in range(8)]
        for index, link in enumerate(links):
            target = (
                links[index + 1]
                if index + 1 < len(links)
                else Path("/run/media/deck/SDCARD")
            )
            link.symlink_to(target)
        candidate = links[0] / "Games" / "Game.exe"

        result = (
            self.coordinator(FilesystemProbe(mount_entries=lambda: ()))
            .resolve_batch([direct_entry(str(candidate))])
            .results[0]
        )

        self.assertEqual(result.payload_status, "unreachable")
        self.assertEqual(result.reason_code, "drive_disconnected")

    def test_symlinked_ancestor_evidence_treats_a_ninth_hop_as_uncertain(self) -> None:
        links = [self.root / f"link-{index}" for index in range(9)]
        for index, link in enumerate(links):
            target = (
                links[index + 1]
                if index + 1 < len(links)
                else Path("/run/media/deck/SDCARD")
            )
            link.symlink_to(target)
        candidate = links[0] / "Games" / "Game.exe"

        result = (
            self.coordinator(FilesystemProbe(mount_entries=lambda: ()))
            .resolve_batch([direct_entry(str(candidate))])
            .results[0]
        )

        self.assertEqual(result.payload_status, "unknown")
        self.assertEqual(result.reason_code, "probe_failure")

    def test_revalidates_resolved_symlink_targets_against_wrapper_policy(self) -> None:
        for target_name in (
            "wine",
            "proton",
            "Heroic.AppImage",
            "Game.sh",
            "bash",
            "bash.x86_64",
            "dash.exe",
            "Fish.AppImage",
        ):
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

    def test_stalled_resolvers_are_bounded_by_worker_admission(self) -> None:
        release = threading.Event()
        call_count = 0
        call_lock = threading.Lock()

        class PermanentlyStalledAdapter:
            launcher_kind = "direct"

            def resolve(self, request: ResolutionRequest) -> ResolutionResult:
                nonlocal call_count
                with call_lock:
                    call_count += 1
                release.wait()
                return ResolutionResult.reachable(
                    request, request.normalized.shortcut_exe or ""
                )

        coordinator = GameResolutionCoordinator(
            adapters=[PermanentlyStalledAdapter()],
            entry_timeout_seconds=0.01,
            batch_timeout_seconds=0.1,
            max_workers=2,
        )
        started_at = time.monotonic()
        try:
            batches = [
                coordinator.resolve_batch([direct_entry("/games/Slow.exe")] * 4)
                for _ in range(3)
            ]
            elapsed = time.monotonic() - started_at

            self.assertLess(elapsed, 0.2)
            self.assertEqual(call_count, 2)
            self.assertEqual(coordinator.live_worker_count, 2)
            self.assertEqual(
                [[item.reason_code for item in batch.results] for batch in batches],
                [["timeout"] * 4] * 3,
            )
        finally:
            release.set()

        self.assertTrue(coordinator.wait_for_workers_to_finish(timeout_seconds=0.2))
        self.assertEqual(coordinator.live_worker_count, 0)

    def test_mount_probe_uses_expected_kind_not_mode_bits(self) -> None:
        payload = self.root / "WindowsGame.exe"
        payload.write_bytes(b"MZ")
        payload.chmod(stat.S_IRUSR | stat.S_IWUSR)

        result = (
            self.coordinator().resolve_batch([direct_entry(str(payload))]).results[0]
        )

        self.assertEqual(result.payload_status, "reachable")
        self.assertEqual(result.metadata_status, "not_requested")

    def test_host_subprocess_env_restores_pyinstaller_library_path(self) -> None:
        # Decky ships as a PyInstaller bundle and points LD_LIBRARY_PATH at its own
        # extracted libraries, which breaks every host binary we shell out to.
        with unittest.mock.patch.dict(
            os.environ,
            {
                "LD_LIBRARY_PATH": "/tmp/_MEIabc123",
                "LD_LIBRARY_PATH_ORIG": "/usr/lib:/usr/local/lib",
            },
            clear=False,
        ):
            env = host_subprocess_env()

        self.assertEqual(env["LD_LIBRARY_PATH"], "/usr/lib:/usr/local/lib")
        self.assertNotIn("LD_LIBRARY_PATH_ORIG", env)

    def test_host_subprocess_env_drops_library_path_without_original(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"LD_LIBRARY_PATH": "/tmp/_MEIabc123"}, clear=False
        ):
            os.environ.pop("LD_LIBRARY_PATH_ORIG", None)
            env = host_subprocess_env()

        self.assertNotIn("LD_LIBRARY_PATH", env)

    def test_host_subprocess_env_preserves_unrelated_variables(self) -> None:
        with unittest.mock.patch.dict(
            os.environ, {"HOME": "/home/deck", "PATH": "/usr/bin"}, clear=False
        ):
            env = host_subprocess_env()

        self.assertEqual(env["HOME"], "/home/deck")
        self.assertEqual(env["PATH"], "/usr/bin")
