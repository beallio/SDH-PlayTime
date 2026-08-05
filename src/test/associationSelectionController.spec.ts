import { describe, expect, test } from "bun:test";
import type { GamePresenceSnapshot } from "@src/app/gamePresence";
import type { AssociationComponentSnapshot } from "@src/types/association";
import {
	createAssociationRequestCoordinator,
	getInitialAssociationComponentSelection,
} from "@src/pages/association/associationSelectionController";

const snapshot: AssociationComponentSnapshot = {
	anchorGameId: "anchor",
	expectedParentGameId: null,
	existingMembers: [
		{ gameId: "anchor", gameName: "Anchor" },
		{ gameId: "candidate", gameName: "Candidate" },
	],
	fingerprint: "fingerprint",
	status: "unconfirmed",
	aliases: [],
};

function presence(availability: "running" | "reachable"): GamePresenceSnapshot {
	return {
		inventories: {
			native_steam: { status: "complete" },
			non_steam: { status: "complete" },
		},
		candidates: [
			{
				id: "anchor",
				name: "Anchor",
				source: "native_steam",
				tracked: true,
				recentPlaytime: 0,
				totalPlaytime: 0,
				inventory: { status: "current", reasons: [] },
				availability: { status: "reachable", reasons: [] },
			},
			{
				id: "candidate",
				name: "Candidate",
				source: "native_steam",
				tracked: true,
				recentPlaytime: 0,
				totalPlaytime: 0,
				inventory: { status: "current", reasons: [] },
				availability: { status: availability, reasons: [] },
			},
		],
	};
}

describe("association selection controller", () => {
	test("ignores an out-of-order component response after a newer anchor request", () => {
		const coordinator = createAssociationRequestCoordinator();
		const olderRequest = coordinator.begin();
		const newerRequest = coordinator.begin();
		const committed: string[] = [];

		if (coordinator.isCurrent(newerRequest)) committed.push("newer-anchor");
		if (coordinator.isCurrent(olderRequest)) committed.push("older-anchor");

		expect(committed).toEqual(["newer-anchor"]);
	});

	test("ranks with the freshly supplied presence snapshot rather than stale evidence", () => {
		const stale = getInitialAssociationComponentSelection(
			snapshot,
			presence("reachable"),
		);
		const refreshed = getInitialAssociationComponentSelection(
			snapshot,
			presence("running"),
		);

		expect(stale.selectedParentId).toBeNull();
		expect(refreshed.selectedParentId).toBe("candidate");
		expect(refreshed.selectedMemberIds).toEqual(["anchor", "candidate"]);
	});
});
