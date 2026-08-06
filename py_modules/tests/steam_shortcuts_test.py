from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from py_modules.game_resolution.steam_shortcuts import (
    SteamShortcutCatalog,
    shortcut_app_id,
)


def _string(key: str, value: str) -> bytes:
    return b"\x01" + key.encode() + b"\x00" + value.encode() + b"\x00"


def _integer(key: str, value: int) -> bytes:
    return b"\x02" + key.encode() + b"\x00" + value.to_bytes(4, "little", signed=True)


def shortcuts_bytes(
    entries: list[dict[str, str | int]], *, include_app_ids: bool = True
) -> bytes:
    contents = bytearray(b"\x00shortcuts\x00")
    for index, entry in enumerate(entries):
        contents.extend(b"\x00" + str(index).encode() + b"\x00")
        fields = dict(entry)
        if include_app_ids and "appid" not in fields:
            executable = fields.get("exe")
            app_name = fields.get("appname")
            assert isinstance(executable, str)
            assert isinstance(app_name, str)
            app_id = shortcut_app_id(executable, app_name)
            fields["appid"] = app_id - 0x100000000
        for key, value in fields.items():
            if isinstance(value, int):
                contents.extend(_integer(key, value))
            else:
                contents.extend(_string(key, value))
        contents.extend(b"\x08")
    contents.extend(b"\x08\x08")
    return bytes(contents)


