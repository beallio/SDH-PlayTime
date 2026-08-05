import { rankAssociationParent } from "@src/app/associationRanking";
import type { GamePresenceSnapshot } from "@src/app/gamePresence";
import type { AssociationComponentSnapshot } from "@src/types/association";
import {
	getAssociationComponentCandidates,
	selectInitialAssociationParent,
} from "./associationViewModel";

const incompleteInventories: GamePresenceSnapshot["inventories"] = {
	native_steam: { status: "incomplete", reason: "loading" },
	non_steam: { status: "incomplete", reason: "loading" },
};

/** Last-request-wins guard shared by association component and presence reads. */
export function createAssociationRequestCoordinator() {
	let latestRequest = 0;
	return {
		begin() {
			latestRequest += 1;
			return latestRequest;
		},
		isCurrent(request: number) {
			return request === latestRequest;
		},
		current() {
			return latestRequest;
		},
		invalidate() {
			latestRequest += 1;
		},
	};
}

/** Derives a component's initial explicit selection from the exact presence snapshot supplied. */
export function getInitialAssociationComponentSelection(
	snapshot: AssociationComponentSnapshot,
	presence: GamePresenceSnapshot | null,
) {
	const candidates = getAssociationComponentCandidates(
		snapshot,
		presence?.candidates ?? [],
	);
	return {
		selectedMemberIds: snapshot.existingMembers.map((member) => member.gameId),
		selectedParentId: selectInitialAssociationParent({
			candidates,
			inventories: presence?.inventories ?? incompleteInventories,
			confirmedParentId: snapshot.expectedParentGameId,
			conflict: snapshot.status === "conflict",
		}),
		ranking: rankAssociationParent({
			candidates,
			inventories: presence?.inventories ?? incompleteInventories,
			confirmedParentId: snapshot.expectedParentGameId,
			conflict: snapshot.status === "conflict",
		}),
	};
}
