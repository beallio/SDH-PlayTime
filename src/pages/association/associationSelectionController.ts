import {
	rankAssociationParent,
	type AssociationRankingResult,
} from "@src/app/associationRanking";
import type {
	GamePresenceCandidate,
	GamePresenceSnapshot,
} from "@src/app/gamePresence";
import type {
	AssociationComponentReadResult,
	AssociationComponentSnapshot,
} from "@src/types/association";
import {
	getAssociationAdditionDecision,
	getAssociationComponentCandidates,
	selectInitialAssociationParent,
} from "./associationViewModel";

const incompleteInventories: GamePresenceSnapshot["inventories"] = {
	native_steam: { status: "incomplete", reason: "loading" },
	non_steam: { status: "incomplete", reason: "loading" },
};

const ADDITION_VERIFICATION_ERROR =
	"This entry could not be verified as an eligible addition. Refresh status and try again.";

export type AssociationSelectionState = {
	selectedMemberIds: string[];
	selectedParentId: string | null;
	parentSelectionKind: "confirmed" | "advisory" | "manual";
	pendingCandidateIds: string[];
	additionMessages: Record<string, string>;
	error: string | null;
	componentCandidates: GamePresenceCandidate[];
	additionCandidates: GamePresenceCandidate[];
	selectedCandidates: GamePresenceCandidate[];
	ranking: AssociationRankingResult;
	allMembersSelected: boolean;
	hasEnoughMembers: boolean;
	canConfirm: boolean;
};

type CheckAddition = () => Promise<AssociationComponentReadResult>;

