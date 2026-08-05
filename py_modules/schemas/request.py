from typing import List, TypedDict, Optional, Mapping
from dataclasses import dataclass
from .common import Game


class AddTimeDict(TypedDict):
    started_at: int
    ended_at: int
    game_id: str
    game_name: str


class DailyStatisticsForPeriodDict(TypedDict):
    start_date: str
    end_date: str
    game_id: Optional[str]


@dataclass(slots=True)
class ApplyManualTimeCorrectionList:
    game: Game
    time: float


ApplyManualTimeCorrectionDict = List[ApplyManualTimeCorrectionList]

GetGameDTO = str

GetFileSHA256DTO = str


class AddGameChecksumDict(TypedDict):
    game_id: str
    checksum: str
    algorithm: str
    chunk_size: int
    created_at: Optional[str]
    updated_at: Optional[str]


class RemoveGameChecksumDTO(TypedDict):
    game_id: str
    checksum: str


class HasDataBeforeDict(TypedDict):
    date: str
    game_id: str


RemoveAllGameChecksumsDTO = str


@dataclass(frozen=True, slots=True)
class AssociationComponentMember:
    game_id: str
    game_name: str

    @classmethod
    def from_dict(cls, value: object) -> "AssociationComponentMember":
        if not isinstance(value, Mapping):
            raise ValueError("selected_members must contain objects")
        game_id = value.get("game_id")
        game_name = value.get("game_name")
        if not isinstance(game_id, str) or not game_id:
            raise ValueError("selected_members.game_id must be a non-empty string")
        if not isinstance(game_name, str) or not game_name:
            raise ValueError("selected_members.game_name must be a non-empty string")
        return cls(game_id=game_id, game_name=game_name)

    def to_dict(self) -> dict[str, str]:
        return {"game_id": self.game_id, "game_name": self.game_name}


@dataclass(frozen=True, slots=True)
class AssociationComponentConfirmationRequest:
    """User confirmation for one complete logical-game component."""

    anchor_game_id: str
    proposed_parent_game_id: str
    proposed_parent_game_name: str
    expected_parent_game_id: str | None
    expected_fingerprint: str
    selected_members: tuple[AssociationComponentMember, ...]

    @classmethod
    def from_dict(cls, value: object) -> "AssociationComponentConfirmationRequest":
        if not isinstance(value, Mapping):
            raise ValueError("association confirmation must be an object")

        anchor_game_id = value.get("anchor_game_id")
        proposed_parent_game_id = value.get("proposed_parent_game_id")
        proposed_parent_game_name = value.get("proposed_parent_game_name")
        expected_parent_game_id = value.get("expected_parent_game_id")
        expected_fingerprint = value.get("expected_fingerprint")
        selected_members = value.get("selected_members")

        required_strings = {
            "anchor_game_id": anchor_game_id,
            "proposed_parent_game_id": proposed_parent_game_id,
            "proposed_parent_game_name": proposed_parent_game_name,
            "expected_fingerprint": expected_fingerprint,
        }
        if any(
            not isinstance(field, str) or not field
            for field in required_strings.values()
        ):
            raise ValueError(
                "association confirmation contains invalid required fields"
            )
        assert isinstance(anchor_game_id, str)
        assert isinstance(proposed_parent_game_id, str)
        assert isinstance(proposed_parent_game_name, str)
        assert isinstance(expected_fingerprint, str)
        if expected_parent_game_id is not None and (
            not isinstance(expected_parent_game_id, str) or not expected_parent_game_id
        ):
            raise ValueError(
                "expected_parent_game_id must be a non-empty string or null"
            )
        if not isinstance(selected_members, list) or not selected_members:
            raise ValueError("selected_members must be a non-empty list")

        parsed_members = tuple(
            AssociationComponentMember.from_dict(member) for member in selected_members
        )
        if len({member.game_id for member in parsed_members}) != len(parsed_members):
            raise ValueError("selected_members cannot contain duplicate game IDs")

        return cls(
            anchor_game_id=anchor_game_id,
            proposed_parent_game_id=proposed_parent_game_id,
            proposed_parent_game_name=proposed_parent_game_name,
            expected_parent_game_id=expected_parent_game_id,
            expected_fingerprint=expected_fingerprint,
            selected_members=parsed_members,
        )
