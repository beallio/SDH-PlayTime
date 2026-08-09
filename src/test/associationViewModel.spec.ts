import { describe, expect, test } from "bun:test";
import type {
	GamePresenceCandidate,
	GamePresenceSnapshot,
} from "@src/app/gamePresence";
import type {
	AssociationComponentSnapshot,
	GameAssociation,
} from "@src/types/association";
import {
	buildAssociationCandidateCards,
	buildAssociationConfirmationRequest,
	buildAssociationConfirmationSummary,
	buildAssociationListGroups,
	compareByGameName,
	getAssociationAdditionDecision,
	getAssociationActionDecision,
	getAssociationComponentCandidates,
	getAssociationContextMenuAction,
	getAssociationListChangeParentAction,
	getAssociationListDisplayState,
	selectInitialAssociationParent,
	shouldRefreshAfterAssociationMutation,
	shouldRefreshAssociationComponent,
} from "@src/pages/association/associationViewModel";

function candidate(
	id: string,
	availability: GamePresenceCandidate["availability"]["status"],
	overrides: Partial<GamePresenceCandidate> = {},
): GamePresenceCandidate {
	return {
		id,
		name: "Duplicate name",
		source: "non_steam",
		tracked: true,
		recentPlaytime: 120,
		totalPlaytime: 3720,
		inventory: { status: "current", reasons: [] },
		availability: { status: availability, reasons: [] },
		...overrides,
	};
}

const inventories: GamePresenceSnapshot["inventories"] = {
	native_steam: { status: "complete" },
	non_steam: { status: "complete" },
};

const snapshot: AssociationComponentSnapshot = {
	anchorGameId: "shortcut",
	expectedParentGameId: "steam",
	existingMembers: [
		{ gameId: "steam", gameName: "Duplicate name" },
		{ gameId: "shortcut", gameName: "Duplicate name" },
	],
	fingerprint: "snapshot-fingerprint",
	status: "confirmed",
	aliases: ["shortcut"],
};

