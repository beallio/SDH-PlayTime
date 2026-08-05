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
	getAssociationActionDecision,
	getAssociationComponentCandidates,
	getAssociationContextMenuAction,
	selectInitialAssociationParent,
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
	test("keeps duplicate names distinguishable and maps inventory, availability, and manual warnings", () => {
		const cards = buildAssociationCandidateCards({
			candidates: [
				candidate("steam", "running", { source: "native_steam" }),
				candidate("shortcut", "unreachable", {
					availability: {
						status: "unreachable",
						reasons: [{ code: "resolver_unreachable", source: "resolver" }],
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
			["Duplicate name", "shortcut"],
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
			sourceLabel: "Non-Steam shortcut",
			availabilityLabel: "Drive disconnected",
			manualParentWarning:
				"This entry cannot be verified as available on this Deck. Selecting it does not claim that it is installed.",
		});
		expect(cards[2]).toMatchObject({
			inventoryLabel: "Status unavailable",
			availabilityLabel: "Status unavailable",
		});
		expect(cards[3].availabilityLabel).toBe("Installation missing");
		expect(cards[4].inventoryLabel).toBe("Historical record");
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

	test("refreshes stale or conflict errors instead of silently retrying", () => {
		expect(shouldRefreshAssociationComponent("STALE_COMPONENT")).toBe(true);
		expect(shouldRefreshAssociationComponent("COMPONENT_CONFLICT")).toBe(true);
		expect(shouldRefreshAssociationComponent("NETWORK_ERROR")).toBe(false);
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
		expect(getAssociationContextMenuAction("parent")).toEqual(
			getAssociationActionDecision("change-parent"),
		);
	});
});
