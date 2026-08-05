from datetime import datetime, date, time, timedelta
from typing import Dict, List, Any, Optional
from py_modules.db.dao import DailyGameTimeDto, Dao, GameTimeDto
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
        self, game_id: Optional[str]
    ) -> Optional[List[str]]:
        if not game_id:
            return None

        component = self.dao.get_game_identity_components().get(game_id)
        return list(component.members) if component else [game_id]

    def combine_games_by_association(self, games_data: List[Any]) -> List[Any]:
        if not self.association_manager:
            return games_data

        all_associations = self.dao.get_all_game_associations()
        if not all_associations:
            return games_data

        parent_to_children: Dict[str, List[str]] = {}
        child_to_parent: Dict[str, str] = {}

        for assoc in all_associations:
            parent_id = assoc["parent_game_id"]
            child_id = assoc["child_game_id"]
            child_to_parent[child_id] = parent_id
            if parent_id not in parent_to_children:
                parent_to_children[parent_id] = []
            parent_to_children[parent_id].append(child_id)

        games_by_id: Dict[str, Any] = {}
        for game in games_data:
            game_id = (
                game.game.id
                if hasattr(game, "game")
                else game.get("game", {}).get("id")
            )
            if game_id:
                games_by_id[game_id] = game

        result = []
        processed_children = set()

        for game in games_data:
            game_id = (
                game.game.id
                if hasattr(game, "game")
                else game.get("game", {}).get("id")
            )

            if game_id in child_to_parent:
                processed_children.add(game_id)
                continue

            if game_id in parent_to_children:
                children_ids = parent_to_children[game_id]
                merged_game = self._merge_associated_games(
                    game, children_ids, games_by_id
                )
                result.append(merged_game)
            else:
                result.append(game)

        return result

    def _merge_associated_games(
        self, parent_game: Any, children_ids: List[str], games_by_id: Dict[str, Any]
    ) -> Any:
        total_time = (
            parent_game.total_time
            if hasattr(parent_game, "total_time")
            else parent_game.get("totalTime", 0)
        )
        all_sessions = list(
            parent_game.sessions
            if hasattr(parent_game, "sessions")
            else parent_game.get("sessions", [])
        )

        for child_id in children_ids:
            if child_id in games_by_id:
                child = games_by_id[child_id]
                child_time = (
                    child.total_time
                    if hasattr(child, "total_time")
                    else child.get("totalTime", 0)
                )
                total_time += child_time
                child_sessions = (
                    child.sessions
                    if hasattr(child, "sessions")
                    else child.get("sessions", [])
                )
                all_sessions.extend(child_sessions)

        all_sessions.sort(
            key=lambda s: s.date if hasattr(s, "date") else s.get("date", ""),
            reverse=True,
        )

        if hasattr(parent_game, "game"):
            return GamePlaytimeDetails(
                game=parent_game.game,
                total_time=total_time,
                sessions=all_sessions,
                last_session=parent_game.last_session,
            )
        else:
            return {
                **parent_game,
                "totalTime": total_time,
                "sessions": all_sessions,
            }

    def _apply_associations_to_playtime_info(self, information_list: List) -> List:
        if not information_list:
            return information_list

        all_associations = self.dao.get_all_game_associations()
        if not all_associations:
            return information_list

        parent_to_children: Dict[str, List[str]] = {}
        child_to_parent: Dict[str, str] = {}
        parent_names: Dict[str, str] = {}

        for assoc in all_associations:
            parent_id = assoc["parent_game_id"]
            child_id = assoc["child_game_id"]
            parent_name = assoc.get("parent_game_name")
            parent_names[parent_id] = parent_name if parent_name else "Unknown Game"

            child_to_parent[child_id] = parent_id
            if parent_id not in parent_to_children:
                parent_to_children[parent_id] = []
            parent_to_children[parent_id].append(child_id)

        games_by_id: Dict[str, Any] = {}
        for info in information_list:
            games_by_id[info.game_id] = info

        result = []
        processed_children = set()

        for info in information_list:
            game_id = info.game_id

            if game_id in child_to_parent:
                processed_children.add(game_id)
                continue

            if game_id in parent_to_children:
                merged_info = self._merge_playtime_info(
                    info, parent_to_children[game_id], games_by_id
                )
                result.append(merged_info)
            else:
                result.append(info)

        # Add parents that didn't have their own playtime
        from py_modules.db.dao import PlaytimeInformation

        for parent_id, children_ids in parent_to_children.items():
            if parent_id not in games_by_id:
                # Create a blank parent info to merge children into
                game_name = parent_names.get(parent_id, "Unknown Game")
                parent_info = PlaytimeInformation(
                    game_id=parent_id,
                    total_time=0.0,
                    last_played_date="",
                    game_name=game_name,
                    aliases_id=None,
                )
                merged_info = self._merge_playtime_info(
                    parent_info, children_ids, games_by_id
                )
                if merged_info.total_time > 0:
                    result.append(merged_info)

        return result

    def _merge_playtime_info(
        self,
        parent_info,
        children_ids: List[str],
        games_by_id: Dict[str, Any],
    ):
        from py_modules.db.dao import PlaytimeInformation

        total_time = parent_info.total_time
        last_played_date = parent_info.last_played_date
        aliases = []

        for child_id in children_ids:
            if child_id in games_by_id:
                child = games_by_id[child_id]
                total_time += child.total_time
                if child.last_played_date and (
                    not last_played_date or child.last_played_date > last_played_date
                ):
                    last_played_date = child.last_played_date
                aliases.append(child_id)

        existing_aliases = (
            parent_info.aliases_id.split(",") if parent_info.aliases_id else []
        )
        all_aliases = list(set(existing_aliases + aliases))
        aliases_str = ",".join(all_aliases) if all_aliases else None

        return PlaytimeInformation(
            game_id=parent_info.game_id,
            total_time=total_time,
            last_played_date=last_played_date,
            game_name=parent_info.game_name,
            aliases_id=aliases_str,
        )

    def _apply_associations_to_daily_statistics(
        self, days: List[DayStatistics]
    ) -> List[DayStatistics]:
        all_associations = self.dao.get_all_game_associations()
        if not all_associations:
            return days

        parent_to_children: Dict[str, List[str]] = {}
        child_to_parent: Dict[str, str] = {}

        for assoc in all_associations:
            parent_id = assoc["parent_game_id"]
            child_id = assoc["child_game_id"]
            child_to_parent[child_id] = parent_id
            if parent_id not in parent_to_children:
                parent_to_children[parent_id] = []
            parent_to_children[parent_id].append(child_id)

        result_days = []

        for day in days:
            games_by_id: Dict[str, GamePlaytimeDetails] = {}
            for game in day.games:
                games_by_id[game.game.id] = game

            merged_games: List[GamePlaytimeDetails] = []
            processed_parents: set = set()

            for game in day.games:
                game_id = game.game.id

                if game_id in child_to_parent:
                    parent_id = child_to_parent[game_id]

                    if (
                        parent_id not in processed_parents
                        and parent_id not in games_by_id
                    ):
                        parent_game_info = self.dao.get_game(parent_id)
                        if parent_game_info:
                            total_time = 0.0
                            all_sessions: List[SessionInformation] = []
                            last_session = None

                            for child_id in parent_to_children.get(parent_id, []):
                                if child_id in games_by_id:
                                    child = games_by_id[child_id]
                                    total_time += child.total_time
                                    all_sessions.extend(child.sessions)
                                    if child.last_session:
                                        if (
                                            not last_session
                                            or child.last_session.date
                                            > last_session.date
                                        ):
                                            last_session = child.last_session

                            if total_time > 0:
                                all_sessions.sort(key=lambda s: s.date, reverse=True)
                                merged_games.append(
                                    GamePlaytimeDetails(
                                        game=Game(parent_id, parent_game_info.name),
                                        total_time=total_time,
                                        sessions=all_sessions,
                                        last_session=last_session,
                                    )
                                )
                            processed_parents.add(parent_id)
                    continue

                if game_id in parent_to_children:
                    processed_parents.add(game_id)
                    total_time = game.total_time
                    all_sessions = list(game.sessions)
                    last_session = game.last_session

                    for child_id in parent_to_children[game_id]:
                        if child_id in games_by_id:
                            child = games_by_id[child_id]
                            total_time += child.total_time
                            all_sessions.extend(child.sessions)

                            if child.last_session:
                                if not last_session:
                                    last_session = child.last_session
                                elif child.last_session.date > last_session.date:
                                    last_session = child.last_session

                    all_sessions.sort(key=lambda s: s.date, reverse=True)

                    merged_games.append(
                        GamePlaytimeDetails(
                            game=game.game,
                            total_time=total_time,
                            sessions=all_sessions,
                            last_session=last_session,
                        )
                    )
                else:
                    merged_games.append(game)

            total_day_time = sum(g.total_time for g in merged_games)
            result_days.append(
                DayStatistics(date=day.date, games=merged_games, total=total_day_time)
            )

        return result_days

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
                canonical_game = next(
                    (game.game for game in game_group if game.game.id == canonical_id),
                    None,
                )
                if canonical_game is None:
                    canonical_name = game_names_by_id.get(canonical_id)
                    if canonical_name is not None:
                        canonical_game = Game(
                            canonical_id, canonical_name or "Unknown Game"
                        )
                    else:
                        canonical_game = min(
                            game_group, key=lambda game: game.game.id
                        ).game
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
    ):
        if game_ids and len(game_ids) > 1:
            daily_reports, sessions_by_day_and_game, last_sessions_map = (
                self.dao.fetch_statistics_data_batch(start_time, end_time, None)
            )
            game_ids_set = set(game_ids)
            daily_reports = [r for r in daily_reports if r.game_id in game_ids_set]
            filtered_sessions: Dict[str, Dict[str, List[SessionInformation]]] = {}
            for date_str, games_dict in sessions_by_day_and_game.items():
                filtered_sessions[date_str] = {
                    gid: sessions
                    for gid, sessions in games_dict.items()
                    if gid in game_ids_set
                }
            sessions_by_day_and_game = filtered_sessions
            last_sessions_map = {
                gid: session
                for gid, session in last_sessions_map.items()
                if gid in game_ids_set
            }
        else:
            fetch_game_id = game_ids[0] if game_ids else None
            daily_reports, sessions_by_day_and_game, last_sessions_map = (
                self.dao.fetch_statistics_data_batch(
                    start_time, end_time, fetch_game_id
                )
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

        components = self.dao.get_game_identity_components()
        return self._combine_games_by_identity_per_day(result_days, components)

    def daily_statistics_for_period(
        self, start: date, end: date, game_id: Optional[str] = None
    ) -> PagedDayStatistics:
        start_time = datetime.combine(start, time.min)
        end_time = datetime.combine(end, time.max)

        game_ids = self._get_game_ids_with_children(game_id)

        combined_data = self._get_statistics_for_period(start_time, end_time, game_ids)

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

            canonical_game_stat = next(
                (
                    game_stat
                    for game_stat in game_stats
                    if game_stat.game_id == canonical_id
                ),
                None,
            )
            canonical_game_info = self.dao.get_game(canonical_id)
            if canonical_game_stat:
                game = Game(canonical_game_stat.game_id, canonical_game_stat.game_name)
            elif canonical_game_info:
                game = Game(canonical_game_info.game_id, canonical_game_info.name)
            elif canonical_id in game_names_by_id:
                game = Game(
                    canonical_id,
                    game_names_by_id[canonical_id] or "Unknown Game",
                )
            else:
                fallback = min(game_stats, key=lambda game_stat: game_stat.game_id)
                game = Game(canonical_id, fallback.game_name)

            sessions = sessions_by_canonical_id.get(canonical_id, [])
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

    def _merge_game_details(
        self,
        parent: GamePlaytimeDetails,
        children_ids: List[str],
        games_by_id: Dict[str, GamePlaytimeDetails],
    ) -> GamePlaytimeDetails:
        total_time = parent.total_time
        all_sessions = list(parent.sessions)
        last_session = parent.last_session

        for child_id in children_ids:
            if child_id in games_by_id:
                child = games_by_id[child_id]
                total_time += child.total_time
                all_sessions.extend(child.sessions)

                if child.last_session:
                    if not last_session:
                        last_session = child.last_session
                    elif child.last_session.date > last_session.date:
                        last_session = child.last_session

        all_sessions.sort(key=lambda s: s.date, reverse=True)

        return GamePlaytimeDetails(
            game=parent.game,
            total_time=total_time,
            sessions=all_sessions,
            last_session=last_session,
        )

    def _generate_date_range(self, start_date, end_date):
        curr_date = start_date
        while curr_date <= end_date:
            yield curr_date
            curr_date += timedelta(days=1)
