import asyncio
import os
import sys
from datetime import datetime, time
from pathlib import Path

import decky


decky_user_home = os.environ["DECKY_USER_HOME"]
data_dir = os.environ["DECKY_PLUGIN_RUNTIME_DIR"]
plugin_dir = Path(os.environ["DECKY_PLUGIN_DIR"])


def add_plugin_to_path():
    directories = [["./"], ["py_modules"]]

    for import_dir in directories:
        sys.path.append(str(plugin_dir.joinpath(*import_dir)))


add_plugin_to_path()

# pylint: disable=wrong-import-order, wrong-import-position
# ruff: noqa: E402
from py_modules.db.dao import Dao
from py_modules.files import Files
from py_modules.game_resolution import (
    GameChecksumCoordinator,
    FlatpakExecutableAdapter,
    GameResolutionCoordinator,
    MAX_RESOLUTION_BATCH_SIZE,
)
from py_modules.game_resolution.models import BatchResolutionResult, ResolutionResult
from py_modules.game_resolution.steam_shortcuts import SteamShortcutCatalog
from py_modules.games import Games
from py_modules.helpers import parse_date
from py_modules.statistics import Statistics
from py_modules.time_tracking import TimeTracking
from py_modules.schemas.request import (
    AddGameChecksumDict,
    AddTimeDict,
    ApplyManualTimeCorrectionDict,
    AssociationComponentConfirmationRequest,
    DailyStatisticsForPeriodDict,
    GetGameDTO,
    HasDataBeforeDict,
    MAX_ASSOCIATION_GAME_ID_LENGTH,
    RemoveAllGameChecksumsDTO,
    RemoveGameChecksumDTO,
)
from py_modules.dto.save_game_checksum import AddGameChecksumDTO
from py_modules.dto.statistics.daily_statistics_for_period import (
    DailyStatisticsForPeriodDTO,
)
from py_modules.dto.time.add_time import AddTimeDTO
from py_modules.utils.camel_case import convert_keys_to_camel_case
from py_modules.dto.time.apply_manual_time_correction import (
    ApplyManualTimeCorrectionDTO,
)
from py_modules.user_manager import UserManager
from py_modules.tracking_manager import TrackingManager
from py_modules.association_manager import AssociationManager


# pylint: enable=wrong-import-order, wrong-import-position
# autopep8: on


def _is_bounded_association_game_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= MAX_ASSOCIATION_GAME_ID_LENGTH
    )