describe("association view model", () => {
	test("sorts cards by displayed name", () => {
		const cards = [
			{ title: "Zelda", id: "z" },
			{ title: "Animal Crossing", id: "a" },
		];

		expect(cards.sort(compareByGameName).map((card) => card.title)).toEqual([
			"Animal Crossing",
			"Zelda",
		]);
	});

	test("uses localeCompare for mixed-case names", () => {
		expect(
			compareByGameName(
				{ title: "alpha", id: "alpha" },
				{ title: "Beta", id: "beta" },
			),
		).toBeLessThan(0);
	});

	test("uses game ID as a deterministic duplicate-name tiebreak", () => {
		const cards = [
			{ title: "Transformers Devastation", id: "3843090730" },
			{ title: "Transformers Devastation", id: "3015223078" },
		];

		expect(cards.sort(compareByGameName).map((card) => card.id)).toEqual([
			"3015223078",
			"3843090730",
		]);
	});

	test("keeps duplicate names distinguishable and preserves launcher and resolver evidence", () => {
		const cards = buildAssociationCandidateCards({
			candidates: [
				candidate("steam", "running", { source: "native_steam" }),
				candidate("direct", "reachable", {
					launcherKind: "direct",
				}),
				candidate("heroic", "reachable", {
					launcherKind: "heroic",
				}),
				candidate("disconnected", "unreachable", {
					availability: {
						status: "unreachable",
						reasons: [{ code: "drive_disconnected", source: "resolver" }],
					},
				}),
				candidate("payload-missing", "unreachable", {
					availability: {
						status: "unreachable",
						reasons: [{ code: "payload_missing", source: "resolver" }],
					},
				}),
				candidate("mismatch", "unreachable", {
					availability: {
						status: "unreachable",
						reasons: [{ code: "kind_mismatch", source: "resolver" }],
					},
				}),
				candidate("unknown", "unknown", {
					tracked: false,
					inventory: {
						status: "unknown",
						reasons: [
							{ code: "inventory_source_unknown", source: "non_steam" },
						],
					},
				}),
				candidate("missing", "unreachable", {
					availability: {
						status: "unreachable",
						reasons: [{ code: "native_not_installed", source: "native_steam" }],
					},
				}),
				candidate("historical", "unknown", {
					inventory: { status: "historical", reasons: [] },
				}),
			],
			selectedParentId: "steam",
			recommendedParentId: "steam",
		});

		expect(cards.map((card) => [card.title, card.id])).toEqual([
			["Duplicate name", "steam"],
			["Duplicate name", "direct"],
			["Duplicate name", "heroic"],
			["Duplicate name", "disconnected"],
			["Duplicate name", "payload-missing"],
			["Duplicate name", "mismatch"],
			["Duplicate name", "unknown"],
			["Duplicate name", "missing"],
			["Duplicate name", "historical"],
		]);
		expect(cards[0]).toMatchObject({
			sourceLabel: "Steam library",
			trackedTimeLabel: "Tracked time: 1h 2m",
			inventoryLabel: "Current library entry",
			availabilityLabel: "Running now",
			recommendationLabel: "Recommended parent",
		});
		expect(cards[1]).toMatchObject({
			sourceLabel: "Direct shortcut",
			availabilityLabel: "Available on this Deck",
		});
		expect(cards[2]).toMatchObject({
			sourceLabel: "Heroic shortcut",
			availabilityLabel: "Available on this Deck",
		});
		expect(cards[3]).toMatchObject({
			availabilityLabel: "Drive disconnected",
			manualParentWarning:
				"This entry cannot be verified as available on this Deck. Selecting it does not claim that it is installed.",
		});
		expect(cards[4].availabilityLabel).toBe("Installation missing");
		expect(cards[5]).toMatchObject({
			availabilityLabel: "Status unavailable",
			manualParentWarning:
				"This entry cannot be verified as available on this Deck. Selecting it does not claim that it is installed.",
		});
		expect(cards[6]).toMatchObject({
			inventoryLabel: "Status unavailable",
			availabilityLabel: "Status unavailable",
		});
		expect(cards[7].availabilityLabel).toBe("Installation missing");
		expect(cards[8].inventoryLabel).toBe("Historical record");
	});

	test("preselects only a reliable recommendation and does not choose semantic ties", () => {
		expect(
			selectInitialAssociationParent({
				candidates: [
					candidate("running", "running"),
					candidate("other", "reachable"),
				],
				inventories,
				confirmedParentId: null,
				conflict: false,
			}),
		).toBe("running");
		expect(
			selectInitialAssociationParent({
				candidates: [
					candidate("first", "reachable"),
					candidate("second", "reachable"),
				],
				inventories,
				confirmedParentId: null,
				conflict: false,
			}),
		).toBeNull();
	});

	test("uses only the selected backend component instead of treating inventory as one group", () => {
		expect(
			getAssociationComponentCandidates(snapshot, [
				candidate("steam", "reachable"),
				candidate("shortcut", "reachable"),
				candidate("unrelated", "running"),
			]).map((item) => item.id),
		).toEqual(["steam", "shortcut"]);
	});

	test("builds an explicit snapshot confirmation and summary without persisting a selection", () => {
		const candidates = [
			candidate("steam", "reachable", { source: "native_steam" }),
			candidate("shortcut", "unreachable"),
		];
		const confirmation = buildAssociationConfirmationSummary({
			snapshot,
			candidates,
			selectedMemberIds: ["shortcut", "steam"],
			proposedParentId: "shortcut",
			reasons: ["A manual parent selection needs review."],
		});

		expect(confirmation).toMatchObject({
			oldParent: { gameId: "steam", gameName: "Duplicate name" },
			proposedParent: { gameId: "shortcut", gameName: "Duplicate name" },
			affectedMembers: ["steam", "shortcut"],
			warnings: [
				"This entry cannot be verified as available on this Deck. Selecting it does not claim that it is installed.",
			],
		});
		expect(
			buildAssociationConfirmationRequest({
				snapshot,
				confirmation,
			}),
		).toEqual({
			anchor_game_id: "shortcut",
			proposed_parent_game_id: "shortcut",
			proposed_parent_game_name: "Duplicate name",
			expected_parent_game_id: "steam",
			expected_fingerprint: "snapshot-fingerprint",
			selected_members: [
				{ game_id: "shortcut", game_name: "Duplicate name" },
				{ game_id: "steam", game_name: "Duplicate name" },
			],
		});
	});

	test("includes explicitly selected singleton additions while keeping the loaded component mandatory", () => {
		const isolatedSnapshot: AssociationComponentSnapshot = {
			anchorGameId: "anchor",
			expectedParentGameId: null,
			existingMembers: [{ gameId: "anchor", gameName: "Duplicate name" }],
			fingerprint: "isolated-fingerprint",
			status: "unconfirmed",
			aliases: [],
		};
		const candidates = [
			candidate("anchor", "reachable"),
			candidate("addition", "reachable"),
		];
		const confirmation = buildAssociationConfirmationSummary({
			snapshot: isolatedSnapshot,
			candidates,
			selectedMemberIds: ["anchor", "addition"],
			proposedParentId: "addition",
			reasons: [],
		});

		expect(confirmation).toMatchObject({
			proposedParent: { gameId: "addition", gameName: "Duplicate name" },
			affectedMembers: ["anchor", "addition"],
		});
		expect(
			buildAssociationConfirmationRequest({
				snapshot: isolatedSnapshot,
				confirmation,
			}),
		).toMatchObject({
			selected_members: [
				{ game_id: "addition", game_name: "Duplicate name" },
				{ game_id: "anchor", game_name: "Duplicate name" },
			],
		});
	});

	test("rejects additions owned by another component before confirmation", () => {
		expect(
			getAssociationAdditionDecision({
				loadedSnapshot: snapshot,
				candidateSnapshot: {
					...snapshot,
					anchorGameId: "other-parent",
					existingMembers: [
						{ gameId: "other-parent", gameName: "Other parent" },
						{ gameId: "addition", gameName: "Duplicate name" },
					],
				},
			}),
		).toEqual({
			action: "reject",
			message:
				"This entry already belongs to another logical game group and cannot be added here.",
		});
	});

	test("refreshes stale or conflict errors instead of silently retrying", () => {
		expect(shouldRefreshAssociationComponent("STALE_COMPONENT")).toBe(true);
		expect(shouldRefreshAssociationComponent("COMPONENT_CONFLICT")).toBe(true);
		expect(shouldRefreshAssociationComponent("NETWORK_ERROR")).toBe(false);
	});

	test("keeps list failures distinct from an empty association list and refreshes groups after successful removal", () => {
		expect(
			getAssociationListDisplayState({ groupCount: 0, hasError: true }),
		).toBe("error");
		expect(
			getAssociationListDisplayState({ groupCount: 0, hasError: false }),
		).toBe("empty");
		expect(
			getAssociationListDisplayState({ groupCount: 1, hasError: true }),
		).toBe("groups");
		expect(shouldRefreshAfterAssociationMutation({ success: true })).toBe(true);
		expect(shouldRefreshAfterAssociationMutation({ success: false })).toBe(
			false,
		);
	});

	test("groups confirmed parents once, retains child actions, and routes parent removal through confirmation", () => {
		const associations: GameAssociation[] = [
			{
				parentGameId: "parent",
				parentGameName:
					"A very long duplicate parent label that must remain data, not identity",
				childGameId: "child-one",
				childGameName: "Duplicate name",
			},
			{
				parentGameId: "parent",
				parentGameName:
					"A very long duplicate parent label that must remain data, not identity",
				childGameId: "child-two",
				childGameName: "Duplicate name",
			},
		];
		const groups = buildAssociationListGroups(associations, [
			candidate("parent", "reachable"),
			candidate("child-one", "reachable"),
			candidate("child-two", "unknown"),
		]);

		expect(groups).toHaveLength(1);
		expect(groups[0]).toMatchObject({
			anchorGameId: "parent",
			parent: { id: "parent", availabilityLabel: "Available on this Deck" },
			children: [{ id: "child-one" }, { id: "child-two" }],
		});
		expect(getAssociationActionDecision("detach-child")).toEqual({
			action: "detach",
			retainsHistory: true,
		});
		expect(getAssociationActionDecision("remove-parent")).toEqual({
			action: "open-group-selector",
			requiresConfirmation: true,
		});
		expect(getAssociationActionDecision("dissolve")).toEqual({
			action: "dissolve",
			removesExplicitEdges: true,
		});
		expect(getAssociationContextMenuAction("parent")).toEqual({
			...getAssociationActionDecision("change-parent"),
			anchorGameId: "parent",
		});
		expect(getAssociationContextMenuAction("parent")).toEqual(
			getAssociationListChangeParentAction("parent"),
		);
	});
});
