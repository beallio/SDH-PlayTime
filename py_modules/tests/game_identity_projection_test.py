import dataclasses
import unittest
from datetime import date, datetime

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


if __name__ == "__main__":
    unittest.main()
