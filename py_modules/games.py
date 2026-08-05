from py_modules.db.dao import Dao
from collections import defaultdict
from typing import Dict, List, Set
from py_modules.schemas.common import Game
from py_modules.game_identity import canonical_game_name
from py_modules.schemas.response import (
    FileChecksum,
    GameDictionary,
    GamePlaytimeSummary,
)
from py_modules.dto.save_game_checksum import AddGameChecksumDTO


class Games:
    __slots__ = ("dao", "association_manager")
    dao: Dao

    def __init__(self, dao: Dao, association_manager=None) -> None:
        self.dao = dao
        self.association_manager = association_manager

    def _get_child_game_ids(self) -> Set[str]:
        if not self.association_manager:
            return set()

        return {
            association["child_game_id"]
            for association in self.dao.get_all_game_associations()
        }

    def get_by_id(self, game_id: str) -> GamePlaytimeSummary | None:
        components = self.dao.get_game_identity_components()
        component = components.get(game_id)
        canonical_id = component.canonical_id if component else game_id
        member_ids = component.members if component else (game_id,)
        games_by_id = self.dao.get_games(member_ids)
        canonical_game_information = games_by_id.get(canonical_id)
        if canonical_game_information is None:
            return None

        canonical_game = Game(
            canonical_id,
            canonical_game_name(
                component,
                {member_id: game.name for member_id, game in games_by_id.items()},
            )
            if component
            else canonical_game_information.name or "Unknown Game",
        )
        total_time = sum(game.time for game in games_by_id.values())

        return GamePlaytimeSummary(canonical_game, total_time=total_time)

    def get_dictionary(self) -> List[Dict[str, GameDictionary]]:
        data = self.dao.get_games_dictionary()
        components = self.dao.get_game_identity_components()
        names_by_game_id = {game.id: game.name for game in data}
        checksums_by_game_id = defaultdict(list)
        for checksum in self.dao.get_games_checksum():
            checksums_by_game_id[checksum.game_id].append(checksum)

        result: List[Dict[str, GameDictionary]] = []

        for game in sorted(data, key=lambda item: item.id):
            component = components.get(game.id)
            if component and component.canonical_id != game.id:
                continue

            member_ids = component.members if component else (game.id,)
            game_files_checksum = [
                checksum
                for member_id in member_ids
                for checksum in checksums_by_game_id[member_id]
            ]

            file_checksums = [
                FileChecksum(
                    Game(gfc.game_id, gfc.game_name),
                    gfc.checksum,
                    gfc.algorithm,
                    gfc.chunk_size,
                    gfc.created_at,
                    gfc.updated_at,
                )
                for gfc in game_files_checksum
            ]
            file_checksums.sort(
                key=lambda checksum: (
                    checksum.game.id,
                    checksum.checksum,
                    checksum.algorithm,
                )
            )

            result.append(
                GameDictionary(
                    Game(
                        game.id,
                        canonical_game_name(component, names_by_game_id)
                        if component
                        else game.name or "Unknown Game",
                    ),
                    files=file_checksums,
                ).to_dict()
            )

        return result

    def get_association_candidates(self) -> List[Dict]:
        return [
            candidate.to_dict() for candidate in self.dao.get_association_candidates()
        ]

    def save_game_checksum(
        self,
        game_id: str,
        hash_checksum: str,
        hash_algorithm: str,
        hash_chunk_size: int,
        hash_created_at: None | str,
        hash_updated_at: None | str,
    ):
        self.dao.save_game_checksum(
            game_id,
            hash_checksum,
            hash_algorithm,
            hash_chunk_size,
            hash_created_at,
            hash_updated_at,
        )

    def save_game_checksum_bulk(self, checksums: List[AddGameChecksumDTO]):
        checksums_data = [
            (
                dto.game_id,
                dto.checksum,
                dto.algorithm,
                dto.chunk_size,
                dto.created_at,
                dto.updated_at,
            )
            for dto in checksums
        ]

        self.dao.save_game_checksum_bulk(checksums_data)

    def remove_game_checksum(self, game_id: str, checksum: str):
        self.dao.remove_game_checksum(game_id, checksum)

    def remove_all_game_checksums(self, game_id: str):
        self.dao.remove_all_game_checksums(game_id)

    def remove_all_checksums(self):
        return self.dao.remove_all_checksums()

    def get_games_checksum(self):
        games_checksum_without_game_dict = self.dao.get_games_checksum()
        components = self.dao.get_game_identity_components()
        child_game_ids = self._get_child_game_ids()
        checksums = [
            FileChecksum(
                Game(
                    game.game_id,
                    game.game_name if game.game_name is not None else "[Unknown name]",
                ),
                game.checksum,
                game.algorithm,
                game.chunk_size,
                game.created_at,
                game.updated_at,
            ).to_dict()
            for game in games_checksum_without_game_dict
            if game.game_id not in child_game_ids
        ]

        def checksum_sort_key(checksum):
            game_id = checksum["game"]["id"]
            component = components.get(game_id)
            canonical_id = component.canonical_id if component else game_id
            return canonical_id, game_id, checksum["checksum"], checksum["algorithm"]

        return sorted(checksums, key=checksum_sort_key)

    def link_game_to_game_with_checksum(self, child_game_id: str, parent_game_id: str):
        parent_game = self.dao.get_game(parent_game_id)

        if not parent_game or parent_game.name is None:
            raise ValueError(
                f"Cannot link game '{child_game_id}' to parent '{parent_game_id}'. Parent game does not exist or has invalid name."
            )

        # Now link the checksum
        return self.dao.link_game_to_game_with_checksum(child_game_id, parent_game_id)
