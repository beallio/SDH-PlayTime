import { useCallback, useEffect, useState } from "react";
import {
	refreshCurrentGamePresenceSnapshot,
	type GamePresenceCandidate,
} from "@src/app/gamePresence";
import { useLocator } from "@src/locator";
import logger from "@src/utils/logger";
import {
	buildAssociationListGroups,
	type AssociationListGroup,
} from "../associationViewModel";

/** Refreshes status alongside explicit rows while retaining one card per parent component. */
export const useAssociations = () => {
	const { associationService } = useLocator();
	const [groups, setGroups] = useState<AssociationListGroup[]>([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<Error | null>(null);

	const loadAssociations = useCallback(async () => {
		setLoading(true);
		setError(null);
		try {
			const associations = await associationService.getAllAssociations();
			let candidates: GamePresenceCandidate[] = [];
			try {
				candidates = (await refreshCurrentGamePresenceSnapshot()).candidates;
			} catch (cause) {
				logger.error("Failed to refresh association list presence:", cause);
			}
			setGroups(buildAssociationListGroups(associations, candidates));
		} catch (cause) {
			setError(
				cause instanceof Error
					? cause
					: new Error("Failed to load game associations"),
			);
			logger.error("Failed to load associations:", cause);
		} finally {
			setLoading(false);
		}
	}, [associationService]);

	useEffect(() => {
		void loadAssociations();
	}, [loadAssociations]);

	const detachMember = useCallback(
		async (childGameId: string) => {
			const result =
				await associationService.detachAssociationMember(childGameId);
			if (result.success) await loadAssociations();
			return result;
		},
		[associationService, loadAssociations],
	);

	const dissolveGroup = useCallback(
		async (anchorGameId: string) => {
			const result =
				await associationService.dissolveAssociationComponent(anchorGameId);
			if (result.success) await loadAssociations();
			return result;
		},
		[associationService, loadAssociations],
	);

	return {
		groups,
		loading,
		error,
		refresh: loadAssociations,
		detachMember,
		dissolveGroup,
	};
};
