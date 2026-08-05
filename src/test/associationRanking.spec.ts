import { describe, expect, test } from "bun:test";
import {
	rankAssociationParent,
	sortAssociationCandidatesForDisplay,
	type AssociationRankingInput,
} from "@src/app/associationRanking";
import type { GamePresenceCandidate } from "@src/app/gamePresence";

function candidate(
	id: string,
	availability: GamePresenceCandidate["availability"]["status"],
	overrides: Partial<GamePresenceCandidate> = {},
): GamePresenceCandidate {
	return {
		id,
		name: `Game ${id}`,
		source: "non_steam",
		tracked: true,
		recentPlaytime: 0,
		totalPlaytime: 0,
		inventory: { status: "current", reasons: [] },
		availability: { status: availability, reasons: [] },
		...overrides,
	};
}

function rank(overrides: Partial<AssociationRankingInput> = {}) {
	return rankAssociationParent({
		candidates: [],
		inventories: {
			native_steam: { status: "complete" },
			non_steam: { status: "complete" },
		},
		confirmedParentId: null,
		conflict: false,
		...overrides,
	});
}

describe("rankAssociationParent", () => {
	test("recommends the sole running member, then the sole current and reachable member", () => {
		expect(
			rank({
				candidates: [candidate("a", "running"), candidate("b", "reachable")],
			}),
		).toMatchObject({
			status: "recommended",
			effectiveParentId: "a",
			advisoryRecommendation: { gameId: "a", tier: "running" },
		});
		expect(
			rank({
				candidates: [
					candidate("a", "unknown", {
						inventory: { status: "historical", reasons: [] },
					}),
					candidate("b", "reachable"),
				],
			}),
		).toMatchObject({
			status: "recommended",
			effectiveParentId: "b",
			advisoryRecommendation: { gameId: "b", tier: "reachable" },
		});
	});

	test("does not break semantic ties with source, playtime, or IDs", () => {
		const result = rank({
			candidates: [
				candidate("999", "reachable", {
					source: "native_steam",
					recentPlaytime: 999,
					totalPlaytime: 9999,
				}),
				candidate("1", "reachable", {
					source: "non_steam",
					recentPlaytime: 1,
					totalPlaytime: 1,
				}),
			],
		});

		expect(result).toMatchObject({
			status: "review_required",
			effectiveParentId: null,
			reasons: [{ code: "multiple_reachable_members" }],
		});
		expect(
			sortAssociationCandidatesForDisplay(result.candidates).map(
				(item) => item.id,
			),
		).toEqual(["999", "1"]);
	});

	test("requires review for incomplete inventory, unknown or unreachable current members, and all historical groups", () => {
		expect(
			rank({
				inventories: {
					native_steam: { status: "incomplete", reason: "failed" },
					non_steam: { status: "complete" },
				},
				candidates: [candidate("a", "reachable")],
			}),
		).toMatchObject({ reasons: [{ code: "inventory_incomplete" }] });
		expect(
			rank({
				candidates: [candidate("a", "reachable"), candidate("b", "unknown")],
			}),
		).toMatchObject({
			reasons: [{ code: "current_member_unavailable" }],
		});
		expect(rank({ candidates: [candidate("a", "unreachable")] })).toMatchObject(
			{
				reasons: [{ code: "current_member_unavailable" }],
			},
		);
		expect(
			rank({
				candidates: [
					candidate("a", "unknown", {
						inventory: { status: "historical", reasons: [] },
					}),
				],
			}),
		).toMatchObject({ reasons: [{ code: "all_members_historical" }] });
	});

	test("keeps a confirmed parent effective regardless of a later advisory ambiguity", () => {
		const result = rank({
			confirmedParentId: "confirmed",
			candidates: [
				candidate("confirmed", "unreachable"),
				candidate("other", "reachable"),
			],
		});

		expect(result).toMatchObject({
			status: "confirmed",
			effectiveParentId: "confirmed",
			advisoryRecommendation: null,
		});
	});

	test("is input-order independent and keeps conflicts out of automatic selection", () => {
		const members = [candidate("a", "running"), candidate("b", "reachable")];
		expect(rank({ candidates: members })).toMatchObject({
			status: "recommended",
			effectiveParentId: "a",
		});
		expect(rank({ candidates: [...members].reverse() })).toMatchObject({
			status: "recommended",
			effectiveParentId: "a",
		});
		expect(rank({ candidates: members, conflict: true })).toMatchObject({
			status: "review_required",
			reasons: [{ code: "component_conflict" }],
		});
		expect(
			rank({
				candidates: [candidate("a", "running"), candidate("b", "running")],
			}),
		).toMatchObject({
			status: "review_required",
			reasons: [{ code: "multiple_running_members" }],
		});
	});
});
