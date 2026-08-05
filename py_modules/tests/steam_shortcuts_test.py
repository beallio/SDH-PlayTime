from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from py_modules.game_resolution.steam_shortcuts import (
    SteamShortcutCatalog,
    shortcut_app_id,
)


def write_shortcuts(path: Path, entries: list[dict[str, str]]) -> None:
    def string(key: str, value: str) -> bytes:
        return b"\x01" + key.encode() + b"\x00" + value.encode() + b"\x00"

    contents = bytearray(b"\x00shortcuts\x00")
    for index, entry in enumerate(entries):
        contents.extend(b"\x00" + str(index).encode() + b"\x00")
        for key, value in entry.items():
            contents.extend(string(key, value))
        contents.extend(b"\x08")
    contents.extend(b"\x08")
    contents.extend(b"\x08")
    path.parent.mkdir(parents=True)
    path.write_bytes(contents)


class SteamShortcutCatalogTest(unittest.TestCase):
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

            request = SteamShortcutCatalog(home, lambda: "123").get_request(
                shortcut_app_id(executable, app_name)
            )

        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.launcher_kind, "direct")
        self.assertEqual(
            request.normalized.executable_tokens, ("/games/Verified Game.exe",)
        )


if __name__ == "__main__":
    unittest.main()
