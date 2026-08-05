import {
	rankAssociationParent,
	type AssociationRankingInput,
	type AssociationRankingReason,
} from "@src/app/associationRanking";
import type { GamePresenceCandidate } from "@src/app/gamePresence";
import type {
	AssociationComponentMember,
	AssociationComponentSnapshot,
	ConfirmAssociationComponentDTO,
	GameAssociation,
} from "@src/types/association";

export type AssociationCandidateCard = {
	id: string;
	title: string;
	sourceLabel: string;
	trackedTimeLabel: string;
	inventoryLabel: string;
	availabilityLabel: string;
	recommendationLabel?: string;
	manualParentWarning?: string;
	isSelectedParent: boolean;
};

export type AssociationConfirmationSummary = {
	oldParent: AssociationComponentMember | null;
	proposedParent: AssociationComponentMember;
	affectedMembers: string[];
	selectedMembers: AssociationComponentMember[];
	reasons: string[];
	warnings: string[];
};

export type AssociationListGroup = {
	anchorGameId: string;
	parent: AssociationCandidateCard;
	children: AssociationCandidateCard[];
};

const MANUAL_PARENT_WARNING =
	"This entry cannot be verified as available on this Deck. Selecting it does not claim that it is installed.";

function formatTrackedTime(totalSeconds: number) {
	const totalMinutes = Math.max(0, Math.floor(totalSeconds / 60));
	const hours = Math.floor(totalMinutes / 60);
	const minutes = totalMinutes % 60;
	if (hours === 0) return `${minutes}m`;
	if (minutes === 0) return `${hours}h`;
	return `${hours}h ${minutes}m`;
}

function sourceLabel(candidate: GamePresenceCandidate) {
	switch (candidate.source) {
		case "native_steam":
			return "Steam library";
		case "non_steam":
			return "Non-Steam shortcut";
		case "unknown":
			return "Unknown source";
	}
}

function inventoryLabel(candidate: GamePresenceCandidate) {
	switch (candidate.inventory.status) {
		case "current":
			return "Current library entry";
		case "historical":
			return "Historical record";
		case "unknown":
			return "Status unavailable";
	}
}

function availabilityLabel(candidate: GamePresenceCandidate) {
	switch (candidate.availability.status) {
		case "running":
			return "Running now";
		case "reachable":
			return "Available on this Deck";
		case "unknown":
			return "Status unavailable";
		case "unreachable":
			return candidate.availability.reasons.some(
				(reason) => reason.code === "native_not_installed",
			)
				? "Installation missing"
				: "Drive disconnected";
	}
}

function requiresManualParentWarning(candidate: GamePresenceCandidate) {
	return (
		candidate.availability.status === "unreachable" ||
		candidate.availability.status === "unknown"
	);
}

function fallbackCandidate(
	member: AssociationComponentMember,
): GamePresenceCandidate {
	return {
		id: member.gameId,
		name: member.gameName,
		source: "unknown",
		tracked: false,
		recentPlaytime: 0,
		totalPlaytime: 0,
		inventory: { status: "unknown", reasons: [] },
		availability: { status: "unknown", reasons: [] },
	};
}

/** Joins an explicit backend component to presence data without widening it to inventory. */
export function getAssociationComponentCandidates(
	snapshot: AssociationComponentSnapshot,
	candidates: ReadonlyArray<GamePresenceCandidate>,
) {
	const candidatesById = new Map(
		candidates.map((candidate) => [candidate.id, candidate]),
	);
	return snapshot.existingMembers.map(
		(member) => candidatesById.get(member.gameId) ?? fallbackCandidate(member),
	);
}

export function associationRankingReasonLabels(
	reasons: ReadonlyArray<AssociationRankingReason>,
) {
	return reasons.map(({ code }) => {
		switch (code) {
			case "confirmed_parent_missing":
				return "The confirmed parent is not present in the current status refresh.";
			case "component_conflict":
				return "This group has conflicting associations and needs an explicit full selection.";
			case "inventory_incomplete":
				return "Library inventory is incomplete, so no parent was selected automatically.";
			case "member_inventory_unknown":
				return "At least one member has unavailable inventory status.";
			case "current_member_unavailable":
				return "At least one current member is unavailable on this Deck.";
			case "multiple_running_members":
				return "More than one member is running now; choose a parent explicitly.";
			case "multiple_reachable_members":
				return "More than one member is available on this Deck; choose a parent explicitly.";
			case "all_members_historical":
				return "All members are historical records; choose a parent explicitly.";
			case "no_reachable_member":
				return "No member can be verified as available on this Deck.";
		}
		return "Status unavailable.";
	});
}

/** Presents evidence without turning availability into an installed claim. */
export function buildAssociationCandidateCards({
	candidates,
	selectedParentId,
	recommendedParentId,
}: {
	candidates: ReadonlyArray<GamePresenceCandidate>;
	selectedParentId: string | null;
	recommendedParentId: string | null;
}): AssociationCandidateCard[] {
	return candidates.map((candidate) => ({
		id: candidate.id,
		title: candidate.name,
		sourceLabel: sourceLabel(candidate),
		trackedTimeLabel: candidate.tracked
			? `Tracked time: ${formatTrackedTime(candidate.totalPlaytime)}`
			: "No tracked time",
		inventoryLabel: inventoryLabel(candidate),
		availabilityLabel: availabilityLabel(candidate),
		recommendationLabel:
			candidate.id === recommendedParentId ? "Recommended parent" : undefined,
		manualParentWarning: requiresManualParentWarning(candidate)
			? MANUAL_PARENT_WARNING
			: undefined,
		isSelectedParent: candidate.id === selectedParentId,
	}));
}

