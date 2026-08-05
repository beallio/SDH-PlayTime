from typing import List, TypedDict, Optional, Mapping
from dataclasses import dataclass
from .common import Game


MAX_ASSOCIATION_COMPONENT_MEMBERS = 100
MAX_ASSOCIATION_GAME_ID_LENGTH = 255
MAX_ASSOCIATION_GAME_NAME_LENGTH = 1024
MAX_ASSOCIATION_FINGERPRINT_LENGTH = 128


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
        _validate_association_game_id(game_id, "selected_members.game_id")
        _validate_association_game_name(game_name, "selected_members.game_name")
        assert isinstance(game_id, str)
        assert isinstance(game_name, str)
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

    def validate(self) -> None:
        """Validate bounded confirmation input before it reaches the DAO."""

        _validate_association_game_id(self.anchor_game_id, "anchor_game_id")
        _validate_association_game_id(
            self.proposed_parent_game_id, "proposed_parent_game_id"
        )
        _validate_association_game_name(
            self.proposed_parent_game_name, "proposed_parent_game_name"
        )
        if self.expected_parent_game_id is not None:
            _validate_association_game_id(
                self.expected_parent_game_id, "expected_parent_game_id"
            )
        if (
            not isinstance(self.expected_fingerprint, str)
            or not self.expected_fingerprint
            or len(self.expected_fingerprint) > MAX_ASSOCIATION_FINGERPRINT_LENGTH
        ):
            raise ValueError("expected_fingerprint is invalid")
        if (
            not isinstance(self.selected_members, tuple)
            or not self.selected_members
            or len(self.selected_members) > MAX_ASSOCIATION_COMPONENT_MEMBERS
        ):
            raise ValueError("selected_members exceeds the maximum component size")

        member_ids = set()
        for member in self.selected_members:
            if not isinstance(member, AssociationComponentMember):
                raise ValueError("selected_members must contain association members")
            _validate_association_game_id(member.game_id, "selected_members.game_id")
            _validate_association_game_name(
                member.game_name, "selected_members.game_name"
            )
            if member.game_id in member_ids:
                raise ValueError("selected_members cannot contain duplicate game IDs")
            member_ids.add(member.game_id)

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

        _validate_association_game_id(anchor_game_id, "anchor_game_id")
        _validate_association_game_id(
            proposed_parent_game_id, "proposed_parent_game_id"
        )
        _validate_association_game_name(
            proposed_parent_game_name, "proposed_parent_game_name"
        )
        if expected_parent_game_id is not None:
            _validate_association_game_id(
                expected_parent_game_id, "expected_parent_game_id"
            )
        if (
            not isinstance(expected_fingerprint, str)
            or not expected_fingerprint
            or len(expected_fingerprint) > MAX_ASSOCIATION_FINGERPRINT_LENGTH
        ):
            raise ValueError("expected_fingerprint is invalid")
        assert isinstance(anchor_game_id, str)
        assert isinstance(proposed_parent_game_id, str)
        assert isinstance(proposed_parent_game_name, str)
        assert isinstance(expected_fingerprint, str)
        assert expected_parent_game_id is None or isinstance(
            expected_parent_game_id, str
        )

        if (
            not isinstance(selected_members, list)
            or not selected_members
            or len(selected_members) > MAX_ASSOCIATION_COMPONENT_MEMBERS
        ):
            raise ValueError("selected_members must be a bounded non-empty list")

        parsed_members = tuple(
            AssociationComponentMember.from_dict(member) for member in selected_members
        )
        request = cls(
            anchor_game_id=anchor_game_id,
            proposed_parent_game_id=proposed_parent_game_id,
            proposed_parent_game_name=proposed_parent_game_name,
            expected_parent_game_id=expected_parent_game_id,
            expected_fingerprint=expected_fingerprint,
            selected_members=parsed_members,
        )
        request.validate()
        return request


def _validate_association_game_id(value: object, field: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_ASSOCIATION_GAME_ID_LENGTH
    ):
        raise ValueError(f"{field} must be a bounded non-empty string")


def _validate_association_game_name(value: object, field: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_ASSOCIATION_GAME_NAME_LENGTH
    ):
        raise ValueError(f"{field} must be a bounded non-empty string")
