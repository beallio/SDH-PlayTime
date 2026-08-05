from collections import defaultdict
from dataclasses import dataclass
from itertools import groupby
from typing import Iterable, Literal


GameIdentityStatus = Literal["confirmed", "unconfirmed", "conflict"]
ChecksumRecord = tuple[str, str, str]
AssociationRecord = tuple[str, str]


@dataclass(frozen=True, slots=True)
class GameIdentityComponent:
    """A deterministic logical-game identity assembled from read-only edges."""

    members: tuple[str, ...]
    aliases: tuple[str, ...]
    canonical_id: str
    explicit_parent_ids: tuple[str, ...]
    status: GameIdentityStatus


class _UnionFind:
    def __init__(self, members: Iterable[str]) -> None:
        self._parents = {member: member for member in members}

    def find(self, member: str) -> str:
        parent = self._parents[member]
        if parent != member:
            self._parents[member] = self.find(parent)
        return self._parents[member]

    def union(self, first: str, second: str) -> None:
        first_root = self.find(first)
        second_root = self.find(second)
        if first_root == second_root:
            return

        if first_root < second_root:
            self._parents[second_root] = first_root
        else:
            self._parents[first_root] = second_root


def _normalize_game_id(game_id: object) -> str:
    return str(game_id)


def _normalize_checksum_records(
    checksum_records: Iterable[ChecksumRecord],
) -> tuple[ChecksumRecord, ...]:
    records = {
        (
            _normalize_game_id(game_id),
            str(checksum),
            str(algorithm),
        )
        for game_id, checksum, algorithm in checksum_records
    }
    return tuple(sorted(records, key=lambda record: (record[1], record[2], record[0])))


def _normalize_association_records(
    association_records: Iterable[AssociationRecord],
) -> tuple[AssociationRecord, ...]:
    return tuple(
        sorted(
            {
                (_normalize_game_id(parent_id), _normalize_game_id(child_id))
                for parent_id, child_id in association_records
            }
        )
    )


def build_game_identity_components(
    game_ids: Iterable[str],
    checksum_records: Iterable[ChecksumRecord],
    association_records: Iterable[AssociationRecord],
) -> dict[str, GameIdentityComponent]:
    """Build one deterministic component map from checksum and explicit edges.

    A checksum edge joins games only when both checksum and algorithm match.
    Explicit parent-child associations also join games, but their parent selects the
    canonical ID when the whole component has exactly one explicit parent. Multiple
    explicit parents are reported as a conflict and use the lexical member minimum as
    a stable display fallback.
    """

    normalized_checksums = _normalize_checksum_records(checksum_records)
    normalized_associations = _normalize_association_records(association_records)
    members = {_normalize_game_id(game_id) for game_id in game_ids}
    members.update(record[0] for record in normalized_checksums)
    members.update(parent_id for parent_id, _ in normalized_associations)
    members.update(child_id for _, child_id in normalized_associations)

    union_find = _UnionFind(sorted(members))

    for _, checksum_group in groupby(
        normalized_checksums,
        key=lambda record: (record[1], record[2]),
    ):
        checksum_members = [record[0] for record in checksum_group]
        leader = checksum_members[0]
        for member in checksum_members[1:]:
            union_find.union(leader, member)

    explicit_parent_ids = set()
    for parent_id, child_id in normalized_associations:
        union_find.union(parent_id, child_id)
        explicit_parent_ids.add(parent_id)

    members_by_root: dict[str, list[str]] = defaultdict(list)
    for member in sorted(members):
        members_by_root[union_find.find(member)].append(member)

    components_by_member: dict[str, GameIdentityComponent] = {}
    for component_members in sorted(
        members_by_root.values(), key=lambda group: group[0]
    ):
        sorted_members = tuple(component_members)
        component_parents = tuple(
            parent_id
            for parent_id in sorted(explicit_parent_ids)
            if parent_id in component_members
        )

        if len(component_parents) == 1:
            canonical_id = component_parents[0]
            status: GameIdentityStatus = "confirmed"
        elif component_parents:
            canonical_id = sorted_members[0]
            status = "conflict"
        else:
            canonical_id = sorted_members[0]
            status = "unconfirmed"

        component = GameIdentityComponent(
            members=sorted_members,
            aliases=tuple(
                member for member in sorted_members if member != canonical_id
            ),
            canonical_id=canonical_id,
            explicit_parent_ids=component_parents,
            status=status,
        )
        components_by_member.update({member: component for member in sorted_members})

    return components_by_member
