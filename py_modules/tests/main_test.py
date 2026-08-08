import unittest
import json
import os
import shutil
import tempfile
import sqlite3
from datetime import datetime
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from py_modules.tests.helpers import remove_date_fields


GAME_PARENT_PROJECTION_FIXTURE_PATH = (
    Path(__file__).parents[2] / "tests" / "fixtures" / "game-parent-projection.json"
)


class TestPlugin(unittest.IsolatedAsyncioTestCase):
    STORAGE_DB_FILENAME = "storage.db"

    @classmethod
    def setUpClass(cls):
        """Set up mock environment and dependencies before importing main.py."""
        cls.mock_decky_user_home = tempfile.mkdtemp()
        cls.mock_plugin_runtime_dir = tempfile.mkdtemp()
        cls.mock_plugin_dir = tempfile.mkdtemp()

        os.makedirs(os.path.join(cls.mock_plugin_dir, "py_modules"), exist_ok=True)

        mock_env = {
            "DECKY_USER_HOME": cls.mock_decky_user_home,
            "DECKY_PLUGIN_RUNTIME_DIR": cls.mock_plugin_runtime_dir,
            "DECKY_PLUGIN_DIR": cls.mock_plugin_dir,
        }

        cls.mock_decky = MagicMock()
        cls.mock_decky.logger = MagicMock()

        cls.mocked_modules = {
            "decky": cls.mock_decky,
        }

        cls.patcher_env = patch.dict("os.environ", mock_env, clear=True)
        cls.patcher_modules = patch.dict("sys.modules", cls.mocked_modules)
        cls.patcher_env.start()
        cls.patcher_modules.start()

        global main
        import main

        cls.main = main

        cls.addClassCleanup(cls.patcher_env.stop)
        cls.addClassCleanup(cls.patcher_modules.stop)
        cls.addClassCleanup(shutil.rmtree, cls.mock_decky_user_home)
        cls.addClassCleanup(shutil.rmtree, cls.mock_plugin_runtime_dir)
        cls.addClassCleanup(shutil.rmtree, cls.mock_plugin_dir)

    def _get_games_from_db(self, db_path: str) -> list:
        """Helper to read game_dict data from a database."""
        with closing(sqlite3.connect(db_path)) as conn:
            return conn.execute("SELECT game_id, name FROM game_dict").fetchall()

    async def test_has_min_required_python_version(self):
        plugin = self.main.Plugin()
        with patch("sys.version_info", (3, 11, 0)):
            self.assertTrue(await plugin.has_min_required_python_version())
        with patch("sys.version_info", (3, 10, 9)):
            self.assertFalse(await plugin.has_min_required_python_version())

    async def test_get_decky_home(self):
        plugin = self.main.Plugin()
        result = await plugin.get_decky_home()
        self.assertEqual(result, self.mock_decky_user_home)

    async def test_apply_manual_time_correction(self):
        plugin = self.main.Plugin()
        await plugin._main()

        # Set a test user before accessing database
        await plugin.set_current_user("76561198012345678")

        await plugin.apply_manual_time_correction(
            [
                {
                    "game": {
                        "id": "3536189763",
                        "name": "Grand Theft Auto: San Andreas",
                    },
                    "time": 28800,
                }
            ]
        )

        per_game_overall_statistics = await plugin.per_game_overall_statistics()
        self.assertEqual(
            remove_date_fields(per_game_overall_statistics),
            [
                {
                    "game": {
                        "id": "3536189763",
                        "name": "Grand Theft Auto: San Andreas",
                    },
                    "lastSession": {
                        "checksum": None,
                        "duration": 28800,
                        "migrated": "manually-changed",
                    },
                    "totalTime": 28800,
                    "sessions": [
                        {
                            "checksum": None,
                            "duration": 28800,
                            "migrated": "manually-changed",
                        }
                    ],
                }
            ],
        )

    async def test_unload_logs_message(self):
        plugin = self.main.Plugin()
        await plugin._unload()
        self.mock_decky.logger.info.assert_called_with("Goodnight, World!")

    async def test_uninstall_logs_message(self):
        plugin = self.main.Plugin()
        await plugin._uninstall()
        self.mock_decky.logger.info.assert_called_with("Goodbye, World!")

    async def test_set_current_user_creates_user_database(self):
        """Test that set_current_user creates a user-specific database."""
        plugin = self.main.Plugin()
        await plugin._main()

        user_id = "76561198099999999"
        await plugin.set_current_user(user_id)

        # Verify user database was created
        user_db_path = (
            Path(self.mock_plugin_runtime_dir) / "users" / user_id / "storage.db"
        )
        self.assertTrue(user_db_path.exists())

        # Verify get_current_user returns correct user
        current_user = await plugin.get_current_user()
        self.assertEqual(current_user, user_id)

    async def test_multi_user_data_isolation(self):
        """Test that different users have isolated data."""
        plugin = self.main.Plugin()
        await plugin._main()

        user1 = "76561198011111111"
        user2 = "76561198022222222"

        # User 1 adds playtime
        await plugin.set_current_user(user1)
        await plugin.apply_manual_time_correction(
            [{"game": {"id": "user1_game", "name": "User 1 Game"}, "time": 3600}]
        )

        # User 2 adds playtime
        await plugin.set_current_user(user2)
        await plugin.apply_manual_time_correction(
            [{"game": {"id": "user2_game", "name": "User 2 Game"}, "time": 7200}]
        )

        # Verify User 1's data
        await plugin.set_current_user(user1)
        user1_stats = await plugin.per_game_overall_statistics()
        user1_game_ids = [stat["game"]["id"] for stat in user1_stats]
        self.assertIn("user1_game", user1_game_ids)
        self.assertNotIn("user2_game", user1_game_ids)

        # Verify User 2's data
        await plugin.set_current_user(user2)
        user2_stats = await plugin.per_game_overall_statistics()
        user2_game_ids = [stat["game"]["id"] for stat in user2_stats]
        self.assertIn("user2_game", user2_game_ids)
        self.assertNotIn("user1_game", user2_game_ids)

    async def test_legacy_db_migration_on_first_user_login(self):
        """Test that legacy DB is migrated when first user logs in."""
        # Create a legacy database with some data first
        from py_modules.db.sqlite_db import SqlLiteDb
        from py_modules.db.migration import DbMigration
        from py_modules.db.dao import Dao

        legacy_path = Path(self.mock_plugin_runtime_dir) / "storage.db"
        db = SqlLiteDb(str(legacy_path))
        DbMigration(db).migrate()
        dao = Dao(db)
        dao.save_game_dict("legacy_game", "Legacy Game")
        dao.save_play_time(
            start=__import__("datetime").datetime(2024, 1, 1, 12, 0, 0),
            time_s=1800,
            game_id="legacy_game",
        )

        # Now create plugin and set user
        plugin = self.main.Plugin()
        await plugin._main()

        user_id = "76561198033333333"
        await plugin.set_current_user(user_id)

        # Verify legacy data was migrated to user's DB
        stats = await plugin.per_game_overall_statistics()
        game_ids = [stat["game"]["id"] for stat in stats]
        self.assertIn("legacy_game", game_ids)

        # Verify legacy DB still exists unchanged
        self.assertTrue(legacy_path.exists())
        legacy_games = self._get_games_from_db(str(legacy_path))
        self.assertEqual(len(legacy_games), 1)
        self.assertEqual(legacy_games[0], ("legacy_game", "Legacy Game"))

    async def test_add_time_with_default_status_tracks_playtime(self):
        """Test that add_time tracks playtime for games with default status."""
        plugin = self.main.Plugin()
        await plugin._main()
        await plugin.set_current_user("76561198044444444")

        # Add playtime (default status)
        await plugin.add_time(
            {
                "started_at": 1672574400,  # 2023-01-01 10:00:00
                "ended_at": 1672578000,  # 2023-01-01 11:00:00
                "game_id": "game_default",
                "game_name": "Default Game",
            }
        )

        # Verify playtime was tracked
        stats = await plugin.per_game_overall_statistics()
        game_ids = [stat["game"]["id"] for stat in stats]
        self.assertIn("game_default", game_ids, "Default status should allow tracking")

        # Verify the actual time
        game_stat = next(s for s in stats if s["game"]["id"] == "game_default")
        self.assertEqual(
            game_stat["totalTime"], 3600, "Should have tracked 1 hour (3600 seconds)"
        )

    async def test_add_time_with_pause_status_prevents_tracking(self):
        """Test that add_time does NOT track playtime for games with pause status."""
        plugin = self.main.Plugin()
        await plugin._main()
        await plugin.set_current_user("76561198055555555")

        # Create game in DB first by adding some initial playtime
        await plugin.add_time(
            {
                "started_at": 1672488000,  # 2022-12-31 10:00:00
                "ended_at": 1672491600,  # 2022-12-31 11:00:00
                "game_id": "game_pause",
                "game_name": "Paused Game",
            }
        )

        # Now set to pause status
        await plugin.set_game_tracking_status(
            {"game_id": "game_pause", "status": "pause"}
        )

        # Try to add more playtime (should be blocked by pause status)
        await plugin.add_time(
            {
                "started_at": 1672574400,  # 2023-01-01 10:00:00
                "ended_at": 1672578000,  # 2023-01-01 11:00:00
                "game_id": "game_pause",
                "game_name": "Paused Game",
            }
        )

        # Verify only the first session was tracked (not the second)
        stats = await plugin.per_game_overall_statistics()
        game_stat = next(s for s in stats if s["game"]["id"] == "game_pause")
        self.assertEqual(
            game_stat["totalTime"],
            3600,  # Only 1 hour from first session
            "Pause status should prevent new tracking - time should not increase",
        )

    async def test_add_time_with_ignore_status_prevents_tracking(self):
        """Test that add_time does NOT track playtime for games with ignore status."""
        plugin = self.main.Plugin()
        await plugin._main()
        await plugin.set_current_user("76561198066666666")

        # Create game in DB first by adding some initial playtime
        await plugin.add_time(
            {
                "started_at": 1672488000,  # 2022-12-31 10:00:00
                "ended_at": 1672491600,  # 2022-12-31 11:00:00
                "game_id": "game_ignore",
                "game_name": "Ignored Game",
            }
        )

        # Now set to ignore status
        await plugin.set_game_tracking_status(
            {"game_id": "game_ignore", "status": "ignore"}
        )

        # Try to add more playtime (should be blocked by ignore status)
        await plugin.add_time(
            {
                "started_at": 1672574400,  # 2023-01-01 10:00:00
                "ended_at": 1672578000,  # 2023-01-01 11:00:00
                "game_id": "game_ignore",
                "game_name": "Ignored Game",
            }
        )

        # Verify playtime did NOT increase (check raw DB since ignore hides from stats)
        dao = plugin._get_current_dao()
        result = dao.fetch_overall_playtime()
        game_data = next((g for g in result if g.game_id == "game_ignore"), None)
        self.assertIsNotNone(game_data, "Game should exist from first session")
        self.assertEqual(
            game_data.time,
            3600,  # Only 1 hour from first session
            "Ignore status should prevent new tracking - time should not increase",
        )

    async def test_add_time_with_hidden_status_tracks_but_hides_from_ui(self):
        """Test that add_time tracks playtime for hidden games but they don't appear in stats."""
        plugin = self.main.Plugin()
        await plugin._main()
        await plugin.set_current_user("76561198077777777")

        # Create game in DB first by adding some initial playtime
        await plugin.add_time(
            {
                "started_at": 1672488000,  # 2022-12-31 10:00:00
                "ended_at": 1672491600,  # 2022-12-31 11:00:00
                "game_id": "game_hidden",
                "game_name": "Hidden Game",
            }
        )

        # Now set to hidden status
        await plugin.set_game_tracking_status(
            {"game_id": "game_hidden", "status": "hidden"}
        )

        # Add more playtime (should be tracked despite hidden status)
        await plugin.add_time(
            {
                "started_at": 1672574400,  # 2023-01-01 10:00:00
                "ended_at": 1672578000,  # 2023-01-01 11:00:00
                "game_id": "game_hidden",
                "game_name": "Hidden Game",
            }
        )

        # Verify playtime is tracked in DB (both sessions)
        dao = plugin._get_current_dao()
        result = dao.fetch_overall_playtime()
        game_data = next(g for g in result if g.game_id == "game_hidden")
        self.assertEqual(
            game_data.time,
            7200,  # 2 hours from both sessions
            "Hidden status should still track playtime in DB",
        )

        # Verify it's hidden from statistics UI
        stats = await plugin.per_game_overall_statistics()
        stat_game_ids = [stat["game"]["id"] for stat in stats]
        self.assertNotIn(
            "game_hidden",
            stat_game_ids,
            "Hidden status should hide game from statistics",
        )

    async def test_add_time_multiple_sessions_with_status_changes(self):
        """Test add_time behavior across status changes."""
        plugin = self.main.Plugin()
        await plugin._main()
        await plugin.set_current_user("76561198088888888")

        # Session 1: Default status - should track
        await plugin.add_time(
            {
                "started_at": 1672574400,  # 2023-01-01 10:00:00
                "ended_at": 1672578000,  # 2023-01-01 11:00:00
                "game_id": "game_multi",
                "game_name": "Multi Status Game",
            }
        )

        # Change to pause status
        await plugin.set_game_tracking_status(
            {"game_id": "game_multi", "status": "pause"}
        )

        # Session 2: Pause status - should NOT track
        await plugin.add_time(
            {
                "started_at": 1672660800,  # 2023-01-02 10:00:00
                "ended_at": 1672664400,  # 2023-01-02 11:00:00
                "game_id": "game_multi",
                "game_name": "Multi Status Game",
            }
        )

        # Change to ignore status
        await plugin.set_game_tracking_status(
            {"game_id": "game_multi", "status": "ignore"}
        )

        # Session 3: Ignore status - should NOT track
        await plugin.add_time(
            {
                "started_at": 1672747200,  # 2023-01-03 10:00:00
                "ended_at": 1672750800,  # 2023-01-03 11:00:00
                "game_id": "game_multi",
                "game_name": "Multi Status Game",
            }
        )

        # Change back to default
        await plugin.set_game_tracking_status(
            {"game_id": "game_multi", "status": "default"}
        )

        # Session 4: Default status again - should track
        await plugin.add_time(
            {
                "started_at": 1672833600,  # 2023-01-04 10:00:00
                "ended_at": 1672837200,  # 2023-01-04 11:00:00
                "game_id": "game_multi",
                "game_name": "Multi Status Game",
            }
        )

        # Verify only sessions 1 and 4 were tracked (2 hours total)
        stats = await plugin.per_game_overall_statistics()
        game_stat = next(s for s in stats if s["game"]["id"] == "game_multi")
        self.assertEqual(
            game_stat["totalTime"],
            7200,  # 2 hours = 7200 seconds
            "Only sessions with default status (1 and 4) should be tracked",
        )

    async def test_add_time_with_existing_playtime_then_pause(self):
        """Test that changing to pause status keeps existing time visible but blocks new tracking."""
        plugin = self.main.Plugin()
        await plugin._main()
        await plugin.set_current_user("76561198099999999")

        # Add playtime with default status
        await plugin.add_time(
            {
                "started_at": 1672574400,  # 2023-01-01 10:00:00
                "ended_at": 1672578000,  # 2023-01-01 11:00:00
                "game_id": "game_pause_after",
                "game_name": "Pause After Game",
            }
        )

        # Verify initial playtime
        stats = await plugin.per_game_overall_statistics()
        game_stat = next(s for s in stats if s["game"]["id"] == "game_pause_after")
        self.assertEqual(game_stat["totalTime"], 3600)

        # Change to pause status
        await plugin.set_game_tracking_status(
            {"game_id": "game_pause_after", "status": "pause"}
        )

        # Try to add more playtime (should be blocked)
        await plugin.add_time(
            {
                "started_at": 1672660800,  # 2023-01-02 10:00:00
                "ended_at": 1672664400,  # 2023-01-02 11:00:00
                "game_id": "game_pause_after",
                "game_name": "Pause After Game",
            }
        )

        # Verify time is still visible (pause doesn't hide) but unchanged
        stats = await plugin.per_game_overall_statistics()
        game_ids = [stat["game"]["id"] for stat in stats]
        self.assertIn(
            "game_pause_after",
            game_ids,
            "Pause status should keep existing time visible",
        )

        game_stat = next(s for s in stats if s["game"]["id"] == "game_pause_after")
        self.assertEqual(
            game_stat["totalTime"],
            3600,
            "Time should not increase - second session should be blocked",
        )

    async def test_association_component_rpcs_return_the_grouped_confirmation_dto(self):
        plugin = self.main.Plugin()
        await plugin._main()
        await plugin.set_current_user("76561198077777777")
        dao = plugin.association_manager.dao
        for game_id, name in [
            ("alpha", "Alpha"),
            ("beta", "Beta"),
            ("gamma", "Gamma"),
        ]:
            dao.save_game_dict(game_id, name)
            dao.save_game_checksum(game_id, "shared", "SHA256", 1, None, None)
        dao.create_game_association("alpha", "beta")
        dao.create_game_association("alpha", "gamma")

        read_result = await plugin.get_game_association_component("gamma")

        self.assertEqual(
            read_result,
            {
                "success": True,
                "data": {
                    "anchorGameId": "gamma",
                    "expectedParentGameId": "alpha",
                    "existingMembers": [
                        {"gameId": "alpha", "gameName": "Alpha"},
                        {"gameId": "beta", "gameName": "Beta"},
                        {"gameId": "gamma", "gameName": "Gamma"},
                    ],
                    "fingerprint": dao.game_association_component_fingerprint(
                        ("alpha", "beta", "gamma")
                    ),
                    "status": "confirmed",
                    "aliases": ["beta", "gamma"],
                },
            },
        )

        confirmation_result = await plugin.confirm_game_association_component(
            {
                "anchor_game_id": "gamma",
                "proposed_parent_game_id": "beta",
                "proposed_parent_game_name": "Beta",
                "expected_parent_game_id": "alpha",
                "expected_fingerprint": read_result["data"]["fingerprint"],
                "selected_members": [
                    {"game_id": "alpha", "game_name": "Alpha"},
                    {"game_id": "beta", "game_name": "Beta"},
                    {"game_id": "gamma", "game_name": "Gamma"},
                ],
            }
        )

        self.assertEqual(confirmation_result["success"], True)
        self.assertEqual(
            confirmation_result["data"]["proposedParent"],
            {"gameId": "beta", "gameName": "Beta"},
        )
        self.assertEqual(
            confirmation_result["data"]["confirmedParent"],
            {"gameId": "beta", "gameName": "Beta"},
        )
        self.assertEqual(confirmation_result["data"]["expectedParentGameId"], "beta")
        self.assertEqual(
            confirmation_result["data"]["fingerprint"],
            read_result["data"]["fingerprint"],
        )
        self.assertEqual(confirmation_result["data"]["status"], "confirmed")
        self.assertEqual(confirmation_result["data"]["aliases"], ["alpha", "gamma"])

    async def test_grouped_confirmation_projects_one_canonical_parent_everywhere(self):
        """The RPC-selected parent must win over checksum order in every projection."""
        fixture = json.loads(
            GAME_PARENT_PROJECTION_FIXTURE_PATH.read_text(encoding="utf-8")
        )
        canonical_record = fixture["canonicalRecord"]
        assert isinstance(canonical_record, dict)
        canonical_parent = fixture["canonicalParent"]
        assert isinstance(canonical_parent, dict)
        aliases = fixture["aliases"]
        assert isinstance(aliases, list)
        steam_alias = fixture["steamAlias"]
        assert isinstance(steam_alias, int)
        plugin = self.main.Plugin()
        await plugin._main()
        await plugin.set_current_user("76561198077777775")
        dao = plugin.association_manager.dao

        for game_id, name in (
            (str(steam_alias), "Steam Shortcut Alias"),
            ("representative-child", "Representative Child"),
            ("hidden-child", "Hidden Child"),
            ("third-leader", "Third Leader"),
            ("explicit-parent", "Explicit Parent"),
        ):
            dao.save_game_dict(game_id, name)

        # Two confirmed parents become one checksum component only after both stars
        # exist. The explicit, zero-time parent selected through the RPC must win.
        dao.create_game_association(str(steam_alias), "representative-child")
        dao.create_game_association("third-leader", "hidden-child")
        for game_id, checksum in (
            (str(steam_alias), "left"),
            ("representative-child", "left"),
            ("representative-child", "right"),
            ("hidden-child", "right"),
        ):
            dao.save_game_checksum(game_id, checksum, "SHA256", 1, None, None)
        for game_id, seconds in (
            (str(steam_alias), 10),
            ("representative-child", 20),
            ("hidden-child", 30),
        ):
            dao.save_play_time(datetime(2025, 1, 1, 12, 0), seconds, game_id)

        snapshot = await plugin.get_game_association_component("representative-child")
        self.assertEqual(snapshot["data"]["status"], "conflict")
        confirmation = await plugin.confirm_game_association_component(
            {
                "anchor_game_id": "representative-child",
                "proposed_parent_game_id": "explicit-parent",
                "proposed_parent_game_name": "Explicit Parent",
                "expected_parent_game_id": None,
                "expected_fingerprint": snapshot["data"]["fingerprint"],
                "selected_members": [
                    {
                        "game_id": str(steam_alias),
                        "game_name": "Steam Shortcut Alias",
                    },
                    {
                        "game_id": "representative-child",
                        "game_name": "Representative Child",
                    },
                    {"game_id": "hidden-child", "game_name": "Hidden Child"},
                    {"game_id": "third-leader", "game_name": "Third Leader"},
                    {"game_id": "explicit-parent", "game_name": "Explicit Parent"},
                ],
            }
        )

        self.assertEqual(confirmation["success"], True)
        self.assertEqual(
            confirmation["data"]["confirmedParent"],
            {
                "gameId": canonical_parent["gameId"],
                "gameName": canonical_parent["gameName"],
            },
        )
        self.assertEqual(canonical_parent["recordedSeconds"], 0)
        self.assertEqual(confirmation["data"]["aliases"], aliases)

        all_time = await plugin.fetch_playtime_information()
        daily = await plugin.daily_statistics_for_period(
            {"start_date": "2025-01-01", "end_date": "2025-01-01"}
        )
        overall = await plugin.per_game_overall_statistics()
        dictionary = await plugin.get_games_dictionary()
        all_time_canonical = next(
            entry
            for entry in all_time
            if entry["game"]["id"] == canonical_record["game"]["id"]
        )
        self.assertEqual(
            {
                key: all_time_canonical[key]
                for key in ("game", "totalTime", "lastPlayedDate", "aliasesId")
            },
            canonical_record,
        )
        daily_canonical = daily["data"][0]["games"][0]
        self.assertEqual(
            {key: daily_canonical[key] for key in ("game", "totalTime")},
            fixture["dailyProjection"],
        )
        overall_canonical = next(
            entry
            for entry in overall
            if entry["game"]["id"] == canonical_record["game"]["id"]
        )
        self.assertEqual(
            {key: overall_canonical[key] for key in ("game", "totalTime")},
            fixture["overallProjection"],
        )
        canonical_dictionary = next(
            entry
            for entry in dictionary
            if entry["game"]["id"] == canonical_record["game"]["id"]
        )
        self.assertEqual(
            {
                "game": canonical_dictionary["game"],
                "fileGameIds": [
                    checksum["game"]["id"] for checksum in canonical_dictionary["files"]
                ],
            },
            fixture["dictionaryProjection"],
        )

        components = dao.get_game_identity_components()
        for game_id in (
            str(steam_alias),
            "representative-child",
            "hidden-child",
            "third-leader",
            "explicit-parent",
        ):
            self.assertEqual(components[game_id].canonical_id, "explicit-parent")

    async def test_grouped_confirmation_rpc_rejects_stale_state_and_rolls_back(self):
        plugin = self.main.Plugin()
        await plugin._main()
        await plugin.set_current_user("76561198077777774")
        dao = plugin.association_manager.dao
        for game_id in ("alpha", "beta", "gamma"):
            dao.save_game_dict(game_id, game_id.title())
            dao.save_game_checksum(game_id, "shared", "SHA256", 1, None, None)
        dao.create_game_association("alpha", "beta")
        dao.create_game_association("alpha", "gamma")

        stale_snapshot = await plugin.get_game_association_component("beta")
        dao.save_game_dict("late-member", "Late Member")
        dao.save_game_checksum("late-member", "shared", "SHA256", 1, None, None)
        stale_result = await plugin.confirm_game_association_component(
            {
                "anchor_game_id": "beta",
                "proposed_parent_game_id": "beta",
                "proposed_parent_game_name": "Beta",
                "expected_parent_game_id": "alpha",
                "expected_fingerprint": stale_snapshot["data"]["fingerprint"],
                "selected_members": [
                    {"game_id": "alpha", "game_name": "Alpha"},
                    {"game_id": "beta", "game_name": "Beta"},
                    {"game_id": "gamma", "game_name": "Gamma"},
                ],
            }
        )
        self.assertEqual(stale_result["success"], False)
        self.assertEqual(stale_result["error"]["code"], "STALE_COMPONENT")

        snapshot = await plugin.get_game_association_component("beta")
        before = dao.get_all_game_associations()
        original_create = dao._create_game_association
        calls = 0

        def fail_second_insert(connection, parent_game_id, child_game_id):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise sqlite3.IntegrityError("forced rollback")
            return original_create(connection, parent_game_id, child_game_id)

        with patch.object(dao, "_create_game_association", fail_second_insert):
            rollback_result = await plugin.confirm_game_association_component(
                {
                    "anchor_game_id": "beta",
                    "proposed_parent_game_id": "beta",
                    "proposed_parent_game_name": "Beta",
                    "expected_parent_game_id": "alpha",
                    "expected_fingerprint": snapshot["data"]["fingerprint"],
                    "selected_members": [
                        {"game_id": "alpha", "game_name": "Alpha"},
                        {"game_id": "beta", "game_name": "Beta"},
                        {"game_id": "gamma", "game_name": "Gamma"},
                        {"game_id": "late-member", "game_name": "Late Member"},
                    ],
                }
            )

        self.assertEqual(rollback_result["success"], False)
        self.assertEqual(rollback_result["error"]["code"], "ASSOCIATION_UPDATE_FAILED")
        self.assertEqual(dao.get_all_game_associations(), before)

    async def test_association_candidates_include_children_and_zero_time_identities(
        self,
    ):
        plugin = self.main.Plugin()
        await plugin._main()
        await plugin.set_current_user("76561198077777776")
        dao = plugin.association_manager.dao
        dao.save_game_dict("zero-parent", "")
        dao.save_game_dict("child-game", "Child Game")
        dao.create_game_association("zero-parent", "child-game")

        candidates = await plugin.get_association_candidates()
        legacy_dictionary = await plugin.get_games_dictionary()

        self.assertEqual(
            candidates,
            [
                {
                    "game": {"id": "child-game", "name": "Child Game"},
                    "duration": 0,
                },
                {
                    "game": {"id": "zero-parent", "name": "Unknown Game"},
                    "duration": 0,
                },
            ],
        )
        self.assertEqual(
            [entry["game"]["id"] for entry in legacy_dictionary],
            ["zero-parent"],
        )

    async def test_association_component_confirmation_rejects_malformed_input(self):
        plugin = self.main.Plugin()
        await plugin._main()
        await plugin.set_current_user("76561198088888888")

        result = await plugin.confirm_game_association_component(None)

        self.assertEqual(result["success"], False)
        self.assertEqual(result["error"]["code"], "INVALID_REQUEST")

    async def test_association_component_confirmation_rejects_over_limit_input(self):
        plugin = self.main.Plugin()
        await plugin._main()
        await plugin.set_current_user("76561198088888887")
        boundary_request = {
            "anchor_game_id": "a" * 255,
            "proposed_parent_game_id": "a" * 255,
            "proposed_parent_game_name": "n" * 1024,
            "expected_parent_game_id": None,
            "expected_fingerprint": "fingerprint",
            "selected_members": [
                {
                    "game_id": "a" * 255,
                    "game_name": "n" * 1024,
                },
                *[
                    {"game_id": f"game-{index}", "game_name": "Game"}
                    for index in range(99)
                ],
            ],
        }

        boundary_result = await plugin.confirm_game_association_component(
            boundary_request
        )
        too_many_members_result = await plugin.confirm_game_association_component(
            {
                **boundary_request,
                "selected_members": [
                    {"game_id": f"game-{index}", "game_name": "Game"}
                    for index in range(101)
                ],
            }
        )
        too_long_name_result = await plugin.confirm_game_association_component(
            {
                **boundary_request,
                "proposed_parent_game_name": "n" * 1025,
            }
        )
        too_long_id_result = await plugin.confirm_game_association_component(
            {
                **boundary_request,
                "anchor_game_id": "a" * 256,
            }
        )

        self.assertEqual(boundary_result["error"]["code"], "ANCHOR_NOT_FOUND")
        self.assertEqual(too_many_members_result["error"]["code"], "INVALID_REQUEST")
        self.assertEqual(too_long_name_result["error"]["code"], "INVALID_REQUEST")
        self.assertEqual(too_long_id_result["error"]["code"], "INVALID_REQUEST")

    async def test_association_component_rpcs_bound_identifiers_and_components(self):
        from py_modules.schemas.request import MAX_ASSOCIATION_COMPONENT_MEMBERS

        plugin = self.main.Plugin()
        await plugin._main()
        await plugin.set_current_user("76561198088888886")
        dao = plugin.association_manager.dao
        boundary_game_id = "a" * 255
        dao.save_game_dict(boundary_game_id, "Boundary Game")

        self.assertEqual(
            (await plugin.get_game_association_component(boundary_game_id))["success"],
            True,
        )
        self.assertEqual(
            (await plugin.detach_game_association_member(boundary_game_id))["error"][
                "code"
            ],
            "NOT_A_CHILD",
        )
        self.assertEqual(
            (await plugin.dissolve_game_association_component(boundary_game_id))[
                "error"
            ]["code"],
            "NOT_ASSOCIATED",
        )

        for method in (
            plugin.get_game_association_component,
            plugin.detach_game_association_member,
            plugin.dissolve_game_association_component,
        ):
            self.assertEqual(
                (await method("a" * 256))["error"]["code"], "INVALID_REQUEST"
            )

        member_ids = tuple(
            f"component-member-{index}"
            for index in range(MAX_ASSOCIATION_COMPONENT_MEMBERS + 1)
        )
        for game_id in member_ids:
            dao.save_game_dict(game_id, game_id.title())
            dao.save_game_checksum(game_id, "shared", "SHA256", 1, None, None)

        for method in (
            plugin.get_game_association_component,
            plugin.detach_game_association_member,
            plugin.dissolve_game_association_component,
        ):
            self.assertEqual(
                (await method(member_ids[0]))["error"]["code"], "INVALID_REQUEST"
            )

    async def test_association_component_confirmation_propagates_structured_errors(
        self,
    ):
        from py_modules.schemas.response import (
            AssociationComponentConfirmationOutcome,
            AssociationComponentError,
        )

        plugin = self.main.Plugin()
        await plugin._main()
        await plugin.set_current_user("76561198099999998")
        request = {
            "anchor_game_id": "alpha",
            "proposed_parent_game_id": "alpha",
            "proposed_parent_game_name": "Alpha",
            "expected_parent_game_id": None,
            "expected_fingerprint": "fingerprint",
            "selected_members": [{"game_id": "alpha", "game_name": "Alpha"}],
        }
        for code in (
            "ANCHOR_NOT_FOUND",
            "STALE_COMPONENT",
            "UNEXPECTED_MEMBER",
            "INCOMPLETE_MEMBER_SELECTION",
            "PARENT_NOT_MEMBER",
            "COMPONENT_CONFLICT",
            "INVALID_SELECTION",
            "ASSOCIATION_UPDATE_FAILED",
        ):
            with patch.object(
                type(plugin.association_manager),
                "confirm_association_component",
                return_value=AssociationComponentConfirmationOutcome(
                    confirmation=None,
                    error=AssociationComponentError(code=code, message="structured"),
                ),
            ):
                result = await plugin.confirm_game_association_component(request)

            self.assertEqual(
                result,
                {
                    "success": False,
                    "error": {"code": code, "message": "structured"},
                },
            )

    async def test_association_removal_rpcs_cover_success_malformed_and_errors(self):
        from py_modules.schemas.response import AssociationComponentError

        plugin = self.main.Plugin()
        await plugin._main()
        await plugin.set_current_user("76561198099999997")
        dao = plugin.association_manager.dao
        for game_id in ("alpha", "beta", "gamma"):
            dao.save_game_dict(game_id, game_id.title())
            dao.save_game_checksum(game_id, "shared", "SHA256", 1, None, None)
        dao.create_game_association("alpha", "beta")
        dao.create_game_association("alpha", "gamma")

        self.assertEqual(
            await plugin.detach_game_association_member("gamma"), {"success": True}
        )
        self.assertEqual(
            await plugin.dissolve_game_association_component("alpha"), {"success": True}
        )
        self.assertEqual(dao.get_all_game_associations(), [])

        for method in (
            plugin.detach_game_association_member,
            plugin.dissolve_game_association_component,
        ):
            malformed = await method(None)
            self.assertEqual(malformed["error"]["code"], "INVALID_REQUEST")

        for manager_method, rpc_method in (
            ("detach_association_member", plugin.detach_game_association_member),
            (
                "dissolve_association_component",
                plugin.dissolve_game_association_component,
            ),
        ):
            with patch.object(
                type(plugin.association_manager),
                manager_method,
                return_value=AssociationComponentError(
                    code="NOT_ASSOCIATED", message="structured"
                ),
            ):
                result = await rpc_method("alpha")

            self.assertEqual(
                result,
                {
                    "success": False,
                    "error": {"code": "NOT_ASSOCIATED", "message": "structured"},
                },
            )

    async def test_game_resolution_rpc_returns_bounded_camel_case_results(self):
        plugin = self.main.Plugin()
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory) / "Game.exe"
            payload.write_bytes(b"MZ")
            request = {
                "launcherKind": "direct",
                "classificationStatus": "recognized",
                "normalized": {
                    "flatpakAppId": None,
                    "shortcutExe": str(payload),
                    "shortcutLaunchOptions": None,
                    "shortcutStartDir": None,
                    "executableTokens": [str(payload)],
                    "launchOptionTokens": [],
                    "startDirTokens": [],
                    "commandTokens": [str(payload)],
                },
                "metadataCandidates": [],
            }
            response = await plugin.resolve_game_payloads([request])

        self.assertEqual(
            response,
            {
                "results": [
                    {
                        "launcherKind": "direct",
                        "classificationStatus": "recognized",
                        "metadataStatus": "not_requested",
                        "payloadStatus": "reachable",
                        "payloadKind": "file",
                        "provenance": "direct_executable",
                        "reasonCode": None,
                        "payloadPath": str(payload),
                    }
                ],
                "error": None,
            },
        )

        malformed = await plugin.resolve_game_payloads([request] * 33)
        self.assertEqual(malformed, {"results": [], "error": "malformed"})

    async def test_get_shortcut_app_details_returns_evidence(self):
        plugin = self.main.Plugin()
        await plugin._main()
        response = await plugin.get_shortcut_app_details(
            0x80000001 | 0x80000000
        )

        self.assertEqual(response, {"status": "failure", "reason": "missing-details"})

    async def test_get_shortcut_app_details_uses_catalog_request(self):
        plugin = self.main.Plugin()
        await plugin._main()
        fake_request = SimpleNamespace(
            request=SimpleNamespace(
                normalized=SimpleNamespace(
                    shortcut_exe='/usr/bin/flatpak',
                    shortcut_launch_options='run com.github.mtkennerly.ludusavi',
                    shortcut_start_dir=None,
                    flatpak_app_id='com.github.mtkennerly.ludusavi',
                )
            )
        )
        with patch.object(plugin.shortcut_catalog, "get_request", return_value=fake_request):
            response = await plugin.get_shortcut_app_details(3245664592)

        self.assertEqual(
            response,
            {
                "status": "success",
                "details": {
                    "strShortcutExe": "/usr/bin/flatpak",
                    "strShortcutLaunchOptions": "run com.github.mtkennerly.ludusavi",
                    "strFlatpakAppID": "com.github.mtkennerly.ludusavi",
                    "strShortcutStartDir": "",
                },
            },
        )

    async def test_game_resolution_rpc_preserves_entry_cardinality_on_failure(self):
        plugin = self.main.Plugin()
        entries = [{"malformed": True}, {"malformed": True}]
        with patch.object(
            plugin.game_resolution_coordinator,
            "resolve_batch",
            side_effect=RuntimeError("simulated unexpected failure"),
        ):
            response = await plugin.resolve_game_payloads(entries)

        self.assertEqual(
            response,
            {
                "results": [
                    {
                        "launcherKind": "unknown",
                        "classificationStatus": "unknown",
                        "metadataStatus": "not_requested",
                        "payloadStatus": "unknown",
                        "payloadKind": "unknown",
                        "provenance": "untrusted_hint",
                        "reasonCode": "probe_failure",
                        "payloadPath": None,
                    },
                    {
                        "launcherKind": "unknown",
                        "classificationStatus": "unknown",
                        "metadataStatus": "not_requested",
                        "payloadStatus": "unknown",
                        "payloadKind": "unknown",
                        "provenance": "untrusted_hint",
                        "reasonCode": "probe_failure",
                        "payloadPath": None,
                    },
                ],
                "error": None,
            },
        )


if __name__ == "__main__":
    unittest.main()
