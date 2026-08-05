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
	getAssociationComponentCandidates,
	selectInitialAssociationParent,
	shouldRefreshAssociationComponent,
} from "../associationViewModel";

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
	const loadedInitialAnchor = useRef<string | null>(null);

	const refreshPresence = useCallback(async () => {
		try {
			const nextPresence = await refreshCurrentGamePresenceSnapshot();
			setPresence(nextPresence);
			return nextPresence;
		} catch (cause) {
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
		async (nextAnchorGameId: string) => {
			setLoading(true);
			setError(null);
			const result =
				await associationService.getAssociationComponent(nextAnchorGameId);
			if (!result.success) {
				setSnapshot(null);
				setError(result.error.message);
				setLoading(false);
				return null;
			}
			setAnchorGameId(nextAnchorGameId);
			setSnapshot(result.data);
			setSelectedMemberIds(
				result.data.existingMembers.map((member) => member.gameId),
			);
			setSelectedParentId(
				selectInitialAssociationParent({
					candidates: getAssociationComponentCandidates(
						result.data,
						presence?.candidates ?? [],
					),
					inventories: presence?.inventories ?? incompleteInventories,
					confirmedParentId: result.data.expectedParentGameId,
					conflict: result.data.status === "conflict",
				}),
			);
			setLoading(false);
			return result.data;
		},
		[associationService, presence],
	);

	useEffect(() => {
		void refreshPresence().finally(() => setLoading(false));
	}, [refreshPresence]);

	useEffect(() => {
		if (
			!initialAnchorGameId ||
			loadedInitialAnchor.current === initialAnchorGameId
		)
			return;
		loadedInitialAnchor.current = initialAnchorGameId;
		void loadComponent(initialAnchorGameId);
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
	const canConfirm =
		!!snapshot && !!selectedParentId && allMembersSelected && !saving;

	const selectAnchor = useCallback(
		(nextAnchorGameId: string) => {
			void loadComponent(nextAnchorGameId);
		},
		[loadComponent],
	);

	const toggleMember = useCallback((gameId: string) => {
		setSelectedMemberIds((current) =>
			current.includes(gameId)
				? current.filter((selectedGameId) => selectedGameId !== gameId)
				: [...current, gameId],
		);
	}, []);

	const refresh = useCallback(async () => {
		setLoading(true);
		await refreshPresence();
		if (anchorGameId) await loadComponent(anchorGameId);
		setLoading(false);
	}, [anchorGameId, loadComponent, refreshPresence]);

	const confirm =
		useCallback(async (): Promise<AssociationComponentConfirmationResult | null> => {
			if (!snapshot || !selectedParentId || !allMembersSelected) return null;
			const summary = buildAssociationConfirmationSummary({
				snapshot,
				candidates: componentCandidates,
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
			componentCandidates,
			ranking,
			refresh,
			selectedMemberIds,
			selectedParentId,
			snapshot,
		]);

	const confirmationSummary = useMemo(() => {
		if (!snapshot || !selectedParentId || !allMembersSelected) return null;
		return buildAssociationConfirmationSummary({
			snapshot,
			candidates: componentCandidates,
			selectedMemberIds,
			proposedParentId: selectedParentId,
			reasons: associationRankingReasonLabels(ranking?.reasons ?? []),
		});
	}, [
		allMembersSelected,
		componentCandidates,
		ranking,
		selectedMemberIds,
		selectedParentId,
		snapshot,
	]);

	return {
		anchorCards,
		componentCards,
		snapshot,
		loading,
		saving,
		error,
		selectedMemberIds,
		selectedParentId,
		allMembersSelected,
		canConfirm,
		rankingReasons: associationRankingReasonLabels(ranking?.reasons ?? []),
		confirmationSummary,
		selectAnchor,
		selectParent: setSelectedParentId,
		toggleMember,
		refresh,
		confirm,
	};
};
