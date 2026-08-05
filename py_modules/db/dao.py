from dataclasses import dataclass
import datetime
from hashlib import sha256
import sqlite3
from typing import Tuple, List, Dict, Optional, Collection

from py_modules.db.sqlite_db import SqlLiteDb
from py_modules.game_identity import (
    GameIdentityComponent,
    build_game_identity_components,
    canonical_game_name,
)
from py_modules.schemas.common import ChecksumAlgorithm, Game
from py_modules.schemas.request import (
    AssociationComponentConfirmationRequest,
    MAX_ASSOCIATION_COMPONENT_MEMBERS,
    MAX_ASSOCIATION_GAME_ID_LENGTH,
)
from py_modules.schemas.response import (
    AssociationComponentConfirmation,
    AssociationComponentError,
    AssociationComponentSnapshot,
    SessionInformation,
)


@dataclass(slots=True)
class GameTimeDto:
    game_id: str
    game_name: str
    time: int
    checksum: str


@dataclass(slots=True)
class DailyGameTimeDto:
    date: str
    game_id: str
    game_name: str
    time: int
    sessions: int
    checksum: str | None


@dataclass(slots=True)
class OverallGamesTimeDto:
    game_id: str
    game_name: str
    last_play_duration_time: float
    last_play_time_date: str
    time: int
    total_sessions: int


@dataclass(slots=True)
class GameInformationDto:
    game_id: str
    name: str
    time: float


@dataclass(slots=True)
class FileChecksum:
    checksum_id: int
    game_id: str
    game_name: str
    checksum: str
    algorithm: ChecksumAlgorithm
    chunk_size: int
    created_at: None | str
    updated_at: None | str


@dataclass(slots=True)
class GameDictionary:
    id: str
    name: str


@dataclass(slots=True)
class GamesChecksum:
    checksum_id: str
    game_id: str
    game_name: None | str
    checksum: str
    algorithm: ChecksumAlgorithm
    chunk_size: int
    created_at: None | str
    updated_at: None | str


@dataclass(slots=True)
class PlaytimeInformation:
    game_id: str
    total_time: float
    last_played_date: str | None
    game_name: str
    aliases_id: str | None


def _row_to_game_time_dto(cursor, row) -> GameTimeDto:
    """Maps row to GameTimeDto: (game_id, game_name, time, checksum)"""
    game_id, game_name, time, checksum = row
    return GameTimeDto(game_id, game_name, time, checksum)


def _row_to_playtime_information(cursor, row) -> PlaytimeInformation:
    """Maps row to PlaytimeInformation: (game_id, total_time, last_played_date, game_name, aliases_id)"""
    game_id, total_time, last_played_date, game_name, aliases_id = row
    return PlaytimeInformation(
        game_id, total_time, last_played_date, game_name, aliases_id
    )


def _row_to_daily_game_time_dto(cursor, row) -> DailyGameTimeDto:
    """Maps row to DailyGameTimeDto: (date, game_id, game_name, time, sessions, checksum)"""
    date, game_id, game_name, time, sessions, checksum = row
    return DailyGameTimeDto(date, game_id, game_name, time, sessions, checksum)


def _row_to_game_session_tuple(cursor, row) -> Tuple[str, SessionInformation]:
    """Maps row to (game_id, SessionInformation): (game_id, date, duration, migrated, checksum)"""
    game_id, date, duration, migrated, checksum = row
    return (game_id, SessionInformation(date, duration, migrated, checksum))


def _row_to_game_info_dto(cursor, row) -> GameInformationDto:
    """Maps row to GameInformationDto: (game_id, name, time)"""
    game_id, name, time = row
    return GameInformationDto(game_id, name, time)


def _row_to_game_dictionary(cursor, row) -> GameDictionary:
    """Maps row to GameDictionary: (id, name)"""
    id, name = row
    return GameDictionary(id, name)


def _row_to_file_checksum(cursor, row) -> FileChecksum:
    """Maps row to FileChecksum: (checksum_id, game_id, game_name, checksum, algorithm, chunk_size, created_at, updated_at)"""
    (
        checksum_id,
        game_id,
        game_name,
        checksum,
        algorithm,
        chunk_size,
        created_at,
        updated_at,
    ) = row
    return FileChecksum(
        checksum_id,
        game_id,
        game_name,
        checksum,
        algorithm,
        chunk_size,
        created_at,
        updated_at,
    )


def _row_to_games_checksum(cursor, row) -> GamesChecksum:
    """Maps row to GamesChecksum: (checksum_id, game_id, game_name, checksum, algorithm, chunk_size, created_at, updated_at)"""
    (
        checksum_id,
        game_id,
        game_name,
        checksum,
        algorithm,
        chunk_size,
        created_at,
        updated_at,
    ) = row
    return GamesChecksum(
        checksum_id,
        game_id,
        game_name,
        checksum,
        algorithm,
        chunk_size,
        created_at,
        updated_at,
    )


def _row_to_date_game_session_tuple(cursor, row) -> Tuple[str, str, SessionInformation]:
    """Maps row to (session_date, game_id, SessionInformation): (session_date, game_id, date_time, duration, migrated, checksum)"""
    session_date, game_id, date_time, duration, migrated, checksum = row
    return (
        session_date,
        game_id,
        SessionInformation(date_time, duration, migrated, checksum),
    )


