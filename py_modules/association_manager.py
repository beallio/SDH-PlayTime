from dataclasses import dataclass
from typing import List, Dict, Optional
from py_modules.db.dao import Dao
from py_modules.schemas.request import AssociationComponentConfirmationRequest
from py_modules.schemas.response import (
    AssociationComponentConfirmationOutcome,
    AssociationComponentError,
    AssociationComponentReadOutcome,
)


@dataclass(slots=True)
class GameAssociation:
    parent_game_id: str
    parent_game_name: str
    child_game_id: str
    child_game_name: str
    created_at: Optional[str]

    def to_dict(self) -> Dict:
        return {
            "parent_game_id": self.parent_game_id,
            "parent_game_name": self.parent_game_name,
            "child_game_id": self.child_game_id,
            "child_game_name": self.child_game_name,
            "created_at": self.created_at,
        }


AssociationError = AssociationComponentError


class AssociationManager:
    __slots__ = ("dao",)
    dao: Dao

    def __init__(self, dao: Dao) -> None:
        self.dao = dao

    def create_association(
        self, parent_game_id: str, child_game_id: str
    ) -> Optional[AssociationError]:
        if parent_game_id == child_game_id:
            return AssociationError(
                code="SELF_ASSOCIATION",
                message="Cannot associate a game with itself.",
            )

        parent_game = self.dao.get_game_with_overall_time(parent_game_id)
        if not parent_game:
            return AssociationError(
                code="PARENT_NOT_FOUND",
                message=f"Parent game '{parent_game_id}' does not exist.",
            )

        child_game = self.dao.get_game_with_overall_time(child_game_id)
        if not child_game:
            return AssociationError(
                code="CHILD_NOT_FOUND",
                message=f"Child game '{child_game_id}' does not exist.",
            )

        if self.dao.is_game_a_child(child_game_id):
            return AssociationError(
                code="ALREADY_CHILD",
                message=(
                    f"Game '{child_game_id}' is already associated with another parent."
                ),
            )

        if self.dao.is_game_a_parent(child_game_id):
            return AssociationError(
                code="IS_PARENT",
                message=(
                    f"Game '{child_game_id}' has children and cannot "
                    "become a child itself."
                ),
            )

        if self.dao.is_game_a_child(parent_game_id):
            return AssociationError(
                code="PARENT_IS_CHILD",
                message=(
                    f"Game '{parent_game_id}' is a child of another game and "
                    "cannot be a parent."
                ),
            )

        self.dao.create_game_association(parent_game_id, child_game_id)
        return None

    def remove_association(self, child_game_id: str) -> Optional[AssociationError]:
        if not self.dao.is_game_a_child(child_game_id):
            return AssociationError(
                code="NOT_A_CHILD",
                message=f"Game '{child_game_id}' is not associated with any parent.",
            )

        self.dao.remove_game_association(child_game_id)
        return None

    def get_association_component(
        self, anchor_game_id: str
    ) -> AssociationComponentReadOutcome:
        try:
            return AssociationComponentReadOutcome(
                snapshot=self.dao.get_game_association_component(anchor_game_id),
                error=None,
            )
        except AssociationComponentError as error:
            return AssociationComponentReadOutcome(snapshot=None, error=error)

    def confirm_association_component(
        self, request: AssociationComponentConfirmationRequest
    ) -> AssociationComponentConfirmationOutcome:
        try:
            return AssociationComponentConfirmationOutcome(
                confirmation=self.dao.confirm_game_association_component(request),
                error=None,
            )
        except AssociationComponentError as error:
            return AssociationComponentConfirmationOutcome(
                confirmation=None, error=error
            )

    def detach_association_member(
        self, child_game_id: str
    ) -> Optional[AssociationError]:
        try:
            self.dao.detach_game_association_member(child_game_id)
            return None
        except AssociationComponentError as error:
            return error

    def dissolve_association_component(
        self, anchor_game_id: str
    ) -> Optional[AssociationError]:
        try:
            self.dao.dissolve_game_association_component(anchor_game_id)
            return None
        except AssociationComponentError as error:
            return error

    def get_all_associations(self) -> List[Dict]:
        associations = self.dao.get_all_game_associations()
        return [
            GameAssociation(
                parent_game_id=a["parent_game_id"],
                parent_game_name=a["parent_game_name"] or "[Unknown]",
                child_game_id=a["child_game_id"],
                child_game_name=a["child_game_name"] or "[Unknown]",
                created_at=a["created_at"],
            ).to_dict()
            for a in associations
        ]

    def get_association_for_game(self, game_id: str) -> Optional[Dict]:
        # Check if game is a child
        parent_id = self.dao.get_parent_of_child(game_id)
        if parent_id:
            parent_game = self.dao.get_game(parent_id)
            return {
                "role": "child",
                "parent_game_id": parent_id,
                "parent_game_name": parent_game.name if parent_game else "[Unknown]",
            }

        # Check if game is a parent
        children = self.dao.get_children_of_parent(game_id)
        if children:
            children_info = []
            for child_id in children:
                child_game = self.dao.get_game(child_id)
                children_info.append(
                    {
                        "game_id": child_id,
                        "game_name": child_game.name if child_game else "[Unknown]",
                    }
                )
            return {
                "role": "parent",
                "children": children_info,
            }

        return None

    def get_combined_playtime(self, game_id: str) -> float:
        return self.dao.get_combined_playtime_for_game(game_id)

    def get_associated_game_ids(self, game_id: str) -> List[str]:
        return self.dao.get_associated_game_ids(game_id)

    def can_be_parent(self, game_id: str) -> bool:
        return not self.dao.is_game_a_child(game_id)

    def can_be_child(self, game_id: str) -> bool:
        return not self.dao.is_game_a_child(game_id) and not self.dao.is_game_a_parent(
            game_id
        )
