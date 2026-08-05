import { describe, expect, test } from "bun:test";
import type { GamePresenceSnapshot } from "@src/app/gamePresence";
import type { AssociationComponentSnapshot } from "@src/types/association";
import {
	createAssociationSelectionController,
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

function presence(
	availability: "running" | "reachable",
	candidates = [
		candidate("anchor", "reachable"),
		candidate("candidate", availability),
	],
): GamePresenceSnapshot {
	return {
		inventories: {
			native_steam: { status: "complete" },
			non_steam: { status: "complete" },
		},
		candidates,
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

	test("re-ranks the exact selected group and updates an untouched advisory parent", async () => {
		const controller = createAssociationSelectionController({
			snapshot: {
				...snapshot,
				existingMembers: [{ gameId: "anchor", gameName: "Anchor" }],
			},
			presence: presence("reachable", [
				candidate("anchor", "reachable"),
				candidate("running", "running"),
			]),
		});

		expect(controller.getState().selectedParentId).toBe("anchor");
		await controller.toggleMember("running", async () => component("running"));

		expect(controller.getState()).toMatchObject({
			selectedMemberIds: ["anchor", "running"],
			selectedParentId: "running",
			ranking: { advisoryRecommendation: { gameId: "running" } },
		});
	});

	test("requires a manual parent after selected additions create a semantic tie and re-ranks after removal", async () => {
		const controller = createAssociationSelectionController({
			snapshot: {
				...snapshot,
				existingMembers: [{ gameId: "anchor", gameName: "Anchor" }],
			},
			presence: presence("reachable", [
				candidate("anchor", "unknown", {
					inventory: { status: "historical", reasons: [] },
				}),
				candidate("first", "reachable"),
				candidate("second", "reachable"),
			]),
		});

		await controller.toggleMember("first", async () => component("first"));
		expect(controller.getState().selectedParentId).toBe("first");
		await controller.toggleMember("second", async () => component("second"));
		expect(controller.getState()).toMatchObject({
			selectedParentId: null,
			ranking: { status: "review_required" },
		});

		await controller.toggleMember("second", async () => component("second"));
		expect(controller.getState().selectedParentId).toBe("first");
	});

	test("preserves a manual parent choice when selected additions change", async () => {
		const controller = createAssociationSelectionController({
			snapshot,
			presence: presence("reachable", [
				candidate("anchor", "reachable"),
				candidate("candidate", "unknown"),
				candidate("running", "running"),
			]),
		});

		await controller.selectParent("candidate", async () =>
			component("candidate"),
		);
		await controller.toggleMember("running", async () => component("running"));

		expect(controller.getState()).toMatchObject({
			selectedParentId: "candidate",
			parentSelectionKind: "manual",
		});
	});

	test("preserves the confirmed backend parent while selected additions change", async () => {
		const controller = createAssociationSelectionController({
			snapshot: { ...snapshot, expectedParentGameId: "candidate" },
			presence: presence("reachable", [
				candidate("anchor", "reachable"),
				candidate("candidate", "reachable"),
				candidate("running", "running"),
			]),
		});

		await controller.toggleMember("running", async () => component("running"));

		expect(controller.getState()).toMatchObject({
			selectedParentId: "candidate",
			parentSelectionKind: "confirmed",
			ranking: { status: "confirmed", effectiveParentId: "candidate" },
		});
	});

	test("keeps the newest async parent eligibility decision", async () => {
		const first = deferred<ReturnType<typeof component>>();
		const second = deferred<ReturnType<typeof component>>();
		const controller = createAssociationSelectionController({
			snapshot: {
				...snapshot,
				existingMembers: [{ gameId: "anchor", gameName: "Anchor" }],
			},
			presence: presence("reachable", [
				candidate("anchor", "reachable"),
				candidate("first", "reachable"),
				candidate("second", "reachable"),
			]),
		});

		const older = controller.selectParent("first", () => first.promise);
		const newer = controller.selectParent("second", () => second.promise);
		second.resolve(component("second"));
		await newer;
		first.resolve(component("first"));
		await older;

		expect(controller.getState()).toMatchObject({
			selectedMemberIds: ["anchor", "second"],
			selectedParentId: "second",
			pendingCandidateIds: [],
		});
	});

	test("cancels a pending addition when its include action is immediately undone", async () => {
		const pending = deferred<ReturnType<typeof component>>();
		const controller = selectionController();

		const include = controller.toggleMember("addition", () => pending.promise);
		expect(controller.getState()).toMatchObject({
			pendingCandidateIds: ["addition"],
			canConfirm: false,
		});
		await controller.toggleMember("addition", async () =>
			component("addition"),
		);
		pending.resolve(component("addition"));
		await include;

		expect(controller.getState()).toMatchObject({
			selectedMemberIds: ["anchor", "candidate"],
			pendingCandidateIds: [],
		});
	});

	test("keeps confirmation disabled until a selected-member eligibility check settles", async () => {
		const pending = deferred<ReturnType<typeof component>>();
		const controller = selectionController();

		await controller.selectParent("anchor", async () => component("anchor"));
		expect(controller.getState().canConfirm).toBe(true);
		const include = controller.toggleMember("addition", () => pending.promise);
		expect(controller.getState()).toMatchObject({
			pendingCandidateIds: ["addition"],
			canConfirm: false,
		});
		pending.resolve(component("addition"));
		await include;
		expect(controller.getState().canConfirm).toBe(true);
	});

	test("does not apply a selection response after disposal", async () => {
		const pending = deferred<ReturnType<typeof component>>();
		const controller = selectionController();

		const include = controller.toggleMember("addition", () => pending.promise);
		controller.dispose();
		pending.resolve(component("addition"));
		await include;

		expect(controller.getState().selectedMemberIds).toEqual([
			"anchor",
			"candidate",
		]);
	});

	test("allows current untracked singletons but rejects owned components and network failures", async () => {
		const singleton = selectionController();
		await singleton.toggleMember("addition", async () => ({
			success: false,
			error: { code: "ANCHOR_NOT_FOUND", message: "No stored component" },
		}));
		expect(singleton.getState().selectedMemberIds).toContain("addition");

		const owned = selectionController();
		await owned.toggleMember("addition", async () => ({
			success: true,
			data: {
				...component("addition").data,
				existingMembers: [
					{ gameId: "owned-parent", gameName: "Owned parent" },
					{ gameId: "addition", gameName: "Addition" },
				],
			},
		}));
		expect(owned.getState()).toMatchObject({
			selectedMemberIds: ["anchor", "candidate"],
			additionMessages: {
				addition:
					"This entry already belongs to another logical game group and cannot be added here.",
			},
		});

		const network = selectionController();
		await network.toggleMember("addition", async () => ({
			success: false,
			error: { code: "NETWORK_ERROR", message: "Offline" },
		}));
		expect(network.getState().selectedMemberIds).not.toContain("addition");
		expect(network.getState().additionMessages.addition).toBe(
			"This entry could not be verified as an eligible addition. Refresh status and try again.",
		);
	});
});

function candidate(
	id: string,
	availability: GamePresenceSnapshot["candidates"][number]["availability"]["status"],
	overrides: Partial<GamePresenceSnapshot["candidates"][number]> = {},
) {
	return {
		id,
		name: id === "anchor" ? "Anchor" : id,
		source: "native_steam" as const,
		tracked: true,
		recentPlaytime: 0,
		totalPlaytime: 0,
		inventory: { status: "current" as const, reasons: [] },
		availability: { status: availability, reasons: [] },
		...overrides,
	};
}

function component(gameId: string) {
	return {
		success: true as const,
		data: {
			anchorGameId: gameId,
			expectedParentGameId: null,
			existingMembers: [{ gameId, gameName: gameId }],
			fingerprint: `${gameId}-fingerprint`,
			status: "unconfirmed" as const,
			aliases: [],
		},
	};
}

function selectionController() {
	return createAssociationSelectionController({
		snapshot,
		presence: presence("reachable", [
			candidate("anchor", "running"),
			candidate("candidate", "unknown"),
			candidate("addition", "reachable"),
		]),
	});
}

function deferred<T>() {
	let resolve!: (value: T) => void;
	const promise = new Promise<T>((nextResolve) => {
		resolve = nextResolve;
	});
	return { promise, resolve };
}
