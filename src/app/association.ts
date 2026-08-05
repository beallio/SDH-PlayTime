import { call } from "@decky/api";
import { BACK_END_API } from "@src/constants";
import type {
	GameAssociation,
	CreateGameAssociationDTO,
	AssociationComponentConfirmationResult,
	AssociationComponentReadResult,
	AssociationResult,
	ConfirmAssociationComponentDTO,
	GameAssociationInfo,
} from "@src/types/association";
import logger from "@src/utils/logger";

export class AssociationService {
	/** Read a component before the user explicitly confirms a complete star. */
	async getAssociationComponent(
		anchorGameId: string,
	): Promise<AssociationComponentReadResult> {
		return await call<[string], AssociationComponentReadResult>(
			BACK_END_API.GET_GAME_ASSOCIATION_COMPONENT,
			anchorGameId,
		).catch((error) => {
			logger.error("Failed to get association component:", error);
			return {
				success: false,
				error: {
					code: "NETWORK_ERROR",
					message: "Failed to get association component. Please try again.",
				},
			};
		});
	}

	/** Confirm the selected parent for a complete logical-game component. */
	async confirmAssociationComponent(
		dto: ConfirmAssociationComponentDTO,
	): Promise<AssociationComponentConfirmationResult> {
		return await call<
			[ConfirmAssociationComponentDTO],
			AssociationComponentConfirmationResult
		>(BACK_END_API.CONFIRM_GAME_ASSOCIATION_COMPONENT, dto).catch((error) => {
			logger.error("Failed to confirm association component:", error);
			return {
				success: false,
				error: {
					code: "NETWORK_ERROR",
					message: "Failed to confirm association component. Please try again.",
				},
			};
		});
	}

	/** Detach a child without removing its recorded playtime. */
	async detachAssociationMember(
		childGameId: string,
	): Promise<AssociationResult> {
		return await call<[string], AssociationResult>(
			BACK_END_API.DETACH_GAME_ASSOCIATION_MEMBER,
			childGameId,
		).catch((error) => {
			logger.error("Failed to detach association member:", error);
			return {
				success: false,
				error: {
					code: "NETWORK_ERROR",
					message: "Failed to detach association member. Please try again.",
				},
			};
		});
	}

	/** Remove every explicit association edge from one component. */
	async dissolveAssociationComponent(
		anchorGameId: string,
	): Promise<AssociationResult> {
		return await call<[string], AssociationResult>(
			BACK_END_API.DISSOLVE_GAME_ASSOCIATION_COMPONENT,
			anchorGameId,
		).catch((error) => {
			logger.error("Failed to dissolve association component:", error);
			return {
				success: false,
				error: {
					code: "NETWORK_ERROR",
					message:
						"Failed to dissolve association component. Please try again.",
				},
			};
		});
	}

	/**
	 * Get all game associations
	 */
	async getAllAssociations(): Promise<GameAssociation[]> {
		try {
			return await call<[], GameAssociation[]>(
				BACK_END_API.GET_ALL_GAME_ASSOCIATIONS,
			);
		} catch (error) {
			logger.error("Failed to get game associations:", error);
			throw error;
		}
	}

	/**
	 * Create an association between a parent and child game
	 */
	async createAssociation(
		parentGameId: string,
		childGameId: string,
	): Promise<AssociationResult> {
		return await call<[CreateGameAssociationDTO], AssociationResult>(
			BACK_END_API.CREATE_GAME_ASSOCIATION,
			{
				parent_game_id: parentGameId,
				child_game_id: childGameId,
			},
		).catch((error) => {
			logger.error("Failed to create game association:", error);
			return {
				success: false,
				error: {
					code: "NETWORK_ERROR",
					message: "Failed to create association. Please try again.",
				},
			};
		});
	}

	/**
	 * Remove an association for a child game
	 */
	async removeAssociation(childGameId: string): Promise<AssociationResult> {
		return await call<[string], AssociationResult>(
			BACK_END_API.REMOVE_GAME_ASSOCIATION,
			childGameId,
		).catch((error) => {
			logger.error("Failed to remove game association:", error);
			return {
				success: false,
				error: {
					code: "NETWORK_ERROR",
					message: "Failed to remove association. Please try again.",
				},
			};
		});
	}

	/**
	 * Get association info for a specific game
	 */
	async getGameAssociation(gameId: string): Promise<GameAssociationInfo> {
		return await call<[string], GameAssociationInfo>(
			BACK_END_API.GET_GAME_ASSOCIATION,
			gameId,
		).catch((error) => {
			logger.error("Failed to get game association:", error);
			return null;
		});
	}

	/**
	 * Check if a game can be a parent (not already a child)
	 */
	async canBeParent(gameId: string): Promise<boolean> {
		return await call<[string], boolean>(
			BACK_END_API.CAN_GAME_BE_PARENT,
			gameId,
		).catch((error) => {
			logger.error("Failed to check if game can be parent:", error);
			return false;
		});
	}

	/**
	 * Check if a game can be a child (not already a child or parent)
	 */
	async canBeChild(gameId: string): Promise<boolean> {
		return await call<[string], boolean>(
			BACK_END_API.CAN_GAME_BE_CHILD,
			gameId,
		).catch((error) => {
			logger.error("Failed to check if game can be child:", error);
			return false;
		});
	}
}