class Plugin:
    files: Files = Files()
    game_resolution_coordinator: GameResolutionCoordinator = GameResolutionCoordinator()
    game_checksum_coordinator: GameChecksumCoordinator
    shortcut_catalog: SteamShortcutCatalog
    games: Games
    statistics: Statistics
    time_tracking: TimeTracking
    user_manager: UserManager
    tracking_manager: TrackingManager
    association_manager: AssociationManager

    async def _main(self):
        try:
            # Initialize UserManager for per-user database handling
            self.user_manager = UserManager(data_dir, decky.logger)
            shortcut_catalog = SteamShortcutCatalog(
                Path(decky_user_home),
                lambda: self.user_manager.current_user_id,
            )
            self.shortcut_catalog = shortcut_catalog
            self.game_checksum_coordinator = GameChecksumCoordinator(
                self.game_resolution_coordinator,
                self.files,
                shortcut_catalog,
            )

            # NOTE: Services (games, statistics, time_tracking) will be initialized
            # when set_current_user is called from the frontend.
            # For backward compatibility, if no user is set, we'll use legacy DB.
            self._initialize_legacy_fallback()
        except Exception as e:
            decky.logger.exception("[main] Unhandled exception: %s", e)
            raise

    def _initialize_legacy_fallback(self):
        """
        Initialize services with legacy DB as fallback.
        This ensures backward compatibility if frontend doesn't send user ID.
        """
        legacy_dao = self.user_manager.get_legacy_dao()

        if legacy_dao is not None:
            self.tracking_manager = TrackingManager(legacy_dao)
            self.association_manager = AssociationManager(legacy_dao)
            self.games = Games(legacy_dao, self.association_manager)
            self.statistics = Statistics(
                legacy_dao, self.tracking_manager, self.association_manager
            )
            self.time_tracking = TimeTracking(legacy_dao)
        else:
            # No legacy DB exists - services will be None until user is set
            self.games = None  # type: ignore
            self.statistics = None  # type: ignore
            self.time_tracking = None  # type: ignore
            self.tracking_manager = None  # type: ignore
            self.association_manager = None  # type: ignore

    def _get_current_dao(self) -> Dao:
        """
        Get the DAO for the current user.
        Falls back to legacy if no user is set.
        """
        dao = self.user_manager.get_current_dao()

        if dao is not None:
            return dao

        # Fallback to legacy
        legacy_dao = self.user_manager.get_legacy_dao()
        if legacy_dao is not None:
            return legacy_dao

        raise RuntimeError(
            "No user is set and no legacy database exists. "
            "Please call set_current_user first."
        )

    def _ensure_services_initialized(self):
        """Ensure services are initialized with current user's DAO."""
        dao = self._get_current_dao()

        # Re-initialize services if DAO has changed
        if self.games is None or self.games.dao is not dao:
            self.tracking_manager = TrackingManager(dao)
            self.association_manager = AssociationManager(dao)
            self.games = Games(dao, self.association_manager)
            self.statistics = Statistics(
                dao, self.tracking_manager, self.association_manager
            )
            self.time_tracking = TimeTracking(dao)

    async def set_current_user(self, steam_user_id: str):
        """
        Set the current Steam user ID for per-user data isolation.

        This should be called from the frontend when a user logs in.
        If legacy storage.db exists and this user doesn't have their own DB yet,
        the legacy data will be migrated to their personal database.

        Args:
            steam_user_id: The 64-bit Steam ID as a string
        """
        if not steam_user_id or not steam_user_id.strip():
            decky.logger.warning(
                "[set_current_user] Empty steam_user_id received, ignoring"
            )
            return None

        if self.user_manager.current_user_id == steam_user_id:
            decky.logger.debug(
                f"[set_current_user] User {steam_user_id} is already set, skipping"
            )
            return None

        try:
            decky.logger.info(f"[set_current_user] Setting user: {steam_user_id}")

            dao = self.user_manager.set_current_user(steam_user_id)

            # Update services to use new user's DAO
            self.tracking_manager = TrackingManager(dao)
            self.association_manager = AssociationManager(dao)
            self.games = Games(dao, self.association_manager)
            self.statistics = Statistics(
                dao, self.tracking_manager, self.association_manager
            )
            self.time_tracking = TimeTracking(dao)

            decky.logger.info(
                f"[set_current_user] Successfully set user: {steam_user_id}"
            )
            return None
        except Exception as e:
            decky.logger.exception("[set_current_user] Unhandled exception: %s", e)
            return None

    async def get_current_user(self) -> str | None:
        """
        Get the current Steam user ID.

        Returns:
            The current user's Steam ID, or None if not set
        """
        return self.user_manager.current_user_id

    async def add_time(self, dto_dict: AddTimeDict):
        try:
            self._ensure_services_initialized()
            dto = AddTimeDTO.from_dict(dto_dict)

            if not self.tracking_manager.should_track_session(dto.game_id):
                status = self.tracking_manager.get_tracking_status(dto.game_id)
                decky.logger.info(
                    "[add_time] Skipping tracking for game %s (status: %s)",
                    dto.game_id,
                    status,
                )
                return

            self.time_tracking.add_time(
                dto.started_at,
                dto.ended_at,
                dto.game_id,
                dto.game_name,
            )
        except Exception as e:
            decky.logger.exception("[add_time] Unhandled exception: %s", e)
            raise

    async def daily_statistics_for_period(self, dto_dict: DailyStatisticsForPeriodDict):
        try:
            self._ensure_services_initialized()
            dto = DailyStatisticsForPeriodDTO.from_dict(dto_dict)

            return convert_keys_to_camel_case(
                self.statistics.daily_statistics_for_period(
                    parse_date(dto.start_date),
                    parse_date(dto.end_date),
                    dto.game_id,
                ).to_dict()
            )
        except Exception as e:
            decky.logger.exception(
                "[daily_statistics_for_period] Unhandled exception: %s", e
            )
            raise

    async def statistics_for_last_two_weeks(self):
        try:
            self._ensure_services_initialized()
            return convert_keys_to_camel_case(
                self.statistics.get_statistics_for_last_two_weeks()
            )

        except Exception as e:
            decky.logger.exception(
                "[statistics_for_GameDictionary_weeks] Unhandled exception: %s", e
            )
            raise

    async def fetch_playtime_information(self):
        try:
            self._ensure_services_initialized()
            return convert_keys_to_camel_case(
                self.statistics.fetch_playtime_information()
            )

        except Exception as e:
            decky.logger.exception(
                "[fetch_playtime_information] Unhandled exception: %s", e
            )
            raise

    async def per_game_overall_statistics(self):
        try:
            self._ensure_services_initialized()
            return convert_keys_to_camel_case(
                self.statistics.per_game_overall_statistic()
            )
        except Exception as e:
            decky.logger.exception(
                "[per_game_overall_statistics] Unhandled exception: %s", e
            )
            raise

    async def short_per_game_overall_statistics(self):
        try:
            self._ensure_services_initialized()
            return convert_keys_to_camel_case(
                self.statistics.per_game_overall_statistic()
            )
        except Exception as e:
            decky.logger.exception(
                "[per_game_overall_statistics] Unhandled exception: %s", e
            )
            raise

    async def apply_manual_time_correction(
        self, list_of_game_stats: ApplyManualTimeCorrectionDict
    ):
        try:
            self._ensure_services_initialized()
            dto = ApplyManualTimeCorrectionDTO.from_dict(list_of_game_stats)
            return self.time_tracking.apply_manual_time_for_games(
                list_of_game_stats=dto, source="manually-changed"
            )
        except Exception as e:
            decky.logger.exception(
                "[apply_manual_time_correction] Unhandled exception: %s", e
            )
            raise

    async def get_game(self, game_id: GetGameDTO):
        try:
            self._ensure_services_initialized()
            game_by_id = self.games.get_by_id(game_id)

            if game_by_id is None:
                return None

            return convert_keys_to_camel_case(game_by_id.to_dict())
        except Exception as e:
            decky.logger.exception("[get_game] Unhandled exception: %s", e)
            raise

    async def has_min_required_python_version(self) -> bool:
        if sys.version_info < (3, 11):
            return False

        return True

    async def get_game_checksum(self, shortcut_evidence: object):
        try:
            result = await asyncio.to_thread(
                self.game_checksum_coordinator.get_checksum, shortcut_evidence
            )
            return convert_keys_to_camel_case(result.to_dict())
        except Exception as error:
            decky.logger.exception(
                "[get_game_checksum] Checksum coordinator failed without hashing "
                "a payload: %s",
                type(error).__name__,
            )
            return {
                "checksum": None,
                "status": "payload_unavailable",
                "reasonCode": "probe_failure",
            }

    async def resolve_game_payloads(self, entries: object):
        """Resolve bounded shortcut hints without executing, mounting, or scanning."""
        try:
            result = await asyncio.to_thread(
                self.game_resolution_coordinator.resolve_batch, entries
            )
            return convert_keys_to_camel_case(result.to_dict())
        except Exception as error:
            decky.logger.exception(
                "[resolve_game_payloads] Resolver failed without processing "
                "a payload: %s",
                type(error).__name__,
            )
            if isinstance(entries, list) and len(entries) <= MAX_RESOLUTION_BATCH_SIZE:
                fallback = BatchResolutionResult(
                    tuple(
                        ResolutionResult.unknown(reason_code="probe_failure")
                        for _ in entries
                    )
                )
                return convert_keys_to_camel_case(fallback.to_dict())
            return {"results": [], "error": "probe_failure"}

    async def is_flatpak_app_installed(self, flatpak_app_id: str) -> bool:
        try:
            return (
                FlatpakExecutableAdapter.installed_payload_path(flatpak_app_id)
                is not None
            )
        except Exception:
            decky.logger.exception(
                "[is_flatpak_app_installed] Unable to determine flatpak install state"
            )
            return False

    async def get_shortcut_app_details(self, app_id: int) -> dict[str, object]:
        try:
            if isinstance(app_id, bool) or not isinstance(app_id, int):
                return {"status": "failure", "reason": "missing-details"}
            lookup_app_id = app_id & 0xFFFFFFFF
            outcome = self.shortcut_catalog.get_request(lookup_app_id)
            if outcome.request is None:
                return {"status": "failure", "reason": "missing-details"}

            normalized = outcome.request.normalized
            return {
                "status": "success",
                "details": {
                    "strShortcutExe": normalized.shortcut_exe or "",
                    "strShortcutLaunchOptions": (
                        normalized.shortcut_launch_options or ""
                    ),
                    "strShortcutStartDir": normalized.shortcut_start_dir or "",
                    "strFlatpakAppID": normalized.flatpak_app_id or "",
                },
            }
        except Exception:
            decky.logger.exception(
                "[get_shortcut_app_details] Unable to read shortcut evidence"
            )
            return {"status": "failure", "reason": "callback-error"}

    async def get_games_dictionary(self):
        try:
            self._ensure_services_initialized()
            return convert_keys_to_camel_case(self.games.get_dictionary())
        except Exception as e:
            decky.logger.exception("[get_games_dictionary] Unhandled exception: %s", e)
            raise

    async def get_association_candidates(self):
        try:
            self._ensure_services_initialized()
            return convert_keys_to_camel_case(self.games.get_association_candidates())
        except Exception as e:
            decky.logger.exception(
                "[get_association_candidates] Unhandled exception: %s", e
            )
            raise

    async def save_game_checksum(self, dto_dict: AddGameChecksumDict):
        try:
            self._ensure_services_initialized()
            dto = AddGameChecksumDTO.from_dict(dto_dict)

            return self.games.save_game_checksum(
                dto.game_id,
                dto.checksum,
                dto.algorithm,
                dto.chunk_size,
                dto.created_at,
                dto.updated_at,
            )
        except Exception as e:
            decky.logger.exception("[save_game_checksum] Unhandled exception: %s", e)
            raise

    async def save_game_checksum_bulk(self, dtos_list: list[AddGameChecksumDict]):
        try:
            self._ensure_services_initialized()
            dtos = [AddGameChecksumDTO.from_dict(dto_dict) for dto_dict in dtos_list]

            return self.games.save_game_checksum_bulk(dtos)
        except Exception as e:
            decky.logger.exception(
                "[save_game_checksum_bulk] Unhandled exception: %s", e
            )
            raise

    async def remove_game_checksum(self, dto: RemoveGameChecksumDTO):
        try:
            self._ensure_services_initialized()
            return convert_keys_to_camel_case(
                self.games.remove_game_checksum(dto["game_id"], dto["checksum"])
            )
        except Exception as e:
            decky.logger.exception("[remove_game_checksum] Unhandled exception: %s", e)
            raise

    async def remove_all_game_checksum(self, game_id: RemoveAllGameChecksumsDTO):
        try:
            self._ensure_services_initialized()
            return convert_keys_to_camel_case(
                self.games.remove_all_game_checksums(game_id)
            )
        except Exception as e:
            decky.logger.exception("[remove_game_checksum] Unhandled exception: %s", e)
            raise

    async def remove_all_checksums(self):
        try:
            self._ensure_services_initialized()
            return self.games.remove_all_checksums()
        except Exception as e:
            decky.logger.exception("[remove_all_checksums] Unhandled exception: %s", e)
            raise

    async def get_games_checksum(
        self,
    ):
        try:
            self._ensure_services_initialized()
            return convert_keys_to_camel_case(self.games.get_games_checksum())
        except Exception as e:
            decky.logger.exception("[get_games_checksum] Unhandled exception: %s", e)
            raise

    async def link_game_to_game_with_checksum(
        self, child_game_id: str, parent_game_id: str
    ):
        try:
            self._ensure_services_initialized()
            return self.games.link_game_to_game_with_checksum(
                child_game_id, parent_game_id
            )
        except Exception as e:
            decky.logger.exception(
                "[link_game_to_game_with_checksum] Unhandled exception: %s", e
            )
            raise

    async def get_decky_home(self):
        try:
            return decky_user_home
        except Exception as e:
            decky.logger.exception("[get_decky_home] Unhandled exception: %s", e)
            raise

    async def has_data_before(self, dto_dict: HasDataBeforeDict):
        try:
            self._ensure_services_initialized()
            date = datetime.combine(parse_date(dto_dict["date"]), time.min)
            game_id = dto_dict["game_id"]
            return self.statistics.dao.has_data_before(date, game_id)
        except Exception as e:
            decky.logger.exception("[has_data_before] Unhandled exception: %s", e)
            raise

    async def get_all_tracking_configs(self):
        """Get all non-default tracking configurations."""
        try:
            self._ensure_services_initialized()
            return convert_keys_to_camel_case(
                self.tracking_manager.get_all_tracking_configs()
            )
        except Exception as e:
            decky.logger.exception(
                "[get_all_tracking_configs] Unhandled exception: %s", e
            )
            raise

    async def set_game_tracking_status(self, dto_dict: dict):
        """Set the tracking status for a game."""
        try:
            self._ensure_services_initialized()
            game_id = dto_dict.get("game_id")
            status = dto_dict.get("status")

            if not isinstance(game_id, str) or not isinstance(status, str):
                raise ValueError("game_id and status must be strings")

            self.tracking_manager.set_tracking_status(game_id, status)
            return True
        except Exception as e:
            decky.logger.exception(
                "[set_game_tracking_status] Unhandled exception: %s", e
            )
            raise

    async def remove_game_tracking_status(self, game_id: str):
        """Remove tracking status for a game (revert to default)."""
        try:
            self._ensure_services_initialized()
            self.tracking_manager.remove_tracking_status(game_id)
            return True
        except Exception as e:
            decky.logger.exception(
                "[remove_game_tracking_status] Unhandled exception: %s", e
            )
            raise

    async def get_game_tracking_status(self, game_id: str):
        """Get the tracking status for a game."""
        try:
            self._ensure_services_initialized()
            return self.tracking_manager.get_tracking_status(game_id)
        except Exception as e:
            decky.logger.exception(
                "[get_game_tracking_status] Unhandled exception: %s", e
            )
            raise

    # ========== Game Association API ==========

    async def create_game_association(self, dto_dict: dict):
        """
        Create an association between a parent and child game.
        Child game's playtime will be combined with parent's in statistics.
        """
        try:
            self._ensure_services_initialized()
            parent_game_id = dto_dict.get("parent_game_id")
            child_game_id = dto_dict.get("child_game_id")

            if not parent_game_id or not child_game_id:
                return {
                    "success": False,
                    "error": {
                        "code": "MISSING_PARAMS",
                        "message": "parent_game_id and child_game_id are required",
                    },
                }

            error = self.association_manager.create_association(
                parent_game_id, child_game_id
            )

            if error:
                return {
                    "success": False,
                    "error": convert_keys_to_camel_case(error.to_dict()),
                }

            return {"success": True}
        except Exception as e:
            decky.logger.exception(
                "[create_game_association] Unhandled exception: %s", e
            )
            raise

    async def get_game_association_component(self, anchor_game_id: str):
        """Read one checksum/association component for an explicit confirmation."""
        try:
            self._ensure_services_initialized()
            if not _is_bounded_association_game_id(anchor_game_id):
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "anchor_game_id must be a non-empty string",
                    },
                }
            outcome = self.association_manager.get_association_component(anchor_game_id)
            if outcome.error:
                return {
                    "success": False,
                    "error": convert_keys_to_camel_case(outcome.error.to_dict()),
                }
            if outcome.snapshot is None:
                return {
                    "success": False,
                    "error": {
                        "code": "ASSOCIATION_UPDATE_FAILED",
                        "message": "The association component could not be read.",
                    },
                }
            return {
                "success": True,
                "data": convert_keys_to_camel_case(outcome.snapshot.to_dict()),
            }
        except Exception as e:
            decky.logger.exception(
                "[get_game_association_component] Unhandled exception: %s", e
            )
            raise

    async def confirm_game_association_component(self, dto_dict: object):
        """Atomically validate and confirm one complete association component."""
        try:
            self._ensure_services_initialized()
            try:
                request = AssociationComponentConfirmationRequest.from_dict(dto_dict)
            except ValueError:
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": (
                            "Invalid association component confirmation request."
                        ),
                    },
                }

            outcome = self.association_manager.confirm_association_component(request)
            if outcome.error:
                return {
                    "success": False,
                    "error": convert_keys_to_camel_case(outcome.error.to_dict()),
                }
            if outcome.confirmation is None:
                return {
                    "success": False,
                    "error": {
                        "code": "ASSOCIATION_UPDATE_FAILED",
                        "message": "The association component could not be confirmed.",
                    },
                }
            return {
                "success": True,
                "data": convert_keys_to_camel_case(outcome.confirmation.to_dict()),
            }
        except Exception as e:
            decky.logger.exception(
                "[confirm_game_association_component] Unhandled exception: %s", e
            )
            raise

    async def detach_game_association_member(self, child_game_id: str):
        """Detach a child association while retaining its playtime history."""
        try:
            self._ensure_services_initialized()
            if not _is_bounded_association_game_id(child_game_id):
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "child_game_id must be a non-empty string",
                    },
                }
            error = self.association_manager.detach_association_member(child_game_id)
            if error:
                return {
                    "success": False,
                    "error": convert_keys_to_camel_case(error.to_dict()),
                }
            return {"success": True}
        except Exception as e:
            decky.logger.exception(
                "[detach_game_association_member] Unhandled exception: %s", e
            )
            raise

    async def dissolve_game_association_component(self, anchor_game_id: str):
        """Dissolve every explicit association edge in one logical component."""
        try:
            self._ensure_services_initialized()
            if not _is_bounded_association_game_id(anchor_game_id):
                return {
                    "success": False,
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "anchor_game_id must be a non-empty string",
                    },
                }
            error = self.association_manager.dissolve_association_component(
                anchor_game_id
            )
            if error:
                return {
                    "success": False,
                    "error": convert_keys_to_camel_case(error.to_dict()),
                }
            return {"success": True}
        except Exception as e:
            decky.logger.exception(
                "[dissolve_game_association_component] Unhandled exception: %s", e
            )
            raise

    async def remove_game_association(self, child_game_id: str):
        """Remove an association for a child game."""
        try:
            self._ensure_services_initialized()

            error = self.association_manager.remove_association(child_game_id)

            if error:
                return {
                    "success": False,
                    "error": convert_keys_to_camel_case(error.to_dict()),
                }

            return {"success": True}
        except Exception as e:
            decky.logger.exception(
                "[remove_game_association] Unhandled exception: %s", e
            )
            raise

    async def get_all_game_associations(self):
        """Get all game associations with game names."""
        try:
            self._ensure_services_initialized()
            return convert_keys_to_camel_case(
                self.association_manager.get_all_associations()
            )
        except Exception as e:
            decky.logger.exception(
                "[get_all_game_associations] Unhandled exception: %s", e
            )
            raise

    async def get_game_association(self, game_id: str):
        """
        Get association info for a specific game.
        Returns role ('parent' or 'child') and related games.
        """
        try:
            self._ensure_services_initialized()
            result = self.association_manager.get_association_for_game(game_id)
            if result:
                return convert_keys_to_camel_case(result)
            return None
        except Exception as e:
            decky.logger.exception("[get_game_association] Unhandled exception: %s", e)
            raise

    async def can_game_be_parent(self, game_id: str):
        """Check if a game can be a parent (not already a child)."""
        try:
            self._ensure_services_initialized()
            return self.association_manager.can_be_parent(game_id)
        except Exception as e:
            decky.logger.exception("[can_game_be_parent] Unhandled exception: %s", e)
            raise

    async def can_game_be_child(self, game_id: str):
        """Check if a game can be a child (not already a child or parent)."""
        try:
            self._ensure_services_initialized()
            return self.association_manager.can_be_child(game_id)
        except Exception as e:
            decky.logger.exception("[can_game_be_child] Unhandled exception: %s", e)
            raise

    async def _unload(self):
        decky.logger.info("Goodnight, World!")

    async def _uninstall(self):
        decky.logger.info("Goodbye, World!")