class Dao:
    def __init__(self, db: SqlLiteDb):
        self._db = db

    def save_game_dict(self, game_id: str, game_name: str) -> None:
        connection: sqlite3.Connection

        with self._db.transactional() as connection:
            self._save_game_dict(connection, game_id, game_name)

    def save_play_time(
        self,
        start: datetime.datetime,
        time_s: int,
        game_id: str,
        source: str | None = None,
    ) -> None:
        with self._db.transactional() as connection:
            self._save_play_time(connection, start, time_s, game_id, source)

    def apply_manual_time_for_game(
        self,
        create_at: datetime.datetime,
        game_id: str,
        game_name: str,
        new_overall_time: float,
        source: str,
    ) -> None:
        with self._db.transactional() as connection:
            self._save_game_dict(connection, game_id, game_name)
            current_time = connection.execute(
                "SELECT sum(duration) FROM play_time WHERE game_id = ?", (game_id,)
            ).fetchone()[0]
            delta_time = new_overall_time - (
                current_time if current_time is not None else 0
            )
            if delta_time != 0:
                self._save_play_time(connection, create_at, delta_time, game_id, source)

    def fetch_per_day_time_report(
        self,
        begin: datetime.datetime,
        end: datetime.datetime,
        game_id: str | None = None,
    ) -> List[DailyGameTimeDto]:
        with self._db.transactional() as connection:
            components = self._get_game_identity_components(connection)
            component = components.get(game_id) if game_id is not None else None
            return self._fetch_per_day_time_report(
                connection,
                begin,
                end,
                component.members if component else ([game_id] if game_id else None),
            )

    def has_data_before(
        self, date: datetime.datetime, game_id: str | None = None
    ) -> bool:
        with self._db.transactional() as connection:
            return self._has_data_before(connection, date, game_id)

    def has_data_after(
        self, date: datetime.datetime, game_id: str | None = None
    ) -> bool:
        with self._db.transactional() as connection:
            return self._has_data_after(connection, date, game_id)

    def has_data_outside_range(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        game_ids: Collection[str] | None = None,
    ) -> tuple[bool, bool]:
        """Return whether any selected game has data before or after a range."""

        with self._db.transactional() as connection:
            if game_ids is None:
                row = connection.execute(
                    """
                    SELECT
                        EXISTS(SELECT 1 FROM play_time WHERE date_time < ?),
                        EXISTS(SELECT 1 FROM play_time WHERE date_time > ?)
                    """,
                    (start_date.isoformat(), end_date.isoformat()),
                ).fetchone()
            else:
                normalized_game_ids = tuple(sorted(set(game_ids)))
                if not normalized_game_ids:
                    return False, False

                placeholders = ", ".join("?" for _ in normalized_game_ids)
                row = connection.execute(
                    f"""
                    SELECT
                        EXISTS(
                            SELECT 1 FROM play_time
                            WHERE date_time < ? AND game_id IN ({placeholders})
                        ),
                        EXISTS(
                            SELECT 1 FROM play_time
                            WHERE date_time > ? AND game_id IN ({placeholders})
                        )
                    """,
                    (
                        start_date.isoformat(),
                        *normalized_game_ids,
                        end_date.isoformat(),
                        *normalized_game_ids,
                    ),
                ).fetchone()

            return row[0] == 1, row[1] == 1

    def _has_data_before(
        self,
        connection: sqlite3.Connection,
        date: datetime.datetime,
        game_id: str | None = None,
    ) -> bool:
        if game_id:
            return (
                connection.execute(
                    """
                    SELECT EXISTS(SELECT 1 FROM play_time pt WHERE date_time < ? AND pt.game_id = ?)
                    """,
                    (
                        date.isoformat(),
                        game_id,
                    ),
                ).fetchone()[0]
                == 1
            )

        return (
            connection.execute(
                """
                SELECT EXISTS(SELECT 1 FROM play_time pt WHERE date_time < ?)
                """,
                (date.isoformat(),),
            ).fetchone()[0]
            == 1
        )

    def _has_data_after(
        self,
        connection: sqlite3.Connection,
        date: datetime.datetime,
        game_id: str | None = None,
    ) -> bool:
        if game_id:
            return (
                connection.execute(
                    """
                    SELECT EXISTS(SELECT 1 FROM play_time pt WHERE date_time > ? AND pt.game_id = ?)
                    """,
                    (
                        date.isoformat(),
                        game_id,
                    ),
                ).fetchone()[0]
                == 1
            )

        return (
            connection.execute(
                """
                    SELECT EXISTS(SELECT 1 FROM play_time pt WHERE date_time > ?)
            """,
                (date.isoformat(),),
            ).fetchone()[0]
            == 1
        )

    def _save_game_dict(
        self, connection: sqlite3.Connection, game_id: str, game_name: str
    ):
        if game_name is None:
            raise ValueError(f"Cannot save game '{game_id}' with invalid name.")

        connection.execute(
            """
                INSERT INTO game_dict (game_id, name)
                VALUES (:game_id, :game_name)
                ON CONFLICT (game_id) DO UPDATE SET name = :game_name
                WHERE name != :game_name
                """,
            {"game_id": game_id, "game_name": game_name},
        )

    def get_game_identity_components(self) -> Dict[str, GameIdentityComponent]:
        with self._db.transactional() as connection:
            return self._get_game_identity_components(connection)

    def _get_game_identity_components(
        self, connection: sqlite3.Connection
    ) -> Dict[str, GameIdentityComponent]:
        game_ids = [
            row[0]
            for row in connection.execute("SELECT game_id FROM game_dict").fetchall()
        ]
        checksum_records = [
            (row[0], row[1], row[2])
            for row in connection.execute(
                "SELECT game_id, checksum, algorithm FROM game_file_checksum"
            ).fetchall()
        ]
        association_records = [
            (row[0], row[1])
            for row in connection.execute(
                "SELECT parent_game_id, child_game_id FROM game_association"
            ).fetchall()
        ]
        return build_game_identity_components(
            game_ids,
            checksum_records,
            association_records,
        )

    @staticmethod
    def game_association_component_fingerprint(member_ids: Collection[str]) -> str:
        """Return a stable optimistic-concurrency token for sorted member IDs."""

        return sha256("\x1f".join(sorted(set(member_ids))).encode()).hexdigest()

    @staticmethod
    def _validate_association_component_game_id(game_id: object, field: str) -> None:
        if (
            not isinstance(game_id, str)
            or not game_id
            or len(game_id) > MAX_ASSOCIATION_GAME_ID_LENGTH
        ):
            raise AssociationComponentError(
                code="INVALID_REQUEST",
                message=f"{field} must be a bounded non-empty string.",
            )

    def _validate_association_component_members(
        self, member_ids: Collection[str]
    ) -> tuple[str, ...]:
        members = tuple(member_ids)
        if len(members) > MAX_ASSOCIATION_COMPONENT_MEMBERS:
            raise AssociationComponentError(
                code="INVALID_REQUEST",
                message="The association component exceeds the maximum size.",
            )
        for member_id in members:
            self._validate_association_component_game_id(
                member_id, "component member game ID"
            )
        return members

    def _get_association_component_member_games(
        self,
        connection: sqlite3.Connection,
        member_ids: tuple[str, ...],
    ) -> tuple[Game, ...]:
        placeholders = ", ".join("?" for _ in member_ids)
        names_by_game_id = dict(
            connection.execute(
                f"SELECT game_id, name FROM game_dict WHERE game_id IN ({placeholders})",
                member_ids,
            ).fetchall()
        )
        return tuple(
            Game(game_id, names_by_game_id.get(game_id) or "Unknown Game")
            for game_id in member_ids
        )

    def get_game_association_component(
        self, anchor_game_id: str
    ) -> AssociationComponentSnapshot:
        self._validate_association_component_game_id(anchor_game_id, "anchor_game_id")
        with self._db.transactional() as connection:
            return self._get_game_association_component(connection, anchor_game_id)

    def _get_game_association_component(
        self,
        connection: sqlite3.Connection,
        anchor_game_id: str,
    ) -> AssociationComponentSnapshot:
        self._validate_association_component_game_id(anchor_game_id, "anchor_game_id")
        components = self._get_game_identity_components(connection)
        component = components.get(anchor_game_id)
        if component is None:
            raise AssociationComponentError(
                code="ANCHOR_NOT_FOUND",
                message="The association component anchor no longer exists.",
            )

        members = self._validate_association_component_members(component.members)
        existing_members = self._get_association_component_member_games(
            connection, members
        )
        expected_parent_game_id = (
            component.canonical_id if component.status == "confirmed" else None
        )
        return AssociationComponentSnapshot(
            anchor_game_id=anchor_game_id,
            expected_parent_game_id=expected_parent_game_id,
            existing_members=existing_members,
            fingerprint=self.game_association_component_fingerprint(members),
            status=component.status,
            aliases=component.aliases,
        )

    def confirm_game_association_component(
        self, request: AssociationComponentConfirmationRequest
    ) -> AssociationComponentConfirmation:
        """Atomically confirm a complete logical-game component's explicit star."""

        try:
            request.validate()
        except ValueError as error:
            raise AssociationComponentError(
                code="INVALID_REQUEST",
                message="The association component confirmation request is invalid.",
            ) from error

        try:
            with self._db.transactional() as connection:
                snapshot = self._get_game_association_component(
                    connection, request.anchor_game_id
                )
                component_member_ids = tuple(
                    member.id for member in snapshot.existing_members
                )
                selected_by_game_id = {
                    member.game_id: member for member in request.selected_members
                }
                selected_member_ids = tuple(sorted(selected_by_game_id))

                if request.expected_fingerprint != snapshot.fingerprint:
                    raise AssociationComponentError(
                        code="STALE_COMPONENT",
                        message="The association component changed before it was confirmed.",
                    )
                if request.expected_parent_game_id != snapshot.expected_parent_game_id:
                    raise AssociationComponentError(
                        code="STALE_COMPONENT",
                        message="The association component parent changed before confirmation.",
                    )
                missing_members = set(component_member_ids) - set(selected_member_ids)
                if snapshot.status == "conflict" and missing_members:
                    raise AssociationComponentError(
                        code="COMPONENT_CONFLICT",
                        message="Conflicted components require confirmation of every member.",
                    )
                if missing_members:
                    raise AssociationComponentError(
                        code="INCOMPLETE_MEMBER_SELECTION",
                        message="Confirmation must include every component member.",
                    )

                existing_member_ids = set(component_member_ids)
                added_member_ids = set(selected_member_ids) - existing_member_ids
                components = self._get_game_identity_components(connection)
                if any(game_id in components for game_id in added_member_ids):
                    raise AssociationComponentError(
                        code="UNEXPECTED_MEMBER",
                        message=(
                            "Selected additions must not already belong to another "
                            "identity component."
                        ),
                    )
                if request.proposed_parent_game_id not in selected_by_game_id:
                    raise AssociationComponentError(
                        code="PARENT_NOT_MEMBER",
                        message="The proposed parent must be a selected component member.",
                    )

                selected_parent = selected_by_game_id[request.proposed_parent_game_id]
                if selected_parent.game_name != request.proposed_parent_game_name:
                    raise AssociationComponentError(
                        code="INVALID_SELECTION",
                        message="The proposed parent name must match the selected member.",
                    )

                selected_members = tuple(
                    selected_by_game_id[game_id] for game_id in selected_member_ids
                )
                for member in selected_members:
                    self._save_game_dict(connection, member.game_id, member.game_name)

                placeholders = ", ".join("?" for _ in component_member_ids)
                connection.execute(
                    f"""
                    DELETE FROM game_association
                    WHERE parent_game_id IN ({placeholders})
                       OR child_game_id IN ({placeholders})
                    """,
                    component_member_ids + component_member_ids,
                )
                for child_game_id in selected_member_ids:
                    if child_game_id != request.proposed_parent_game_id:
                        self._create_game_association(
                            connection,
                            request.proposed_parent_game_id,
                            child_game_id,
                        )

                confirmed_snapshot = self._get_game_association_component(
                    connection, request.anchor_game_id
                )

                return AssociationComponentConfirmation(
                    anchor_game_id=request.anchor_game_id,
                    proposed_parent=Game(
                        request.proposed_parent_game_id,
                        request.proposed_parent_game_name,
                    ),
                    expected_parent_game_id=confirmed_snapshot.expected_parent_game_id,
                    existing_members=confirmed_snapshot.existing_members,
                    fingerprint=confirmed_snapshot.fingerprint,
                    selected_members=tuple(
                        Game(member.game_id, member.game_name)
                        for member in selected_members
                    ),
                    confirmed_parent=Game(
                        request.proposed_parent_game_id,
                        request.proposed_parent_game_name,
                    ),
                    status="confirmed",
                    aliases=confirmed_snapshot.aliases,
                )
        except AssociationComponentError:
            raise
        except Exception as error:
            raise AssociationComponentError(
                code="ASSOCIATION_UPDATE_FAILED",
                message="The association component could not be confirmed.",
            ) from error

    @staticmethod
    def _component_aliases(component: GameIdentityComponent) -> str | None:
        return ",".join(component.aliases) or None

    @staticmethod
    def _component_name(
        component: GameIdentityComponent,
        names_by_game_id: Dict[str, str],
    ) -> str:
        return canonical_game_name(component, names_by_game_id)

    def fetch_overall_playtime(self) -> List[GameTimeDto]:
        with self._db.transactional() as connection:
            return self._fetch_overall_playtime(connection)

    def _save_play_time(
        self,
        connection: sqlite3.Connection,
        start: datetime.datetime,
        time_s: float,
        game_id: str,
        source: str | None = None,
    ):
        connection.execute(
            """
                INSERT INTO play_time(date_time, duration, game_id, migrated)
                VALUES (?,?,?,?)
                """,
            (start.isoformat(), time_s, game_id, source),
        )
        self._append_overall_time(connection, game_id, time_s)

    # TODO: Add `_remove_play_time`

    def _append_overall_time(
        self, connection: sqlite3.Connection, game_id: str, delta_time_s: float
    ):
        connection.execute(
            """
                INSERT INTO overall_time (game_id, duration)
                VALUES (:game_id, :delta_time_s)
                ON CONFLICT (game_id)
                    DO UPDATE SET duration = duration + :delta_time_s
            """,
            {"game_id": game_id, "delta_time_s": delta_time_s},
        )

    def _fetch_overall_playtime(
        self,
        connection: sqlite3.Connection,
    ) -> List[GameTimeDto]:
        connection.row_factory = _row_to_game_time_dto

        return connection.execute(
            """
            SELECT
                ot.game_id,
                gd.name AS game_name,
                ot.duration,
                gfc.checksum
            FROM
                overall_time ot
            JOIN 
                game_dict gd ON ot.game_id = gd.game_id
            LEFT JOIN (
                SELECT game_id, MIN(checksum) AS checksum
                FROM game_file_checksum
                GROUP BY game_id
            ) gfc ON ot.game_id = gfc.game_id;
            """
        ).fetchall()

    def fetch_playtime_information(self) -> List[PlaytimeInformation]:
        with self._db.transactional() as connection:
            return self._fetch_playtime_information(connection)

    def _fetch_playtime_information(
        self,
        connection: sqlite3.Connection,
    ) -> List[PlaytimeInformation]:
        components = self._get_game_identity_components(connection)
        rows = connection.execute(
            """
            SELECT
                gd.game_id,
                gd.name,
                COALESCE(ot.duration, 0) AS total_duration,
                pt_agg.last_played_date
            FROM game_dict gd
            LEFT JOIN overall_time ot ON gd.game_id = ot.game_id
            LEFT JOIN (
                SELECT game_id, MAX(date_time) AS last_played_date
                FROM play_time
                GROUP BY game_id
            ) pt_agg ON gd.game_id = pt_agg.game_id
            """
        ).fetchall()

        stats_by_canonical_id: Dict[str, List[tuple[str, str, float, str | None]]] = {}
        for game_id, game_name, total_duration, last_played_date in rows:
            component = components[game_id]
            stats_by_canonical_id.setdefault(component.canonical_id, []).append(
                (game_id, game_name, total_duration, last_played_date)
            )

        information = []
        for game_stats in stats_by_canonical_id.values():
            component = components[game_stats[0][0]]
            names_by_game_id = {game_id: name for game_id, name, _, _ in game_stats}
            last_played_dates = [
                last_played_date
                for _, _, _, last_played_date in game_stats
                if last_played_date is not None
            ]
            information.append(
                PlaytimeInformation(
                    game_id=component.canonical_id,
                    total_time=sum(
                        total_duration for _, _, total_duration, _ in game_stats
                    ),
                    last_played_date=max(last_played_dates, default=None),
                    game_name=self._component_name(component, names_by_game_id),
                    aliases_id=self._component_aliases(component),
                )
            )

        return sorted(
            information,
            key=lambda item: (
                item.last_played_date is not None,
                item.last_played_date or "",
                item.game_id,
            ),
            reverse=True,
        )

    def fetch_playtime_information_for_period(
        self,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
    ) -> List[PlaytimeInformation]:
        with self._db.transactional() as connection:
            return self._fetch_playtime_information_for_period(
                connection, start_time, end_time
            )

    def fetch_statistics_data_batch(
        self,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
        game_ids: Collection[str] | None = None,
    ) -> tuple[
        List[DailyGameTimeDto],
        Dict[str, Dict[str, List[SessionInformation]]],
        Dict[str, SessionInformation],
    ]:
        with self._db.transactional() as connection:
            # Fetch daily reports
            daily_reports = self._fetch_per_day_time_report(
                connection, start_time, end_time, game_ids
            )

            # Extract game IDs
            game_ids_in_period = {report.game_id for report in daily_reports}

            # Fetch sessions for period
            sessions_by_day_and_game = self._fetch_sessions_for_period(
                connection, start_time, end_time, game_ids
            )

            # Fetch last sessions
            last_sessions_map = self._fetch_last_sessions_for_games(
                connection, game_ids_in_period
            )

            return daily_reports, sessions_by_day_and_game, last_sessions_map

    def _fetch_playtime_information_for_period(
        self,
        connection: sqlite3.Connection,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
    ) -> List[PlaytimeInformation]:
        components = self._get_game_identity_components(connection)
        rows = connection.execute(
            """
            SELECT
                gd.game_id,
                gd.name,
                COALESCE(SUM(CASE
                    WHEN pt.date_time >= :start AND pt.date_time < :end
                    THEN pt.duration
                    ELSE 0
                END), 0) AS period_duration,
                MAX(pt.date_time) AS last_played_date
            FROM game_dict gd
            LEFT JOIN play_time pt ON gd.game_id = pt.game_id
            GROUP BY gd.game_id, gd.name
            """,
            {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
        ).fetchall()

        stats_by_canonical_id: Dict[str, List[tuple[str, str, float, str | None]]] = {}
        for game_id, game_name, period_duration, last_played_date in rows:
            component = components[game_id]
            stats_by_canonical_id.setdefault(component.canonical_id, []).append(
                (game_id, game_name, period_duration, last_played_date)
            )

        information = []
        for game_stats in stats_by_canonical_id.values():
            total_time = sum(period_duration for _, _, period_duration, _ in game_stats)
            if total_time <= 0:
                continue

            component = components[game_stats[0][0]]
            names_by_game_id = {game_id: name for game_id, name, _, _ in game_stats}
            last_played_dates = [
                last_played_date
                for _, _, _, last_played_date in game_stats
                if last_played_date is not None
            ]
            information.append(
                PlaytimeInformation(
                    game_id=component.canonical_id,
                    total_time=total_time,
                    last_played_date=max(last_played_dates, default=None),
                    game_name=self._component_name(component, names_by_game_id),
                    aliases_id=self._component_aliases(component),
                )
            )

        return sorted(
            information,
            key=lambda item: (
                item.last_played_date is not None,
                item.last_played_date or "",
                item.game_id,
            ),
            reverse=True,
        )

    def _fetch_per_day_time_report(
        self,
        connection: sqlite3.Connection,
        begin: datetime.datetime,
        end: datetime.datetime,
        game_ids: Collection[str] | None = None,
    ) -> List[DailyGameTimeDto]:
        connection.row_factory = _row_to_daily_game_time_dto

        params: list[str] = [begin.isoformat(), end.isoformat()]
        game_id_filter = ""
        if game_ids is not None:
            selected_game_ids = sorted(set(game_ids))
            if not selected_game_ids:
                return []
            placeholders = ", ".join("?" for _ in selected_game_ids)
            game_id_filter = f"AND pt.game_id IN ({placeholders})"
            params.extend(selected_game_ids)

        return connection.execute(
            f"""
            SELECT
                STRFTIME('%Y-%m-%d', pt.date_time) AS date,
                pt.game_id,
                gd.name AS game_name,
                SUM(pt.duration) AS total_time,
                COUNT(*) AS sessions,
                gfc.checksum
            FROM play_time pt
            LEFT JOIN game_dict gd ON pt.game_id = gd.game_id
            LEFT JOIN (
                SELECT game_id, MIN(checksum) AS checksum
                FROM game_file_checksum
                GROUP BY game_id
            ) gfc ON gfc.game_id = pt.game_id
            WHERE pt.date_time BETWEEN ? AND ?
                AND pt.migrated IS NULL
                {game_id_filter}
            GROUP BY
                STRFTIME('%Y-%m-%d', pt.date_time),
                pt.game_id, gd.name
            ORDER BY date, game_name;
            """,
            params,
        ).fetchall()

    def fetch_all_game_sessions_report(self) -> List[tuple[str, SessionInformation]]:
        with self._db.transactional() as connection:
            connection.row_factory = _row_to_game_session_tuple

            return connection.execute(
                """
                SELECT
                    pt.game_id,
                    pt.date_time,
                    pt.duration,
                    pt.migrated,
                    gfc.checksum
                FROM
                    play_time pt
                LEFT JOIN
                    (
                        SELECT game_id, MIN(checksum) AS checksum
                        FROM game_file_checksum
                        GROUP BY game_id
                    ) gfc
                ON
                    pt.game_id = gfc.game_id
                ORDER BY
                    pt.game_id, pt.date_time;
            """
            ).fetchall()

    def fetch_all_last_playtime_session_information(
        self,
    ) -> Dict[str, SessionInformation]:
        with self._db.transactional() as connection:
            connection.row_factory = _row_to_game_session_tuple

            return dict(
                connection.execute(
                    """
                SELECT
                    pt.game_id,
                    pt.date_time,
                    pt.duration,
                    pt.migrated,
                    gfc.checksum
                FROM (
                    SELECT
                        *,
                        ROW_NUMBER() OVER (PARTITION BY game_id ORDER BY date_time DESC) AS rn
                    FROM play_time
                ) pt
                LEFT JOIN (
                    SELECT game_id, MIN(checksum) AS checksum
                    FROM game_file_checksum
                    GROUP BY game_id
                ) gfc ON gfc.game_id = pt.game_id
                WHERE pt.rn = 1;
                """
                ).fetchall()
            )

    def fetch_sessions_for_period(
        self,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
        game_id: Optional[str] = None,
    ) -> Dict[str, Dict[str, List[SessionInformation]]]:
        with self._db.transactional() as connection:
            components = self._get_game_identity_components(connection)
            component = components.get(game_id) if game_id is not None else None
            return self._fetch_sessions_for_period(
                connection,
                start_time,
                end_time,
                component.members if component else ([game_id] if game_id else None),
            )

    def _fetch_sessions_for_period(
        self,
        connection: sqlite3.Connection,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
        game_ids: Collection[str] | None = None,
    ) -> Dict[str, Dict[str, List[SessionInformation]]]:
        params: list[str] = [start_time.isoformat(), end_time.isoformat()]
        game_id_filter = ""
        if game_ids is not None:
            selected_game_ids = sorted(set(game_ids))
            if not selected_game_ids:
                return {}
            placeholders = ", ".join("?" for _ in selected_game_ids)
            game_id_filter = f"AND pt.game_id IN ({placeholders})"
            params.extend(selected_game_ids)

        query = f"""
            SELECT
                strftime('%Y-%m-%d', pt.date_time) as session_date,
                pt.game_id,
                pt.date_time,
                pt.duration,
                pt.migrated,
                gfc.checksum
            FROM
                play_time pt
            LEFT JOIN
                (
                    SELECT game_id, MIN(checksum) AS checksum
                    FROM game_file_checksum
                    GROUP BY game_id
                ) gfc ON pt.game_id = gfc.game_id
            WHERE
                pt.date_time >= ? AND pt.date_time < ?
                {game_id_filter}
            ORDER BY
                session_date, pt.game_id, pt.date_time;
            """

        sessions_by_day_and_game: Dict[str, Dict[str, List[SessionInformation]]] = {}

        connection.row_factory = _row_to_date_game_session_tuple

        rows = connection.execute(query, params).fetchall()

        for session_date, game_id_val, session_info in rows:
            if session_date not in sessions_by_day_and_game:
                sessions_by_day_and_game[session_date] = {}
            if game_id_val not in sessions_by_day_and_game[session_date]:
                sessions_by_day_and_game[session_date][game_id_val] = []
            sessions_by_day_and_game[session_date][game_id_val].append(session_info)

        return sessions_by_day_and_game

    def fetch_last_sessions_for_games(
        self,
        game_ids: Collection[str],
    ) -> Dict[str, SessionInformation]:
        with self._db.transactional() as connection:
            return self._fetch_last_sessions_for_games(
                connection,
                game_ids,
            )

    def _fetch_last_sessions_for_games(
        self,
        connection: sqlite3.Connection,
        game_ids: Collection[str],
    ) -> Dict[str, SessionInformation]:
        game_ids_list = sorted(set(game_ids))
        if not game_ids_list:
            return {}
        placeholders = ", ".join("?" for _ in game_ids_list)

        connection.row_factory = _row_to_game_session_tuple

        query = f"""
            SELECT
                pt.game_id,
                pt.date_time,
                pt.duration,
                pt.migrated,
                gfc.checksum
            FROM (
                SELECT
                    *,
                    ROW_NUMBER() OVER (PARTITION BY game_id ORDER BY date_time DESC) AS rn
                FROM play_time
                WHERE game_id IN ({placeholders})
            ) pt
            LEFT JOIN (
                SELECT game_id, MIN(checksum) AS checksum
                FROM game_file_checksum
                GROUP BY game_id
            ) gfc ON gfc.game_id = pt.game_id
            WHERE pt.rn = 1;
        """

        rows = connection.execute(query, game_ids_list).fetchall()

        return dict(rows)

    def get_game(self, game_id: str) -> GameInformationDto | None:
        with self._db.transactional() as connection:
            return self._get_game(connection, game_id)

    def get_games(self, game_ids: Collection[str]) -> Dict[str, GameInformationDto]:
        """Fetch dictionary and total-time records for a set of game IDs at once."""

        with self._db.transactional() as connection:
            normalized_game_ids = tuple(sorted(set(game_ids)))
            if not normalized_game_ids:
                return {}

            connection.row_factory = _row_to_game_info_dto
            placeholders = ", ".join("?" for _ in normalized_game_ids)
            rows = connection.execute(
                f"""
                SELECT
                    gd.game_id,
                    gd.name,
                    COALESCE(ot.duration, 0) AS time
                FROM game_dict gd
                LEFT JOIN overall_time ot ON gd.game_id = ot.game_id
                WHERE gd.game_id IN ({placeholders})
                """,
                normalized_game_ids,
            ).fetchall()

            return {game.game_id: game for game in rows}

    def _get_game(
        self, connection: sqlite3.Connection, game_id: str
    ) -> GameInformationDto | None:
        connection.row_factory = _row_to_game_info_dto

        return connection.execute(
            """
            SELECT
                gd.game_id,
                gd.name,
                ot.duration as time
            FROM
                game_dict gd
            INNER JOIN overall_time ot
                ON gd.game_id = ot.game_id
            WHERE
                gd.game_id = ?
            """,
            (game_id,),
        ).fetchone()

    def get_games_dictionary(self) -> List[GameDictionary]:
        with self._db.transactional() as connection:
            return self._get_games_dictionary(connection)

    def _get_games_dictionary(
        self, connection: sqlite3.Connection
    ) -> List[GameDictionary]:
        connection.row_factory = _row_to_game_dictionary

        return connection.execute(
            """
            SELECT
                gd.game_id,
                gd.name
            FROM
                game_dict gd;
            """,
        ).fetchall()

    def get_game_files_checksum(self, game_id: str) -> List[FileChecksum]:
        with self._db.transactional() as connection:
            return self._get_game_files_checksum(connection, game_id)

    def _get_game_files_checksum(
        self, connection: sqlite3.Connection, game_id: str
    ) -> List[FileChecksum]:
        connection.row_factory = _row_to_file_checksum

        return connection.execute(
            """
            SELECT
                gfc.checksum_id,
                gfc.game_id,
                gd.name,
                gfc.checksum,
                gfc.algorithm,
                gfc.chunk_size,
                gfc.created_at,
                gfc.updated_at
            FROM
                game_file_checksum gfc
            LEFT JOIN game_dict gd ON gd.game_id = gfc.game_id
            WHERE
                gfc.game_id = ?
            """,
            (game_id,),
        ).fetchall()

    def save_game_checksum(
        self,
        game_id: str,
        hash_checksum: str,
        hash_algorithm: str,
        hash_chunk_size: int,
        hash_created_at: None | str,
        hash_updated_at: None | str,
    ) -> None:
        with self._db.transactional() as connection:
            self._save_game_checksum(
                connection,
                game_id,
                hash_checksum,
                hash_algorithm,
                hash_chunk_size,
                hash_created_at,
                hash_updated_at,
            )

    def _save_game_checksum(
        self,
        connection: sqlite3.Connection,
        game_id: str,
        hash_checksum: str,
        hash_algorithm: str,
        hash_chunk_size: int,
        hash_created_at: None | str,
        hash_updated_at: None | str,
    ):
        connection.execute(
            """
                INSERT INTO game_file_checksum(game_id, checksum, algorithm, chunk_size, created_at, updated_at)
                VALUES (?, ?, ?, ?, IFNULL(?, CURRENT_TIMESTAMP), IFNULL(?, CURRENT_TIMESTAMP))
                """,
            (
                game_id,
                hash_checksum,
                hash_algorithm,
                hash_chunk_size,
                hash_created_at,
                hash_updated_at,
            ),
        )

    def save_game_checksum_bulk(
        self,
        checksums_data: List[Tuple[str, str, str, int, Optional[str], Optional[str]]],
    ) -> None:
        with self._db.transactional() as connection:
            self._save_game_checksum_bulk(connection, checksums_data)

    def _save_game_checksum_bulk(
        self,
        connection: sqlite3.Connection,
        checksums_data: List[Tuple[str, str, str, int, Optional[str], Optional[str]]],
    ):
        connection.executemany(
            """
            INSERT OR IGNORE INTO game_file_checksum(game_id, checksum, algorithm, chunk_size, created_at, updated_at)
            VALUES (?, ?, ?, ?, IFNULL(?, CURRENT_TIMESTAMP), IFNULL(?, CURRENT_TIMESTAMP))
            """,
            checksums_data,
        )

    def remove_game_checksum(
        self,
        game_id: str,
        checksum: str,
    ) -> None:
        with self._db.transactional() as connection:
            self._remove_game_checksum(
                connection,
                game_id,
                checksum,
            )

    def _remove_game_checksum(
        self,
        connection: sqlite3.Connection,
        game_id: str,
        checksum: str,
    ):
        connection.execute(
            """
                DELETE FROM game_file_checksum WHERE game_id = ? AND checksum = ?
                """,
            (
                game_id,
                checksum,
            ),
        )

    def remove_all_game_checksums(
        self,
        game_id: str,
    ) -> None:
        with self._db.transactional() as connection:
            self._remove_all_game_checksums(
                connection,
                game_id,
            )

    def _remove_all_game_checksums(
        self,
        connection: sqlite3.Connection,
        game_id: str,
    ):
        connection.execute(
            """
                DELETE FROM game_file_checksum WHERE game_id = ?
                """,
            (game_id,),
        )

    def get_games_checksum(
        self,
    ) -> List[GamesChecksum]:
        with self._db.transactional() as connection:
            return self._get_games_checksum(
                connection,
            )

    def _get_games_checksum(
        self,
        connection: sqlite3.Connection,
    ) -> List[GamesChecksum]:
        connection.row_factory = _row_to_games_checksum

        return connection.execute(
            """
            SELECT
                checksum_id,
                gfc.game_id,
                gd.name,
                checksum,
                algorithm,
                chunk_size,
                created_at,
                updated_at
            FROM
                game_file_checksum gfc
            LEFT JOIN
                game_dict gd
            ON gfc.game_id = gd.game_id;
            """,
        ).fetchall()

    def remove_all_checksums(
        self,
    ) -> int:
        with self._db.transactional() as connection:
            return self._remove_all_checksums(
                connection,
            )

    def _remove_all_checksums(
        self,
        connection: sqlite3.Connection,
    ) -> int:
        cursor = connection.execute(
            """
            DELETE
            FROM
                game_file_checksum;
            """,
        )

        return cursor.rowcount

    def link_game_to_game_with_checksum(
        self, child_game_id: str, parent_game_id: str
    ) -> None:
        with self._db.transactional() as connection:
            self._link_game_to_game_with_checksum(
                connection, child_game_id, parent_game_id
            )

    def _link_game_to_game_with_checksum(
        self,
        connection: sqlite3.Connection,
        child_game_id,
        parent_game_id,
    ):
        return connection.execute(
            """
                INSERT INTO game_file_checksum(game_id, checksum, algorithm, chunk_size)
                SELECT
                    ?,
                    gfc.checksum,
                    gfc.algorithm,
                    gfc.chunk_size
                FROM
                    game_file_checksum AS gfc
                WHERE
                    gfc.game_id = ?
                LIMIT 1;
                """,
            (
                child_game_id,
                parent_game_id,
            ),
        )

    def upsert_tracking_status(self, game_id: str, status: str) -> None:
        """Insert or update tracking status for a game."""
        with self._db.transactional() as connection:
            connection.execute(
                """
                INSERT INTO game_tracking_status (game_id, status, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(game_id) DO UPDATE SET
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (game_id, status),
            )

    def get_tracking_status(self, game_id: str) -> Optional[str]:
        """Get tracking status for a game. Returns None if not set (meaning default)."""
        with self._db.transactional() as connection:
            result = connection.execute(
                """
                SELECT status FROM game_tracking_status WHERE game_id = ?
                """,
                (game_id,),
            ).fetchone()
            return result[0] if result else None

    def delete_tracking_status(self, game_id: str) -> None:
        """Delete tracking status for a game (revert to default)."""
        with self._db.transactional() as connection:
            connection.execute(
                """
                DELETE FROM game_tracking_status WHERE game_id = ?
                """,
                (game_id,),
            )

    def get_all_tracking_configs(self) -> List[Dict[str, str]]:
        """Get all non-default tracking configurations with game names."""
        with self._db.transactional() as connection:
            rows = connection.execute(
                """
                SELECT gts.game_id, gd.name as game_name, gts.status
                FROM game_tracking_status gts
                JOIN game_dict gd ON gts.game_id = gd.game_id
                ORDER BY gd.name
                """
            ).fetchall()

            return [
                {
                    "game_id": row[0],
                    "game_name": row[1],
                    "status": row[2],
                }
                for row in rows
            ]

    def create_game_association(self, parent_game_id: str, child_game_id: str) -> None:
        with self._db.transactional() as connection:
            self._create_game_association(connection, parent_game_id, child_game_id)

    def _create_game_association(
        self,
        connection: sqlite3.Connection,
        parent_game_id: str,
        child_game_id: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO game_association (parent_game_id, child_game_id)
            VALUES (?, ?)
            """,
            (parent_game_id, child_game_id),
        )

    def remove_game_association(self, child_game_id: str) -> None:
        with self._db.transactional() as connection:
            self._remove_game_association(connection, child_game_id)

    def detach_game_association_member(self, child_game_id: str) -> None:
        """Detach one child while retaining all playtime and game records."""

        with self._db.transactional() as connection:
            self._get_game_association_component(connection, child_game_id)
            if self._is_game_a_parent(connection, child_game_id):
                raise AssociationComponentError(
                    code="PARENT_REQUIRES_CONFIRMATION",
                    message=(
                        "Removing a parent requires a replacement confirmation or "
                        "explicit dissolution."
                    ),
                )
            if not self._is_game_a_child(connection, child_game_id):
                raise AssociationComponentError(
                    code="NOT_A_CHILD",
                    message=f"Game '{child_game_id}' is not associated with any parent.",
                )
            self._remove_game_association(connection, child_game_id)

    def dissolve_game_association_component(self, anchor_game_id: str) -> None:
        """Delete all explicit edges in one component without deleting history."""

        with self._db.transactional() as connection:
            snapshot = self._get_game_association_component(connection, anchor_game_id)
            member_ids = tuple(member.id for member in snapshot.existing_members)
            placeholders = ", ".join("?" for _ in member_ids)
            result = connection.execute(
                f"""
                DELETE FROM game_association
                WHERE parent_game_id IN ({placeholders})
                   OR child_game_id IN ({placeholders})
                """,
                member_ids + member_ids,
            )
            if result.rowcount == 0:
                raise AssociationComponentError(
                    code="NOT_ASSOCIATED",
                    message="The association component has no explicit edges to dissolve.",
                )

    def _remove_game_association(
        self,
        connection: sqlite3.Connection,
        child_game_id: str,
    ) -> None:
        connection.execute(
            """
            DELETE FROM game_association WHERE child_game_id = ?
            """,
            (child_game_id,),
        )

    def get_game_association(self, game_id: str) -> Optional[Dict[str, str]]:
        with self._db.transactional() as connection:
            return self._get_game_association(connection, game_id)

    def _get_game_association(
        self,
        connection: sqlite3.Connection,
        game_id: str,
    ) -> Optional[Dict[str, str]]:
        row = connection.execute(
            """
            SELECT parent_game_id, child_game_id
            FROM game_association
            WHERE child_game_id = ?
            """,
            (game_id,),
        ).fetchone()

        if row:
            return {"parent_game_id": row[0], "child_game_id": row[1]}
        return None

    def is_game_a_child(self, game_id: str) -> bool:
        with self._db.transactional() as connection:
            return self._is_game_a_child(connection, game_id)

    def _is_game_a_child(
        self,
        connection: sqlite3.Connection,
        game_id: str,
    ) -> bool:
        result = connection.execute(
            """
            SELECT EXISTS(SELECT 1 FROM game_association WHERE child_game_id = ?)
            """,
            (game_id,),
        ).fetchone()
        return result[0] == 1

    def is_game_a_parent(self, game_id: str) -> bool:
        with self._db.transactional() as connection:
            return self._is_game_a_parent(connection, game_id)

    def _is_game_a_parent(
        self,
        connection: sqlite3.Connection,
        game_id: str,
    ) -> bool:
        result = connection.execute(
            """
            SELECT EXISTS(SELECT 1 FROM game_association WHERE parent_game_id = ?)
            """,
            (game_id,),
        ).fetchone()
        return result[0] == 1

    def get_children_of_parent(self, parent_game_id: str) -> List[str]:
        with self._db.transactional() as connection:
            return self._get_children_of_parent(connection, parent_game_id)

    def _get_children_of_parent(
        self,
        connection: sqlite3.Connection,
        parent_game_id: str,
    ) -> List[str]:
        rows = connection.execute(
            """
            SELECT child_game_id FROM game_association WHERE parent_game_id = ?
            """,
            (parent_game_id,),
        ).fetchall()
        return [row[0] for row in rows]

    def get_parent_of_child(self, child_game_id: str) -> Optional[str]:
        with self._db.transactional() as connection:
            return self._get_parent_of_child(connection, child_game_id)

    def _get_parent_of_child(
        self,
        connection: sqlite3.Connection,
        child_game_id: str,
    ) -> Optional[str]:
        row = connection.execute(
            """
            SELECT parent_game_id FROM game_association WHERE child_game_id = ?
            """,
            (child_game_id,),
        ).fetchone()
        return row[0] if row else None

    def get_all_game_associations(self) -> List[Dict[str, str]]:
        with self._db.transactional() as connection:
            return self._get_all_game_associations(connection)

    def _get_all_game_associations(
        self,
        connection: sqlite3.Connection,
    ) -> List[Dict[str, str]]:
        rows = connection.execute(
            """
            SELECT 
                ga.parent_game_id,
                pd.name as parent_game_name,
                ga.child_game_id,
                cd.name as child_game_name,
                ga.created_at
            FROM game_association ga
            LEFT JOIN game_dict pd ON ga.parent_game_id = pd.game_id
            LEFT JOIN game_dict cd ON ga.child_game_id = cd.game_id
            ORDER BY pd.name, cd.name
            """
        ).fetchall()

        return [
            {
                "parent_game_id": row[0],
                "parent_game_name": row[1],
                "child_game_id": row[2],
                "child_game_name": row[3],
                "created_at": row[4],
            }
            for row in rows
        ]

    def get_associated_game_ids(self, game_id: str) -> List[str]:
        with self._db.transactional() as connection:
            return self._get_associated_game_ids(connection, game_id)

    def _get_associated_game_ids(
        self,
        connection: sqlite3.Connection,
        game_id: str,
    ) -> List[str]:
        # Check if this game is a child
        parent_id = self._get_parent_of_child(connection, game_id)

        if parent_id:
            # Game is a child - get parent and all siblings
            children = self._get_children_of_parent(connection, parent_id)
            return [parent_id] + children

        # Check if this game is a parent
        children = self._get_children_of_parent(connection, game_id)
        if children:
            return [game_id] + children

        # No associations
        return [game_id]

    def get_combined_playtime_for_game(self, game_id: str) -> float:
        with self._db.transactional() as connection:
            return self._get_combined_playtime_for_game(connection, game_id)

    def _get_combined_playtime_for_game(
        self,
        connection: sqlite3.Connection,
        game_id: str,
    ) -> float:
        associated_ids = self._get_associated_game_ids(connection, game_id)
        placeholders = ", ".join("?" for _ in associated_ids)

        result = connection.execute(
            f"""
            SELECT COALESCE(SUM(duration), 0)
            FROM overall_time
            WHERE game_id IN ({placeholders})
            """,
            associated_ids,
        ).fetchone()

        return result[0] if result else 0.0
