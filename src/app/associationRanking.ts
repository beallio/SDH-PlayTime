import type {
	GamePresenceCandidate,
	GamePresenceInventoryCompleteness,
} from "./gamePresence";

export type AssociationRankingReasonCode =
	| "confirmed_parent_missing"
	| "component_conflict"
	| "inventory_incomplete"
	| "member_inventory_unknown"
	| "current_member_unavailable"
	| "multiple_running_members"
	| "multiple_reachable_members"
	| "all_members_historical"
	| "no_reachable_member";

export type AssociationRankingReason = { code: AssociationRankingReasonCode };

export type AssociationParentRecommendation = {
	gameId: string;
	tier: "running" | "reachable";
};

export type AssociationRankingInput = {
	candidates: ReadonlyArray<GamePresenceCandidate>;
	inventories: Record<
		"native_steam" | "non_steam",
		GamePresenceInventoryCompleteness
	>;
	confirmedParentId: string | null;
	conflict: boolean;
};

export type AssociationRankingResult = {
	status: "confirmed" | "recommended" | "review_required";
	effectiveParentId: string | null;
	advisoryRecommendation: AssociationParentRecommendation | null;
	reasons: AssociationRankingReason[];
	candidates: GamePresenceCandidate[];
};

function sourceRank(source: GamePresenceCandidate["source"]) {
	switch (source) {
		case "native_steam":
			return 0;
		case "non_steam":
			return 1;
		case "unknown":
			return 2;
	}
}

function numericId(id: string) {
	return /^\d+$/.test(id) ? Number(id) : undefined;
}

/**
 * Produces a stable presentation order only. Callers must use the recommendation
 * result, rather than this ordering, to choose a parent.
 */
export function sortAssociationCandidatesForDisplay(
	candidates: ReadonlyArray<GamePresenceCandidate>,
): GamePresenceCandidate[] {
	return [...candidates].sort((left, right) => {
		const sourceComparison = sourceRank(left.source) - sourceRank(right.source);
		if (sourceComparison !== 0) return sourceComparison;
		if (left.recentPlaytime !== right.recentPlaytime) {
			return right.recentPlaytime - left.recentPlaytime;
		}
		if (left.totalPlaytime !== right.totalPlaytime) {
			return right.totalPlaytime - left.totalPlaytime;
		}
		const leftNumericId = numericId(left.id);
		const rightNumericId = numericId(right.id);
		if (leftNumericId !== undefined && rightNumericId !== undefined) {
			const numericComparison = leftNumericId - rightNumericId;
			if (numericComparison !== 0) return numericComparison;
		}
		return left.id.localeCompare(right.id);
	});
}

function review(
	candidates: ReadonlyArray<GamePresenceCandidate>,
	code: AssociationRankingReasonCode,
): AssociationRankingResult {
	return {
		status: "review_required",
		effectiveParentId: null,
		advisoryRecommendation: null,
		reasons: [{ code }],
		candidates: sortAssociationCandidatesForDisplay(candidates),
	};
}

/**
 * Selects only from unambiguous live evidence. A confirmation always remains the
 * effective parent; any automatic result is deliberately advisory.
 */
export function rankAssociationParent(
	input: AssociationRankingInput,
): AssociationRankingResult {
	const candidates = sortAssociationCandidatesForDisplay(input.candidates);
	if (input.confirmedParentId) {
		return {
			status: "confirmed",
			effectiveParentId: input.confirmedParentId,
			advisoryRecommendation: null,
			reasons: candidates.some(
				(candidate) => candidate.id === input.confirmedParentId,
			)
				? []
				: [{ code: "confirmed_parent_missing" }],
			candidates,
		};
	}
	if (input.conflict) return review(candidates, "component_conflict");
	if (
		input.inventories.native_steam.status !== "complete" ||
		input.inventories.non_steam.status !== "complete"
	) {
		return review(candidates, "inventory_incomplete");
	}
	if (
		candidates.some((candidate) => candidate.inventory.status === "unknown")
	) {
		return review(candidates, "member_inventory_unknown");
	}
	const current = candidates.filter(
		(candidate) => candidate.inventory.status === "current",
	);
	if (
		current.some(
			(candidate) =>
				candidate.availability.status === "unknown" ||
				candidate.availability.status === "unreachable",
		)
	) {
		return review(candidates, "current_member_unavailable");
	}
	if (current.length === 0) return review(candidates, "all_members_historical");

	const running = current.filter(
		(candidate) => candidate.availability.status === "running",
	);
	if (running.length > 1) return review(candidates, "multiple_running_members");
	if (running.length === 1) {
		const selected = running[0] as GamePresenceCandidate;
		return {
			status: "recommended",
			effectiveParentId: selected.id,
			advisoryRecommendation: { gameId: selected.id, tier: "running" },
			reasons: [],
			candidates,
		};
	}

	const reachable = current.filter(
		(candidate) => candidate.availability.status === "reachable",
	);
	if (reachable.length > 1)
		return review(candidates, "multiple_reachable_members");
	if (reachable.length === 1) {
		const selected = reachable[0] as GamePresenceCandidate;
		return {
			status: "recommended",
			effectiveParentId: selected.id,
			advisoryRecommendation: { gameId: selected.id, tier: "reachable" },
			reasons: [],
			candidates,
		};
	}
	return review(candidates, "no_reachable_member");
}
