/**
 * A game association links a child game to a parent game.
 * When associated, the child game's playtime is combined with the parent's in statistics.
 */
export type GameAssociation = {
	parentGameId: string;
	parentGameName: string;
	childGameId: string;
	childGameName: string;
	createdAt?: string;
};

/**
 * DTO for creating a game association
 */
export type CreateGameAssociationDTO = {
	parent_game_id: string;
	child_game_id: string;
};

/**
 * Response from association API operations
 */
export type AssociationResult = {
	success: boolean;
	error?: {
		code: string;
		message: string;
	};
};

export type AssociationComponentMember = {
	gameId: string;
	gameName: string;
};

export type AssociationComponentMemberDTO = {
	game_id: string;
	game_name: string;
};

export type AssociationCandidate = {
	game: {
		id: string;
		name: string;
	};
	duration: number;
};

export type AssociationComponentSnapshot = {
	anchorGameId: string;
	expectedParentGameId: string | null;
	existingMembers: AssociationComponentMember[];
	fingerprint: string;
	status: "confirmed" | "unconfirmed" | "conflict";
	aliases: string[];
};

export type ConfirmAssociationComponentDTO = {
	anchor_game_id: string;
	proposed_parent_game_id: string;
	proposed_parent_game_name: string;
	expected_parent_game_id: string | null;
	expected_fingerprint: string;
	selected_members: AssociationComponentMemberDTO[];
};

export type AssociationComponentConfirmation = AssociationComponentSnapshot & {
	proposedParent: AssociationComponentMember;
	selectedMembers: AssociationComponentMember[];
	confirmedParent: AssociationComponentMember;
	status: "confirmed";
};

export type AssociationComponentReadResult =
	| { success: true; data: AssociationComponentSnapshot }
	| { success: false; error: NonNullable<AssociationResult["error"]> };

export type AssociationComponentConfirmationResult =
	| { success: true; data: AssociationComponentConfirmation }
	| { success: false; error: NonNullable<AssociationResult["error"]> };

/**
 * Association info for a specific game
 */
export type GameAssociationInfo =
	| {
			role: "parent";
			children: Array<{
				gameId: string;
				gameName: string;
			}>;
	  }
	| {
			role: "child";
			parentGameId: string;
			parentGameName: string;
	  }
	| null;
