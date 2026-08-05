from dataclasses import dataclass
from typing import List, Dict, Any, Literal
from .common import ChecksumAlgorithm, Game


@dataclass(slots=True)
class SessionInformation:
    date: str
    duration: float
    migrated: str | None
    checksum: str | None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "duration": self.duration,
            "migrated": self.migrated,
            "checksum": self.checksum,
        }


@dataclass(slots=True)
class GamePlaytimeSummary:
    game: Game
    total_time: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "game": {"id": self.game.id, "name": self.game.name},
            "total_time": self.total_time,
        }


@dataclass(slots=True)
class GamePlaytimeDetails(GamePlaytimeSummary):
    sessions: List[SessionInformation]
    last_session: SessionInformation | None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "game": {"id": self.game.id, "name": self.game.name},
            "total_time": self.total_time,
            "sessions": [s.to_dict() for s in self.sessions],
            "last_session": self.last_session.to_dict() if self.last_session else None,
        }


@dataclass(slots=True)
class GamePlaytimeReport(GamePlaytimeSummary):
    last_played_date: str | None
    aliases_id: str | None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "game": {"id": self.game.id, "name": self.game.name},
            "total_time": self.total_time,
            "last_played_date": self.last_played_date,
            "aliases_id": self.aliases_id,
        }


@dataclass(slots=True)
class DayStatistics:
    date: str
    games: List[GamePlaytimeDetails]
    total: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "games": [g.to_dict() for g in self.games],
            "total": self.total,
        }


@dataclass(slots=True)
class PagedDayStatistics:
    data: List[DayStatistics]
    has_prev: bool
    has_next: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data": [d.to_dict() for d in self.data],
            "has_prev": self.has_prev,
            "has_next": self.has_next,
        }


@dataclass(slots=True)
class FileChecksum:
    game: Game
    checksum: str
    algorithm: ChecksumAlgorithm
    chunk_size: int
    created_at: None | str
    updated_at: None | str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "game": {"id": self.game.id, "name": self.game.name},
            "checksum": self.checksum,
            "algorithm": self.algorithm,
            "chunk_size": self.chunk_size,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class GameDictionary:
    game: Game
    files: List[FileChecksum]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "game": {"id": self.game.id, "name": self.game.name},
            "files": [f.to_dict() for f in self.files],
        }


@dataclass(slots=True)
class AssociationComponentError(Exception):
    code: str
    message: str

    def to_dict(self) -> Dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class AssociationComponentSnapshot:
    anchor_game_id: str
    expected_parent_game_id: str | None
    existing_members: tuple[Game, ...]
    fingerprint: str
    status: Literal["confirmed", "unconfirmed", "conflict"]
    aliases: tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anchor_game_id": self.anchor_game_id,
            "expected_parent_game_id": self.expected_parent_game_id,
            "existing_members": [
                {"game_id": member.id, "game_name": member.name}
                for member in self.existing_members
            ],
            "fingerprint": self.fingerprint,
            "status": self.status,
            "aliases": list(self.aliases),
        }


@dataclass(frozen=True, slots=True)
class AssociationComponentConfirmation:
    anchor_game_id: str
    proposed_parent: Game
    expected_parent_game_id: str | None
    existing_members: tuple[Game, ...]
    fingerprint: str
    selected_members: tuple[Game, ...]
    confirmed_parent: Game
    status: Literal["confirmed"]
    aliases: tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anchor_game_id": self.anchor_game_id,
            "proposed_parent": {
                "game_id": self.proposed_parent.id,
                "game_name": self.proposed_parent.name,
            },
            "expected_parent_game_id": self.expected_parent_game_id,
            "existing_members": [
                {"game_id": member.id, "game_name": member.name}
                for member in self.existing_members
            ],
            "fingerprint": self.fingerprint,
            "selected_members": [
                {"game_id": member.id, "game_name": member.name}
                for member in self.selected_members
            ],
            "confirmed_parent": {
                "game_id": self.confirmed_parent.id,
                "game_name": self.confirmed_parent.name,
            },
            "status": self.status,
            "aliases": list(self.aliases),
        }


@dataclass(frozen=True, slots=True)
class AssociationComponentReadOutcome:
    snapshot: AssociationComponentSnapshot | None
    error: AssociationComponentError | None


@dataclass(frozen=True, slots=True)
class AssociationComponentConfirmationOutcome:
    confirmation: AssociationComponentConfirmation | None
    error: AssociationComponentError | None