def write_shortcuts(path: Path, entries: list[dict[str, str | int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    contents = shortcuts_bytes(entries)
    path.write_bytes(contents)


def catalog_from_bytes(data: bytes) -> SteamShortcutCatalog:
    return SteamShortcutCatalog(
        Path("/shortcuts-test-home"), lambda: "123", read_bytes=lambda _path: data
    )


def direct_entry(executable: str = "/games/Verified.exe") -> dict[str, str]:
    return {"appname": "Verified Game", "exe": executable}


class SteamShortcutCatalogTest(unittest.TestCase):
    def _outcome_from_bytes(self, data: bytes, app_id: int = 1):
        return catalog_from_bytes(data).get_request(app_id)

    def test_binds_a_checksum_request_to_its_matching_shortcuts_vdf_record(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            executable = '"/games/Verified Game.exe"'
            app_name = "Verified Game"
            write_shortcuts(
                home / ".local/share/Steam/userdata/123/config/shortcuts.vdf",
                [{"appname": app_name, "exe": executable}],
            )

            outcome = SteamShortcutCatalog(home, lambda: "123").get_request(
                shortcut_app_id(executable, app_name)
            )

        self.assertIsNotNone(outcome.request)
        assert outcome.request is not None
        self.assertIsNone(outcome.reason_code)
        self.assertEqual(outcome.request.launcher_kind, "direct")
        self.assertEqual(
            outcome.request.normalized.executable_tokens, ("/games/Verified Game.exe",)
        )

    def test_binds_a_nonheroic_flatpak_request_to_matching_shortcuts_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            executable = "/usr/bin/flatpak"
            launch_options = "run org.example.flatpak.game"
            app_name = "Flatpak Game"
            write_shortcuts(
                home / ".local/share/Steam/userdata/123/config/shortcuts.vdf",
                [
                    {
                        "appname": app_name,
                        "exe": executable,
                        "launchoptions": launch_options,
                    },
                ],
            )

            outcome = SteamShortcutCatalog(home, lambda: "123").get_request(
                shortcut_app_id(executable, app_name)
            )

        self.assertIsNotNone(outcome.request)
        assert outcome.request is not None
        self.assertEqual(outcome.request.launcher_kind, "flatpak")
        self.assertEqual(
            outcome.request.normalized.executable_tokens, ("/usr/bin/flatpak",)
        )
        self.assertEqual(outcome.request.normalized.launch_option_tokens, ("run", "org.example.flatpak.game"))

    def test_refuses_distinct_records_with_the_same_shortcut_app_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            executable = "/games/Verified.exe"
            app_name = "Verified Game"
            write_shortcuts(
                home / ".local/share/Steam/userdata/123/config/shortcuts.vdf",
                [
                    {"appname": app_name, "exe": executable},
                    {
                        "appname": app_name,
                        "exe": executable,
                        "launchoptions": "--alternate-launch-data",
                    },
                ],
            )

            outcome = SteamShortcutCatalog(home, lambda: "123").get_request(
                shortcut_app_id(executable, app_name)
            )

        self.assertEqual(getattr(outcome, "reason_code", None), "ambiguous")

    def test_deduplicates_aliases_and_identical_catalog_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            executable = "/games/Verified.exe"
            app_name = "Verified Game"
            entry = {"appname": app_name, "exe": executable}
            target = home / ".steam/root/userdata/123/config/shortcuts.vdf"
            write_shortcuts(target, [entry])
            local_share = home / ".local/share"
            local_share.mkdir(parents=True)
            (local_share / "Steam").symlink_to(home / ".steam/root")
            write_shortcuts(
                home / ".steam/steam/userdata/123/config/shortcuts.vdf", [entry]
            )

            outcome = SteamShortcutCatalog(home, lambda: "123").get_request(
                shortcut_app_id(executable, app_name)
            )

        self.assertIsNotNone(outcome.request)
        self.assertIsNone(outcome.reason_code)

    def test_validates_signed_stored_app_id_against_derived_identity(self) -> None:
        executable = "/games/Verified.exe"
        app_name = "Verified Game"
        app_id = shortcut_app_id(executable, app_name)
        valid = self._outcome_from_bytes(
            shortcuts_bytes([{"appname": app_name, "exe": executable}]), app_id
        )
        missing = self._outcome_from_bytes(
            shortcuts_bytes(
                [{"appname": app_name, "exe": executable}], include_app_ids=False
            ),
            app_id,
        )
        non_integer = self._outcome_from_bytes(
            shortcuts_bytes(
                [{"appname": app_name, "exe": executable, "appid": "not-an-int"}]
            ),
            app_id,
        )
        mismatched = self._outcome_from_bytes(
            shortcuts_bytes([{"appname": app_name, "exe": executable, "appid": 1}]),
            app_id,
        )

        self.assertIsNotNone(valid.request)
        self.assertIsNone(valid.reason_code)
        for outcome in (missing, non_integer, mismatched):
            self.assertIsNone(outcome.request)
            self.assertEqual(outcome.reason_code, "malformed")

    def test_rejects_malformed_shortcuts_before_accepting_a_record(self) -> None:
        valid = shortcuts_bytes([direct_entry()])
        excessive_nesting = b"\x08"
        for index in range(17):
            excessive_nesting = (
                b"\x00nested" + str(index).encode() + b"\x00" + excessive_nesting
            )
        excessive_nesting = b"\x00shortcuts\x00" + excessive_nesting + b"\x08"
        excessive_records = (
            b"\x00shortcuts\x00"
            + b"".join(
                b"\x00" + str(index).encode() + b"\x00\x08" for index in range(4097)
            )
            + b"\x08"
        )
        malformed_cases = {
            "truncated string": b"\x00shortcuts\x00\x00"
            b"0\x00\x01appname\x00unterminated",
            "truncated integer": b"\x00shortcuts\x00\x000\x00\x02appid\x00\x01",
            "unsupported field type": b"\x00shortcuts\x00\x00"
            b"0\x00\x03appid\x00\x08\x08",
            "invalid utf8": b"\x00shortcuts\x00\x00"
            b"0\x00\x01appname\x00\xff\x00\x08\x08",
            "oversized string": b"\x00shortcuts\x00\x00"
            b"0\x00\x01appname\x00" + b"x" * 4097 + b"\x00\x08\x08",
            "duplicate casefolded key": b"\x00shortcuts\x00\x00"
            b"0\x00"
            + _string("appname", "one")
            + _string("AppName", "two")
            + b"\x08\x08",
            "duplicate record key": b"\x00shortcuts\x00\x000\x00\x08\x000\x00\x08\x08",
            "trailing bytes": valid + b"trailing",
            "excessive nesting": excessive_nesting,
            "excessive records": excessive_records,
            "excessive file size": b"x" * (8 * 1024 * 1024 + 1),
        }

        for name, data in malformed_cases.items():
            with self.subTest(name=name):
                outcome = self._outcome_from_bytes(data)
                self.assertIsNone(outcome.request)
                self.assertEqual(outcome.reason_code, "malformed")

    def test_default_reader_stops_at_the_shortcuts_size_limit(self) -> None:
        class TooLargeStream:
            read_size: int | None = None

            def __enter__(self):
                return self

            def __exit__(self, _type, _value, _traceback):
                return False

            def read(self, size: int) -> bytes:
                self.read_size = size
                return b"x" * size

        stream = TooLargeStream()
        with patch.object(Path, "open", return_value=stream):
            outcome = SteamShortcutCatalog(
                Path("/shortcuts-test-home"), lambda: "123"
            ).get_request(1)

        self.assertIsNone(outcome.request)
        self.assertEqual(outcome.reason_code, "malformed")
        self.assertEqual(stream.read_size, 8 * 1024 * 1024 + 1)


if __name__ == "__main__":
    unittest.main()
