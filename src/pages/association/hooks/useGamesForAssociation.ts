import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { rankAssociationParent } from "@src/app/associationRanking";
import {
	refreshCurrentGamePresenceSnapshot,
	type GamePresenceSnapshot,
} from "@src/app/gamePresence";
import { useLocator } from "@src/locator";
import type {
	AssociationComponentConfirmationResult,
	AssociationComponentSnapshot,
} from "@src/types/association";
import logger from "@src/utils/logger";
import {
	associationRankingReasonLabels,
	buildAssociationCandidateCards,
	buildAssociationConfirmationRequest,
	buildAssociationConfirmationSummary,
	getAssociationAdditionDecision,
	getAssociationComponentCandidates,
	selectInitialAssociationParent,
	shouldRefreshAssociationComponent,
} from "../associationViewModel";
import {
	createAssociationRequestCoordinator,
	getInitialAssociationComponentSelection,
} from "../associationSelectionController";

const incompleteInventories: GamePresenceSnapshot["inventories"] = {
	native_steam: { status: "incomplete", reason: "loading" },
	non_steam: { status: "incomplete", reason: "loading" },
};

/** Loads one explicit identity component; it never presents the full inventory as a group. */
export const useGamesForAssociation = (initialAnchorGameId: string | null) => {
	const { associationService } = useLocator();
	const [presence, setPresence] = useState<GamePresenceSnapshot | null>(null);
	const [snapshot, setSnapshot] = useState<AssociationComponentSnapshot | null>(
		null,
	);
	const [anchorGameId, setAnchorGameId] = useState<string | null>(
		initialAnchorGameId,
	);
	const [selectedParentId, setSelectedParentId] = useState<string | null>(null);
	const [selectedMemberIds, setSelectedMemberIds] = useState<string[]>([]);
	const [loading, setLoading] = useState(true);
	const [saving, setSaving] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [additionMessages, setAdditionMessages] = useState<
		Record<string, string>
	>({});
	const loadedInitialAnchor = useRef<string | null>(null);
	const mounted = useRef(true);
	const presenceRef = useRef<GamePresenceSnapshot | null>(null);
	const snapshotRef = useRef<AssociationComponentSnapshot | null>(null);
	const componentRequests = useRef<ReturnType<
		typeof createAssociationRequestCoordinator
	> | null>(null);
	const presenceRequests = useRef<ReturnType<
		typeof createAssociationRequestCoordinator
	> | null>(null);
	if (!componentRequests.current)
		componentRequests.current = createAssociationRequestCoordinator();
	if (!presenceRequests.current)
		presenceRequests.current = createAssociationRequestCoordinator();

	useEffect(
		() => () => {
			mounted.current = false;
			componentRequests.current?.invalidate();
			presenceRequests.current?.invalidate();
		},
		[],
	);

	const refreshPresence = useCallback(async () => {
		const request = presenceRequests.current?.begin();
		try {
			const nextPresence = await refreshCurrentGamePresenceSnapshot();
			if (
				!mounted.current ||
				request === undefined ||
				!presenceRequests.current?.isCurrent(request)
			)
				return null;
			presenceRef.current = nextPresence;
			setPresence(nextPresence);
			return nextPresence;
		} catch (cause) {
			if (
				!mounted.current ||
				request === undefined ||
				!presenceRequests.current?.isCurrent(request)
			)
				return null;
			const message =
				cause instanceof Error
					? cause.message
					: "Failed to refresh game status.";
			setError(message);
			logger.error("Failed to refresh association game presence:", cause);
			return null;
		}
	}, []);

	const loadComponent = useCallback(
		async (
			nextAnchorGameId: string,
			presenceSnapshot?: GamePresenceSnapshot | null,
			{ preserveError = false }: { preserveError?: boolean } = {},
		) => {
			const request = componentRequests.current?.begin();
			setLoading(true);
			if (!preserveError) setError(null);
			const result =
				await associationService.getAssociationComponent(nextAnchorGameId);
			if (
				!mounted.current ||
				request === undefined ||
				!componentRequests.current?.isCurrent(request)
			)
				return null;
			if (!result.success) {
				snapshotRef.current = null;
				setSnapshot(null);
				setError(result.error.message);
				setLoading(false);
				return null;
			}
			const selection = getInitialAssociationComponentSelection(
				result.data,
				presenceSnapshot ?? presenceRef.current,
			);
			setAnchorGameId(nextAnchorGameId);
			snapshotRef.current = result.data;
			setSnapshot(result.data);
			setSelectedMemberIds(selection.selectedMemberIds);
			setSelectedParentId(selection.selectedParentId);
			setAdditionMessages({});
			setLoading(false);
			return result.data;
		},
		[associationService],
	);

	useEffect(() => {
		void refreshPresence().finally(() => {
			if (mounted.current && !snapshotRef.current) setLoading(false);
		});
	}, [refreshPresence]);

	useEffect(() => {
		if (
			!initialAnchorGameId ||
			loadedInitialAnchor.current === initialAnchorGameId
		)
			return;
		loadedInitialAnchor.current = initialAnchorGameId;
		void loadComponent(initialAnchorGameId, undefined, { preserveError: true });
	}, [initialAnchorGameId, loadComponent]);

	const componentCandidates = useMemo(
		() =>
			snapshot
				? getAssociationComponentCandidates(
						snapshot,
						presence?.candidates ?? [],
					)
				: [],
		[presence, snapshot],
	);
	const ranking = useMemo(
		() =>
			snapshot
				? rankAssociationParent({
						candidates: componentCandidates,
						inventories: presence?.inventories ?? incompleteInventories,
						confirmedParentId: snapshot.expectedParentGameId,
						conflict: snapshot.status === "conflict",
					})
				: null,
		[componentCandidates, presence, snapshot],
	);

	useEffect(() => {
		if (!snapshot || !presence || selectedParentId) return;
		setSelectedParentId(
			selectInitialAssociationParent({
				candidates: componentCandidates,
				inventories: presence.inventories,
				confirmedParentId: snapshot.expectedParentGameId,
				conflict: snapshot.status === "conflict",
			}),
		);
	}, [componentCandidates, presence, selectedParentId, snapshot]);

	const componentCards = useMemo(
		() =>
			buildAssociationCandidateCards({
				candidates: componentCandidates,
				selectedParentId,
				recommendedParentId: ranking?.advisoryRecommendation?.gameId ?? null,
			}),
		[componentCandidates, ranking, selectedParentId],
	);
	const additionCandidates = useMemo(() => {
		if (!snapshot) return [];
		const componentMemberIds = new Set(
			snapshot.existingMembers.map((member) => member.gameId),
		);
		return (presence?.candidates ?? []).filter(
			(candidate) => !componentMemberIds.has(candidate.id),
		);
	}, [presence, snapshot]);
	const additionCards = useMemo(
		() =>
			buildAssociationCandidateCards({
				candidates: additionCandidates,
				selectedParentId,
				recommendedParentId: null,
			}),
		[additionCandidates, selectedParentId],
	);
	const selectedCandidates = useMemo(
		() => [...componentCandidates, ...additionCandidates],
		[additionCandidates, componentCandidates],
	);
	const anchorCards = useMemo(
		() =>
			buildAssociationCandidateCards({
				candidates: presence?.candidates ?? [],
				selectedParentId: null,
				recommendedParentId: null,
			}),
		[presence],
	);
	const allMembersSelected =
		!!snapshot &&
		snapshot.existingMembers.every((member) =>
			selectedMemberIds.includes(member.gameId),
		);
	const hasEnoughMembers = selectedMemberIds.length >= 2;
	const canConfirm =
		!!snapshot &&
		!!selectedParentId &&
		allMembersSelected &&
		hasEnoughMembers &&
		!saving;

	const selectAnchor = useCallback(
		(nextAnchorGameId: string) => {
			void loadComponent(nextAnchorGameId);
		},
		[loadComponent],
	);

	const ensureAddition = useCallback(
		async (gameId: string) => {
			const loadedSnapshot = snapshotRef.current;
			if (!loadedSnapshot) return false;
			if (
				loadedSnapshot.existingMembers.some(
					(member) => member.gameId === gameId,
				) ||
				selectedMemberIds.includes(gameId)
			)
				return true;
			const componentRequest = componentRequests.current?.current();
			const result = await associationService.getAssociationComponent(gameId);
			if (
				!mounted.current ||
				componentRequest === undefined ||
				!componentRequests.current?.isCurrent(componentRequest) ||
				snapshotRef.current !== loadedSnapshot
			)
				return false;
			if (!result.success) {
				const message =
					"This entry could not be verified as an eligible addition. Refresh status and try again.";
				setAdditionMessages((current) => ({ ...current, [gameId]: message }));
				setError(message);
				return false;
			}
			const decision = getAssociationAdditionDecision({
				loadedSnapshot,
				candidateSnapshot: result.data,
			});
			if (decision.action !== "add") {
				setAdditionMessages((current) => ({
					...current,
					[gameId]: decision.message,
				}));
				setError(decision.message);
				if (decision.action === "refresh")
					void loadComponent(loadedSnapshot.anchorGameId, undefined, {
						preserveError: true,
					});
				return false;
			}
			setAdditionMessages((current) => {
				const remaining = { ...current };
				delete remaining[gameId];
				return remaining;
			});
			setSelectedMemberIds((current) =>
				current.includes(gameId) ? current : [...current, gameId],
			);
			return true;
		},
		[associationService, loadComponent, selectedMemberIds],
	);

	const toggleMember = useCallback(
		async (gameId: string) => {
			if (!snapshot) return;
			if (snapshot.existingMembers.some((member) => member.gameId === gameId))
				return;
			if (selectedMemberIds.includes(gameId)) {
				setSelectedMemberIds((current) =>
					current.filter((selectedGameId) => selectedGameId !== gameId),
				);
				setSelectedParentId((current) => (current === gameId ? null : current));
				return;
			}
			await ensureAddition(gameId);
		},
		[ensureAddition, selectedMemberIds, snapshot],
	);

	const selectParent = useCallback(
		async (gameId: string) => {
			if (!snapshot) return;
			const isExistingMember = snapshot.existingMembers.some(
				(member) => member.gameId === gameId,
			);
			if (!isExistingMember && !(await ensureAddition(gameId))) return;
			setSelectedParentId(gameId);
		},
		[ensureAddition, snapshot],
	);

	const refresh = useCallback(async () => {
		setLoading(true);
		setError(null);
		const nextPresence = await refreshPresence();
		if (anchorGameId) {
			await loadComponent(anchorGameId, nextPresence ?? presenceRef.current, {
				preserveError: true,
			});
			return;
		}
		if (mounted.current) setLoading(false);
	}, [anchorGameId, loadComponent, refreshPresence]);

	const confirm =
		useCallback(async (): Promise<AssociationComponentConfirmationResult | null> => {
			if (
				!snapshot ||
				!selectedParentId ||
				!allMembersSelected ||
				!hasEnoughMembers
			)
				return null;
			const summary = buildAssociationConfirmationSummary({
				snapshot,
				candidates: selectedCandidates,
				selectedMemberIds,
				proposedParentId: selectedParentId,
				reasons: associationRankingReasonLabels(ranking?.reasons ?? []),
			});
			setSaving(true);
			setError(null);
			try {
				const result = await associationService.confirmAssociationComponent(
					buildAssociationConfirmationRequest({
						snapshot,
						confirmation: summary,
					}),
				);
				if (!result.success) {
					setError(result.error.message);
					if (shouldRefreshAssociationComponent(result.error.code)) {
						await refresh();
					}
				}
				return result;
			} finally {
				setSaving(false);
			}
		}, [
			allMembersSelected,
			associationService,
			hasEnoughMembers,
			ranking,
			refresh,
			selectedMemberIds,
			selectedCandidates,
			selectedParentId,
			snapshot,
		]);

	const confirmationSummary = useMemo(() => {
		if (
			!snapshot ||
			!selectedParentId ||
			!allMembersSelected ||
			!hasEnoughMembers
		)
			return null;
		return buildAssociationConfirmationSummary({
			snapshot,
			candidates: selectedCandidates,
			selectedMemberIds,
			proposedParentId: selectedParentId,
			reasons: associationRankingReasonLabels(ranking?.reasons ?? []),
		});
	}, [
		allMembersSelected,
		hasEnoughMembers,
		ranking,
		selectedMemberIds,
		selectedCandidates,
		selectedParentId,
		snapshot,
	]);

	return {
		anchorCards,
		componentCards,
		additionCards,
		snapshot,
		loading,
		saving,
		error,
		selectedMemberIds,
		selectedParentId,
		additionMessages,
		allMembersSelected,
		hasEnoughMembers,
		canConfirm,
		rankingReasons: associationRankingReasonLabels(ranking?.reasons ?? []),
		confirmationSummary,
		selectAnchor,
		selectParent,
		toggleMember,
		refresh,
		confirm,
	};
};
