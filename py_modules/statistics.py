from datetime import datetime, date, time, timedelta
from typing import Any, Dict, List, Optional
from py_modules.db.dao import DailyGameTimeDto, Dao, GameTimeDto
from py_modules.game_identity import canonical_game_name
from py_modules.helpers import format_date
from py_modules.schemas.common import Game
from py_modules.schemas.response import (
    DayStatistics,
    GamePlaytimeDetails,
    SessionInformation,
    PagedDayStatistics,
    GamePlaytimeReport,
)
from dataclasses import dataclass
from py_modules.helpers import start_of_week, end_of_week


@dataclass(slots=True)
class PlayTimeWithHash:
    game_id: str
    checksum: Optional[str]


class Statistics:
    __slots__ = ("dao", "tracking_manager", "association_manager")
    dao: Dao

    def __init__(
        self, dao: Dao, tracking_manager=None, association_manager=None
    ) -> None:
        self.dao = dao
        self.tracking_manager = tracking_manager
        self.association_manager = association_manager

    def _get_game_ids_with_children(
        self, game_id: Optional[str], components
    ) -> Optional[List[str]]:
        if not game_id:
            return None

        component = components.get(game_id)
        return list(component.members) if component else [game_id]

    def combine_games_by_checksum_per_day(
        self, days: List[DayStatistics]
    ) -> List[DayStatistics]:
        return self._combine_games_by_identity_per_day(
            days, self.dao.get_game_identity_components()
        )

    def _combine_games_by_identity_per_day(
        self, days: List[DayStatistics], components
    ) -> List[DayStatistics]:
        """Combine each day's reports using the shared canonical component map."""
        result_days = []
        game_names_by_id = {
            game.id: game.name for game in self.dao.get_games_dictionary()
        }

        for day in days:
            games_by_canonical_id: Dict[str, List[GamePlaytimeDetails]] = {}
            for gwt in day.games:
                component = components.get(gwt.game.id)
                canonical_id = component.canonical_id if component else gwt.game.id
                games_by_canonical_id.setdefault(canonical_id, []).append(gwt)

            merged_games: List[GamePlaytimeDetails] = []
            for canonical_id in sorted(games_by_canonical_id):
                game_group = games_by_canonical_id[canonical_id]
                component = components.get(canonical_id)
                if component:
                    canonical_game = Game(
                        canonical_id,
                        canonical_game_name(component, game_names_by_id),
                    )
                else:
                    fallback = min(game_group, key=lambda game: game.game.id).game
                    canonical_game = Game(
                        canonical_id,
                        fallback.name or "Unknown Game",
                    )
                all_sessions = [s for g in game_group for s in g.sessions]
                if len(game_group) > 1:
                    all_sessions.sort(key=lambda s: s.date, reverse=True)
                last_sessions: List[SessionInformation] = []
                for game in game_group:
                    if game.last_session is not None:
                        last_sessions.append(game.last_session)

                merged_games.append(
                    GamePlaytimeDetails(
                        game=canonical_game,
                        total_time=sum(game.total_time for game in game_group),
                        sessions=all_sessions,
                        last_session=(
                            max(last_sessions, key=lambda session: session.date)
                            if last_sessions
                            else None
                        ),
                    )
                )

            # Re-calculate total time for the day after merging
            total_day_time = sum(gwt.total_time for gwt in merged_games)
            result_days.append(
                DayStatistics(date=day.date, games=merged_games, total=total_day_time)
            )

        return result_days

    def _get_statistics_for_period(
        self,
        start_time: datetime,
        end_time: datetime,
        game_ids: Optional[List[str]] = None,
        components=None,
    ):
        daily_reports, sessions_by_day_and_game, last_sessions_map = (
            self.dao.fetch_statistics_data_batch(start_time, end_time, game_ids)
        )

        reports_by_date: Dict[str, List[DailyGameTimeDto]] = {}

        for report in daily_reports:
            if report.date not in reports_by_date:
                reports_by_date[report.date] = []
            reports_by_date[report.date].append(report)

        result_days: List[DayStatistics] = []

        for day in self._generate_date_range(start_time, end_time):
            date_str = format_date(day)

            day_games: List[GamePlaytimeDetails] = []
            total_day_time = 0.0

            for report in reports_by_date.get(date_str, []):
                # Retrieve pre-fetched data from our lookups (fast, no DB call)
                game_sessions = sessions_by_day_and_game.get(date_str, {}).get(
                    report.game_id, []
                )
                last_session = last_sessions_map.get(report.game_id)

                day_games.append(
                    GamePlaytimeDetails(
                        game=Game(report.game_id, report.game_name),
                        total_time=report.time,
                        sessions=game_sessions,
                        last_session=last_session,
                    )
                )
                total_day_time += report.time

            result_days.append(
                DayStatistics(date=date_str, games=day_games, total=total_day_time)
            )

        return self._combine_games_by_identity_per_day(
            result_days,
            components
            if components is not None
            else self.dao.get_game_identity_components(),
        )

    def daily_statistics_for_period(
        self, start: date, end: date, game_id: Optional[str] = None
    ) -> PagedDayStatistics:
        start_time = datetime.combine(start, time.min)
        end_time = datetime.combine(end, time.max)

        components = self.dao.get_game_identity_components()
        game_ids = self._get_game_ids_with_children(game_id, components)

        combined_data = self._get_statistics_for_period(
            start_time,
            end_time,
            game_ids,
            components,
        )

        # For has_prev/has_next, check any of the game IDs
        has_prev = False
        has_next = False
        if game_ids:
            for gid in game_ids:
                if self.dao.has_data_before(start_time, gid):
                    has_prev = True
                if self.dao.has_data_after(end_time, gid):
                    has_next = True
                if has_prev and has_next:
                    break
        else:
            has_prev = self.dao.has_data_before(start_time, None)
            has_next = self.dao.has_data_after(end_time, None)

        return PagedDayStatistics(
            data=combined_data,
            has_prev=has_prev,
            has_next=has_next,
        )

    def get_last_sessions_from_grouped_sessions(
        self, sessions_by_checksum: Dict[str, List[SessionInformation]]
    ) -> Dict[str, SessionInformation]:
        """
        Gets the last session for each checksum from the grouped sessions.
        Returns a dictionary mapping checksum to the most recent SessionInformation based on date.
        """
        last_sessions_by_checksum: Dict[str, SessionInformation] = {}

        for checksum, sessions in sessions_by_checksum.items():
            if sessions:
                last_session = max(
                    sessions,
                    key=lambda s: datetime.fromisoformat(s.date.replace("Z", "+00:00")),
                )
                last_sessions_by_checksum[checksum] = last_session

        return last_sessions_by_checksum

    def get_statistics_for_last_two_weeks(self):
        now = datetime.now()

        start_current_week = start_of_week(now)
        two_weeks_ago_start = start_current_week - timedelta(weeks=1)

        two_weeks_ago_end = end_of_week(now)

        information_list = self.dao.fetch_playtime_information_for_period(
            two_weeks_ago_start, two_weeks_ago_end
        )

        visibility_map = {}
        if self.tracking_manager:
            game_ids = [info.game_id for info in information_list]
            visibility_map = self.tracking_manager.get_bulk_visibility(game_ids)

        results = []
        for information in information_list:
            if self.tracking_manager and not visibility_map.get(
                information.game_id, True
            ):
                continue

            results.append(
                GamePlaytimeReport(
                    game=Game(information.game_id, information.game_name),
                    total_time=information.total_time,
                    last_played_date=information.last_played_date,
                    aliases_id=information.aliases_id,
                ).to_dict()
            )
        return results

    def fetch_playtime_information(self) -> List[dict[str, GamePlaytimeReport]]:
        information_list = self.dao.fetch_playtime_information()

        visibility_map = {}
        if self.tracking_manager:
            game_ids = [info.game_id for info in information_list]
            visibility_map = self.tracking_manager.get_bulk_visibility(game_ids)

        results = []
        for information in information_list:
            if self.tracking_manager and not visibility_map.get(
                information.game_id, True
            ):
                continue

            results.append(
                GamePlaytimeReport(
                    game=Game(information.game_id, information.game_name),
                    total_time=information.total_time,
                    last_played_date=information.last_played_date,
                    aliases_id=information.aliases_id,
                ).to_dict()
            )
        return results

    def per_game_overall_statistic(self) -> List[Dict[str, Any]]:
        """
        Returns overall statistics grouped by the canonical game identity component.
        Filters out games based on tracking status (hidden/ignore are excluded).
        """
        data = self.dao.fetch_overall_playtime()
        all_sessions = self.dao.fetch_all_game_sessions_report()
        components = self.dao.get_game_identity_components()
        game_names_by_id = {
            game.id: game.name for game in self.dao.get_games_dictionary()
        }

        games_by_canonical_id: Dict[str, List[GameTimeDto]] = {}

        for game_stat in data:
            component = components.get(game_stat.game_id)
            canonical_id = component.canonical_id if component else game_stat.game_id
            games_by_canonical_id.setdefault(canonical_id, []).append(game_stat)

        sessions_by_canonical_id: Dict[str, List[SessionInformation]] = {}

        for game_id, session in all_sessions:
            component = components.get(game_id)
            canonical_id = component.canonical_id if component else game_id
            sessions_by_canonical_id.setdefault(canonical_id, []).append(
                SessionInformation(
                    date=session.date,
                    duration=session.duration,
                    migrated=session.migrated,
                    checksum=session.checksum,
                )
            )

        visibility_map = {}
        if self.tracking_manager:
            game_ids = list(games_by_canonical_id)
            visibility_map = self.tracking_manager.get_bulk_visibility(game_ids)

        results = []
        for canonical_id, game_stats in games_by_canonical_id.items():
            if self.tracking_manager and not visibility_map.get(canonical_id, True):
                continue

            component = components.get(canonical_id)
            if component:
                game = Game(
                    canonical_id,
                    canonical_game_name(component, game_names_by_id),
                )
            else:
                fallback = min(game_stats, key=lambda game_stat: game_stat.game_id)
                game = Game(canonical_id, fallback.game_name or "Unknown Game")

            sessions = sessions_by_canonical_id.get(canonical_id, [])
            if len(game_stats) > 1:
                sessions.sort(key=lambda session: session.date, reverse=True)
            results.append(
                GamePlaytimeDetails(
                    game=game,
                    total_time=sum(game_stat.time for game_stat in game_stats),
                    sessions=sessions,
                    last_session=(
                        max(sessions, key=lambda session: session.date)
                        if sessions
                        else None
                    ),
                ).to_dict()
            )
        return results

    def _generate_date_range(self, start_date, end_date):
        curr_date = start_date
        while curr_date <= end_date:
            yield curr_date
            curr_date += timedelta(days=1)
