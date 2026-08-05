import dataclasses
import unittest
from datetime import date, datetime
from unittest import mock

from py_modules.db.dao import Dao
from py_modules.db.migration import DbMigration
from py_modules.games import Games
from py_modules.schemas.common import Game
from py_modules.schemas.response import (
    DayStatistics,
    GamePlaytimeDetails,
    SessionInformation,
)
from py_modules.statistics import Statistics
from py_modules.tests.helpers import AbstractDatabaseTest


class GameIdentityProjectionTest(AbstractDatabaseTest):
    def setUp(self) -> None:
        super().setUp()
        DbMigration(db=self.database).migrate()
        self.dao = Dao(self.database)
        self.statistics = Statistics(self.dao, tracking_manager=None)

    def _save_identity_fixture(self) -> None:
        for game_id, name in [
            ("alpha", "Checksum Leader"),
            ("checksum-child", "Checksum Child"),
            ("explicit-parent", "Explicit Parent"),
        ]:
            self.dao.save_game_dict(game_id, name)
        self.dao.save_play_time(datetime(2025, 1, 1, 10, 0), 10, "alpha")
        self.dao.save_play_time(datetime(2025, 1, 1, 11, 0), 20, "checksum-child")
        for game_id in ["alpha", "checksum-child"]:
            self.dao.save_game_checksum(game_id, "shared", "SHA256", 1, None, None)
        self.dao.create_game_association("explicit-parent", "checksum-child")

    def test_explicit_parent_is_canonical_for_every_statistics_projection(self):
        self._save_identity_fixture()

        all_time = self.statistics.fetch_playtime_information()
        daily = self.statistics.daily_statistics_for_period(
            date(2025, 1, 1), date(2025, 1, 1)
        )
        overall = self.statistics.per_game_overall_statistic()
        game = Games(self.dao).get_by_id("checksum-child")

        self.assertEqual(
            [report["game"]["id"] for report in all_time], ["explicit-parent"]
        )
        self.assertEqual(all_time[0]["total_time"], 30)
        self.assertEqual(all_time[0]["aliases_id"], "alpha,checksum-child")
        self.assertEqual(daily.data[0].games[0].game.id, "explicit-parent")
        self.assertEqual(daily.data[0].games[0].total_time, 30)
        self.assertEqual(overall[0]["game"]["id"], "explicit-parent")
        self.assertEqual(overall[0]["total_time"], 30)
        self.assertIsNotNone(game)
        self.assertEqual(game.game.id, "explicit-parent")
        self.assertEqual(game.total_time, 30)

    def test_daily_projection_is_independent_of_report_order(self):
        self._save_identity_fixture()
        components = self.dao.get_game_identity_components()
        self.assertEqual(components["alpha"].canonical_id, "explicit-parent")
        alpha = GamePlaytimeDetails(
            game=Game("alpha", "Checksum Leader"),
            total_time=10,
            sessions=[SessionInformation("2025-01-01T10:00:00", 10, None, "shared")],
            last_session=SessionInformation("2025-01-01T10:00:00", 10, None, "shared"),
        )
        child = GamePlaytimeDetails(
            game=Game("checksum-child", "Checksum Child"),
            total_time=20,
            sessions=[SessionInformation("2025-01-01T11:00:00", 20, None, "shared")],
            last_session=SessionInformation("2025-01-01T11:00:00", 20, None, "shared"),
        )

        forward = self.statistics._combine_games_by_identity_per_day(
            [DayStatistics("2025-01-01", [alpha, child], 30)], components
        )
        reverse = self.statistics._combine_games_by_identity_per_day(
            [DayStatistics("2025-01-01", [child, alpha], 30)], components
        )

        self.assertEqual(dataclasses.asdict(forward[0]), dataclasses.asdict(reverse[0]))
        self.assertEqual(forward[0].games[0].game.id, "explicit-parent")
        self.assertEqual(forward[0].games[0].last_session.date, "2025-01-01T11:00:00")

    def _save_transitive_bridge_fixture(self) -> None:
        for game_id, name in [
            ("checksum-leader", "Checksum Leader"),
            ("bridge", "Bridge"),
            ("child", "Child"),
            ("explicit-parent", "Explicit Parent"),
        ]:
            self.dao.save_game_dict(game_id, name)

        for game_id, played_at, duration in [
            ("checksum-leader", datetime(2025, 1, 1, 10, 0), 10),
            ("bridge", datetime(2025, 1, 1, 11, 0), 30),
            ("child", datetime(2025, 1, 1, 12, 0), 20),
        ]:
            self.dao.save_play_time(played_at, duration, game_id)

        for game_id, checksum in [
            ("checksum-leader", "left"),
            ("bridge", "left"),
            ("bridge", "right"),
            ("child", "right"),
        ]:
            self.dao.save_game_checksum(game_id, checksum, "SHA256", 1, None, None)
        self.dao.create_game_association("explicit-parent", "child")

    def test_transitive_bridge_interval_is_counted_once_in_daily_and_overall(self):
        self._save_transitive_bridge_fixture()

        daily = self.statistics.daily_statistics_for_period(
            date(2025, 1, 1), date(2025, 1, 1), "bridge"
        )
        overall = self.statistics.per_game_overall_statistic()

        self.assertEqual(len(daily.data[0].games), 1)
        self.assertEqual(daily.data[0].total, 60)
        self.assertEqual(daily.data[0].games[0].total_time, 60)
        self.assertEqual(
            [session.date for session in daily.data[0].games[0].sessions],
            [
                "2025-01-01T12:00:00",
                "2025-01-01T11:00:00",
                "2025-01-01T10:00:00",
            ],
        )
        self.assertEqual(overall[0]["total_time"], 60)
        self.assertEqual(
            [session["date"] for session in overall[0]["sessions"]],
            [
                "2025-01-01T12:00:00",
                "2025-01-01T11:00:00",
                "2025-01-01T10:00:00",
            ],
        )

    def test_empty_canonical_name_is_normalized_in_every_projection(self):
        for game_id, game_name in [
            ("explicit-parent", ""),
            ("child", "Child"),
            ("fallback-parent", ""),
            ("fallback-child", "Fallback Child"),
        ]:
            self.dao.save_game_dict(game_id, game_name)
        self.dao.save_play_time(datetime(2025, 1, 1, 10, 0), 10, "explicit-parent")
        self.dao.save_play_time(datetime(2025, 1, 1, 11, 0), 20, "child")
        self.dao.save_play_time(datetime(2025, 1, 1, 12, 0), 30, "fallback-child")
        self.dao.create_game_association("explicit-parent", "child")
        self.dao.create_game_association("fallback-parent", "fallback-child")

        all_time = self.statistics.fetch_playtime_information()
        daily = self.statistics.daily_statistics_for_period(
            date(2025, 1, 1), date(2025, 1, 1)
        )
        overall = self.statistics.per_game_overall_statistic()
        dictionary = Games(self.dao).get_dictionary()

        all_time_names = {
            report["game"]["id"]: report["game"]["name"] for report in all_time
        }
        daily_names = {game.game.id: game.game.name for game in daily.data[0].games}
        overall_names = {
            report["game"]["id"]: report["game"]["name"] for report in overall
        }
        dictionary_names = {
            entry["game"]["id"]: entry["game"]["name"] for entry in dictionary
        }

        for canonical_id in ("explicit-parent", "fallback-parent"):
            self.assertEqual(all_time_names[canonical_id], "Unknown Game")
            self.assertEqual(daily_names[canonical_id], "Unknown Game")
            self.assertEqual(overall_names[canonical_id], "Unknown Game")
            self.assertEqual(dictionary_names[canonical_id], "Unknown Game")

    def test_identity_projections_batch_component_requests(self):
        self._save_transitive_bridge_fixture()

        with mock.patch.object(
            self.dao,
            "fetch_statistics_data_batch",
            wraps=self.dao.fetch_statistics_data_batch,
        ) as fetch_statistics_data_batch:
            self.statistics.daily_statistics_for_period(
                date(2025, 1, 1), date(2025, 1, 1), "bridge"
            )

        self.assertEqual(fetch_statistics_data_batch.call_count, 1)
        self.assertEqual(
            set(fetch_statistics_data_batch.call_args.args[2]),
            {"checksum-leader", "bridge", "child", "explicit-parent"},
        )

        with mock.patch.object(
            self.dao,
            "get_game",
            wraps=self.dao.get_game,
        ) as get_game:
            self.statistics.per_game_overall_statistic()

        self.assertEqual(get_game.call_count, 0)

        games = Games(self.dao)
        with mock.patch.object(
            self.dao,
            "get_game_files_checksum",
            wraps=self.dao.get_game_files_checksum,
        ) as get_game_files_checksum:
            games.get_dictionary()

        self.assertEqual(get_game_files_checksum.call_count, 0)


if __name__ == "__main__":
    unittest.main()