type AssociationSelectionControllerOptions = {
	snapshot: AssociationComponentSnapshot;
	presence: GamePresenceSnapshot | null;
	onChange?: (state: AssociationSelectionState) => void;
	onRefreshRequested?: () => void;
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

/**
 * Owns the user-driven group selection state. Each candidate verification has its
 * own generation so an older response can never re-add or reselect a game after a
 * newer user action. The hook is deliberately only an RPC/React adapter for this
 * controller, keeping these interaction decisions independently testable.
 */
export function createAssociationSelectionController({
	snapshot,
	presence: initialPresence,
	onChange,
	onRefreshRequested,
}: AssociationSelectionControllerOptions) {
	let presence = initialPresence;
	let selectedMemberIds = snapshot.existingMembers.map((member) => member.gameId);
	let selectedParentId: string | null = null;
	let parentSelectionKind: AssociationSelectionState["parentSelectionKind"] =
		snapshot.expectedParentGameId ? "confirmed" : "advisory";
	let additionMessages: Record<string, string> = {};
	let error: string | null = null;
	let disposed = false;
	let nextCandidateOperation = 0;
	let nextParentOperation = 0;
	let currentParentOperation = 0;
	let pendingParentCandidate: { id: string; operation: number } | null = null;
	const currentCandidateOperations = new Map<string, number>();
	const pendingCandidateOperations = new Map<string, number>();

	function componentCandidates() {
		return getAssociationComponentCandidates(
			snapshot,
			presence?.candidates ?? [],
		);
	}

	function additionCandidates() {
		const componentMemberIds = new Set(
			snapshot.existingMembers.map((member) => member.gameId),
		);
		return (presence?.candidates ?? []).filter(
			(candidate) => !componentMemberIds.has(candidate.id),
		);
	}

	function selectedCandidates() {
		const selectedIds = new Set(selectedMemberIds);
		return [
			...componentCandidates(),
			...additionCandidates().filter((candidate) => selectedIds.has(candidate.id)),
		];
	}

	function ranking() {
		return rankAssociationParent({
			candidates: selectedCandidates(),
			inventories: presence?.inventories ?? incompleteInventories,
			confirmedParentId: snapshot.expectedParentGameId,
			conflict: snapshot.status === "conflict",
		});
	}

	function selectionContains(gameId: string | null) {
		return gameId !== null && selectedMemberIds.includes(gameId);
	}

	function reconcileAdvisoryParent() {
		if (
			parentSelectionKind === "confirmed" &&
			selectionContains(snapshot.expectedParentGameId)
		) {
			selectedParentId = snapshot.expectedParentGameId;
			return;
		}
		if (parentSelectionKind === "manual" && selectionContains(selectedParentId))
			return;
		const nextRanking = ranking();
		selectedParentId = selectInitialAssociationParent({
			candidates: nextRanking.candidates,
			inventories: presence?.inventories ?? incompleteInventories,
			confirmedParentId: snapshot.expectedParentGameId,
			conflict: snapshot.status === "conflict",
		});
		parentSelectionKind = snapshot.expectedParentGameId
			? "confirmed"
			: "advisory";
	}

	function getState(): AssociationSelectionState {
		const nextComponentCandidates = componentCandidates();
		const nextAdditionCandidates = additionCandidates();
		const nextSelectedCandidates = selectedCandidates();
		const nextRanking = ranking();
		const allMembersSelected = snapshot.existingMembers.every((member) =>
			selectedMemberIds.includes(member.gameId),
		);
		const hasEnoughMembers = selectedMemberIds.length >= 2;
		const allSelectedCandidatesAvailable =
			nextSelectedCandidates.length === selectedMemberIds.length;
		return {
			selectedMemberIds: [...selectedMemberIds],
			selectedParentId,
			parentSelectionKind,
			pendingCandidateIds: [...pendingCandidateOperations.keys()],
			additionMessages: { ...additionMessages },
			error,
			componentCandidates: nextComponentCandidates,
			additionCandidates: nextAdditionCandidates,
			selectedCandidates: nextSelectedCandidates,
			ranking: nextRanking,
			allMembersSelected,
			hasEnoughMembers,
			canConfirm:
				!!selectedParentId &&
				selectionContains(selectedParentId) &&
				allMembersSelected &&
				hasEnoughMembers &&
				allSelectedCandidatesAvailable &&
				pendingCandidateOperations.size === 0,
		};
	}

	function publish() {
		if (!disposed) onChange?.(getState());
	}

	function beginCandidateOperation(gameId: string) {
		const operation = ++nextCandidateOperation;
		currentCandidateOperations.set(gameId, operation);
		pendingCandidateOperations.set(gameId, operation);
		error = null;
		publish();
		return operation;
	}

	function isCurrentCandidateOperation(gameId: string, operation: number) {
		return !disposed && currentCandidateOperations.get(gameId) === operation;
	}

	function finishCandidateOperation(gameId: string, operation: number) {
		if (pendingCandidateOperations.get(gameId) === operation) {
			pendingCandidateOperations.delete(gameId);
			publish();
		}
	}

	function invalidateCandidateOperation(gameId: string) {
		currentCandidateOperations.set(gameId, ++nextCandidateOperation);
		if (pendingCandidateOperations.delete(gameId)) publish();
	}

	function beginParentSelection() {
		currentParentOperation = ++nextParentOperation;
		if (pendingParentCandidate) {
			invalidateCandidateOperation(pendingParentCandidate.id);
			pendingParentCandidate = null;
		}
		return currentParentOperation;
	}

	function setAdditionMessage(gameId: string, message: string | null) {
		if (message) additionMessages = { ...additionMessages, [gameId]: message };
		else {
			const nextMessages = { ...additionMessages };
			delete nextMessages[gameId];
			additionMessages = nextMessages;
		}
	}

	function includeMember(gameId: string) {
		if (!selectedMemberIds.includes(gameId)) {
			selectedMemberIds = [...selectedMemberIds, gameId];
			reconcileAdvisoryParent();
		}
	}

	function removeMember(gameId: string) {
		selectedMemberIds = selectedMemberIds.filter(
			(selectedGameId) => selectedGameId !== gameId,
		);
		if (selectedParentId === gameId) {
			selectedParentId = null;
			parentSelectionKind = "advisory";
		}
		reconcileAdvisoryParent();
	}

	function candidateIsPresent(gameId: string) {
		return (presence?.candidates ?? []).some(
			(candidate) => candidate.id === gameId,
		);
	}

	function getEligibilityDecision(
		gameId: string,
		result: AssociationComponentReadResult,
	) {
		if (!candidateIsPresent(gameId)) {
			return {
				action: "reject" as const,
				message:
					"This entry is no longer in the current status refresh. Refresh status before choosing it.",
			};
		}
		if (!result.success) {
			if (result.error.code === "ANCHOR_NOT_FOUND") return { action: "add" as const };
			return { action: "reject" as const, message: ADDITION_VERIFICATION_ERROR };
		}
		return getAssociationAdditionDecision({
			loadedSnapshot: snapshot,
			candidateSnapshot: result.data,
		});
	}

	async function ensureAddition(
		gameId: string,
		checkAddition: CheckAddition,
		isOperationCurrent: () => boolean = () => true,
	) {
		if (selectedMemberIds.includes(gameId)) return true;
		if (!candidateIsPresent(gameId)) {
			const message =
				"This entry is no longer in the current status refresh. Refresh status before choosing it.";
			setAdditionMessage(gameId, message);
			error = message;
			publish();
			return false;
		}
		const operation = beginCandidateOperation(gameId);
		let result: AssociationComponentReadResult;
		try {
			result = await checkAddition();
		} catch {
			result = {
				success: false,
				error: { code: "NETWORK_ERROR", message: ADDITION_VERIFICATION_ERROR },
			};
		}
		if (
			!isCurrentCandidateOperation(gameId, operation) ||
			!isOperationCurrent()
		)
			return false;
		const decision = getEligibilityDecision(gameId, result);
		finishCandidateOperation(gameId, operation);
		if (decision.action === "add") {
			setAdditionMessage(gameId, null);
			includeMember(gameId);
			publish();
			return true;
		}
		setAdditionMessage(gameId, decision.message);
		error = decision.message;
		publish();
		if (decision.action === "refresh") onRefreshRequested?.();
		return false;
	}

	function selectParentImmediately(gameId: string) {
		selectedParentId = gameId;
		parentSelectionKind = "manual";
		error = null;
		publish();
	}

	function stateForInitialSelection() {
		reconcileAdvisoryParent();
		return getState();
	}

	function updatePresence(nextPresence: GamePresenceSnapshot | null) {
		if (disposed) return;
		presence = nextPresence;
		reconcileAdvisoryParent();
		publish();
	}

	async function toggleMember(gameId: string, checkAddition: CheckAddition) {
		if (disposed || snapshot.existingMembers.some((member) => member.gameId === gameId))
			return false;
		if (pendingCandidateOperations.has(gameId)) {
			invalidateCandidateOperation(gameId);
			if (pendingParentCandidate?.id === gameId)
				pendingParentCandidate = null;
			return false;
		}
		if (selectedMemberIds.includes(gameId)) {
			invalidateCandidateOperation(gameId);
			removeMember(gameId);
			publish();
			return false;
		}
		return await ensureAddition(gameId, checkAddition);
	}

	async function selectParent(gameId: string, checkAddition: CheckAddition) {
		if (disposed) return false;
		const parentOperation = beginParentSelection();
		if (selectedMemberIds.includes(gameId)) {
			selectParentImmediately(gameId);
			return true;
		}
		const expectedCandidateOperation = nextCandidateOperation + 1;
		pendingParentCandidate = { id: gameId, operation: expectedCandidateOperation };
		const added = await ensureAddition(
			gameId,
			checkAddition,
			() =>
				!disposed &&
				currentParentOperation === parentOperation &&
				pendingParentCandidate?.id === gameId &&
				pendingParentCandidate.operation === expectedCandidateOperation,
		);
		if (
			!added ||
			disposed ||
			currentParentOperation !== parentOperation ||
			pendingParentCandidate?.id !== gameId ||
			pendingParentCandidate.operation !== expectedCandidateOperation
		)
			return false;
		pendingParentCandidate = null;
		selectParentImmediately(gameId);
		return true;
	}

	function dispose() {
		disposed = true;
		currentParentOperation = ++nextParentOperation;
		pendingParentCandidate = null;
		pendingCandidateOperations.clear();
		currentCandidateOperations.clear();
	}

	stateForInitialSelection();
	return {
		getState,
		updatePresence,
		toggleMember,
		selectParent,
		dispose,
	};
}

/** Derives a component's initial explicit selection from the exact presence snapshot supplied. */
export function getInitialAssociationComponentSelection(
	snapshot: AssociationComponentSnapshot,
	presence: GamePresenceSnapshot | null,
) {
	const state = createAssociationSelectionController({ snapshot, presence }).getState();
	return {
		selectedMemberIds: state.selectedMemberIds,
		selectedParentId: state.selectedParentId,
		ranking: state.ranking,
	};
}