/** Only a backend-confirmed parent or unambiguous evidence may preselect a parent. */
export function selectInitialAssociationParent(input: AssociationRankingInput) {
	const ranking = rankAssociationParent(input);
	return ranking.status === "confirmed" || ranking.status === "recommended"
		? ranking.effectiveParentId
		: null;
}

function memberById(
	members: ReadonlyArray<AssociationComponentMember>,
	gameId: string,
) {
	const member = members.find((item) => item.gameId === gameId);
	if (!member)
		throw new Error("The selected association member is no longer present.");
	return member;
}

export function buildAssociationConfirmationSummary({
	snapshot,
	candidates,
	selectedMemberIds,
	proposedParentId,
	reasons,
}: {
	snapshot: AssociationComponentSnapshot;
	candidates: ReadonlyArray<GamePresenceCandidate>;
	selectedMemberIds: ReadonlyArray<string>;
	proposedParentId: string;
	reasons: string[];
}): AssociationConfirmationSummary {
	const selectedIds = new Set(selectedMemberIds);
	const selectedMembers = snapshot.existingMembers.filter((member) =>
		selectedIds.has(member.gameId),
	);
	const proposedParent = memberById(selectedMembers, proposedParentId);
	const candidatesById = new Map(
		candidates.map((candidate) => [candidate.id, candidate]),
	);
	const selectedCandidate = candidatesById.get(proposedParentId);
	return {
		oldParent: snapshot.expectedParentGameId
			? memberById(snapshot.existingMembers, snapshot.expectedParentGameId)
			: null,
		proposedParent,
		affectedMembers: selectedMembers.map((member) => member.gameId),
		selectedMembers,
		reasons,
		warnings:
			selectedCandidate && requiresManualParentWarning(selectedCandidate)
				? [MANUAL_PARENT_WARNING]
				: [],
	};
}

/** Creates the optimistic-concurrency payload only after a user accepts a summary. */
export function buildAssociationConfirmationRequest({
	snapshot,
	confirmation,
}: {
	snapshot: AssociationComponentSnapshot;
	confirmation: AssociationConfirmationSummary;
}): ConfirmAssociationComponentDTO {
	return {
		anchor_game_id: snapshot.anchorGameId,
		proposed_parent_game_id: confirmation.proposedParent.gameId,
		proposed_parent_game_name: confirmation.proposedParent.gameName,
		expected_parent_game_id: snapshot.expectedParentGameId,
		expected_fingerprint: snapshot.fingerprint,
		selected_members: [...confirmation.selectedMembers]
			.sort((left, right) => left.gameId.localeCompare(right.gameId))
			.map((member) => ({
				game_id: member.gameId,
				game_name: member.gameName,
			})),
	};
}

export function shouldRefreshAssociationComponent(
	errorCode: string | undefined,
) {
	return errorCode === "STALE_COMPONENT" || errorCode === "COMPONENT_CONFLICT";
}

/** Groups only explicit parent-child edges; it never infers a group from inventory. */
export function buildAssociationListGroups(
	associations: ReadonlyArray<GameAssociation>,
	candidates: ReadonlyArray<GamePresenceCandidate>,
): AssociationListGroup[] {
	const candidatesById = new Map(
		candidates.map((candidate) => [candidate.id, candidate]),
	);
	const grouped = new Map<string, GameAssociation[]>();
	for (const association of associations) {
		const children = grouped.get(association.parentGameId) ?? [];
		children.push(association);
		grouped.set(association.parentGameId, children);
	}
	return [...grouped.entries()].map(([parentGameId, children]) => {
		const first = children[0] as GameAssociation;
		const parent =
			candidatesById.get(parentGameId) ??
			fallbackCandidate({
				gameId: parentGameId,
				gameName: first.parentGameName,
			});
		return {
			anchorGameId: parentGameId,
			parent: buildAssociationCandidateCards({
				candidates: [parent],
				selectedParentId: parentGameId,
				recommendedParentId: null,
			})[0] as AssociationCandidateCard,
			children: children.map((child) => {
				const candidate =
					candidatesById.get(child.childGameId) ??
					fallbackCandidate({
						gameId: child.childGameId,
						gameName: child.childGameName,
					});
				return buildAssociationCandidateCards({
					candidates: [candidate],
					selectedParentId: null,
					recommendedParentId: null,
				})[0] as AssociationCandidateCard;
			}),
		};
	});
}

export type AssociationAction =
	| "change-parent"
	| "detach-child"
	| "remove-parent"
	| "dissolve";

export function getAssociationActionDecision(action: AssociationAction) {
	switch (action) {
		case "detach-child":
			return { action: "detach" as const, retainsHistory: true };
		case "change-parent":
		case "remove-parent":
			return {
				action: "open-group-selector" as const,
				requiresConfirmation: true,
			};
		case "dissolve":
			return { action: "dissolve" as const, removesExplicitEdges: true };
	}
}

/** Context menus deliberately route into the same confirmation-capable selector. */
export function getAssociationContextMenuAction(_anchorGameId: string) {
	return getAssociationActionDecision("change-parent");
}
