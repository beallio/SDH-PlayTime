import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
	shouldRefreshAssociationComponent,
} from "../associationViewModel";
import {
	createAssociationSelectionController,
	createAssociationRequestCoordinator,
} from "../associationSelectionController";

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
	const [selectionState, setSelectionState] = useState<ReturnType<
		ReturnType<typeof createAssociationSelectionController>["getState"]
	> | null>(null);
	const [loading, setLoading] = useState(true);
	const [saving, setSaving] = useState(false);
	const [error, setError] = useState<string | null>(null);
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
	const selectionController = useRef<ReturnType<
		typeof createAssociationSelectionController
	> | null>(null);
	if (!componentRequests.current)
		componentRequests.current = createAssociationRequestCoordinator();
	if (!presenceRequests.current)
		presenceRequests.current = createAssociationRequestCoordinator();

	useEffect(() => {
		mounted.current = true;
		return () => {
			mounted.current = false;
			componentRequests.current?.invalidate();
			presenceRequests.current?.invalidate();
			selectionController.current?.dispose();
			selectionController.current = null;
		};
	}, []);

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
			selectionController.current?.updatePresence(nextPresence);
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
			selectionController.current?.dispose();
			const nextSelectionController = createAssociationSelectionController({
				snapshot: result.data,
				presence: presenceSnapshot ?? presenceRef.current,
				onChange: setSelectionState,
				onRefreshRequested: () => {
					void loadComponent(result.data.anchorGameId, undefined, {
						preserveError: true,
					});
				},
			});
			selectionController.current = nextSelectionController;
			setAnchorGameId(nextAnchorGameId);
			snapshotRef.current = result.data;
			setSnapshot(result.data);
			setSelectionState(nextSelectionController.getState());
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

	const componentCandidates = selectionState?.componentCandidates ?? [];
	const additionCandidates = selectionState?.additionCandidates ?? [];
	const selectedCandidates = selectionState?.selectedCandidates ?? [];
	const selectedMemberIds = selectionState?.selectedMemberIds ?? [];
	const selectedParentId = selectionState?.selectedParentId ?? null;
	const ranking = selectionState?.ranking ?? null;
	const additionMessages = selectionState?.additionMessages ?? {};

	const componentCards = useMemo(
		() =>
			buildAssociationCandidateCards({
				candidates: componentCandidates,
				selectedParentId,
				recommendedParentId: ranking?.advisoryRecommendation?.gameId ?? null,
			}),
		[componentCandidates, ranking, selectedParentId],
	);
	const additionCards = useMemo(
		() =>
			buildAssociationCandidateCards({
				candidates: additionCandidates,
				selectedParentId,
				recommendedParentId: ranking?.advisoryRecommendation?.gameId ?? null,
			}),
		[additionCandidates, ranking, selectedParentId],
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
	const allMembersSelected = selectionState?.allMembersSelected ?? false;
	const hasEnoughMembers = selectionState?.hasEnoughMembers ?? false;
	const canConfirm = (selectionState?.canConfirm ?? false) && !saving;

	const selectAnchor = useCallback(
		(nextAnchorGameId: string) => {
			void loadComponent(nextAnchorGameId);
		},
		[loadComponent],
	);

	const toggleMember = useCallback(
		async (gameId: string) => {
			await selectionController.current?.toggleMember(gameId, () =>
				associationService.getAssociationComponent(gameId),
			);
		},
		[associationService],
	);

	const selectParent = useCallback(
		async (gameId: string) => {
			await selectionController.current?.selectParent(gameId, () =>
				associationService.getAssociationComponent(gameId),
			);
		},
		[associationService],
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
			if (!snapshot || !selectedParentId || !canConfirm) return null;
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
			associationService,
			canConfirm,
			ranking,
			refresh,
			selectedMemberIds,
			selectedCandidates,
			selectedParentId,
			snapshot,
		]);

	const confirmationSummary = useMemo(() => {
		if (!snapshot || !selectedParentId || !canConfirm) return null;
		return buildAssociationConfirmationSummary({
			snapshot,
			candidates: selectedCandidates,
			selectedMemberIds,
			proposedParentId: selectedParentId,
			reasons: associationRankingReasonLabels(ranking?.reasons ?? []),
		});
	}, [
		canConfirm,
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
		error: error ?? selectionState?.error ?? null,
		selectedMemberIds,
		selectedParentId,
		additionMessages,
		pendingCandidateIds: selectionState?.pendingCandidateIds ?? [],
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
