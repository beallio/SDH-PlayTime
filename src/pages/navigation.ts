import { Navigation } from "@decky/ui";
import { atom } from "nanostores";

export const DETAILED_REPORT_ROUTE = "/playtime/detailed-report";
export const GAME_REPORT_ROUTE = "/playtime/game-report-route/:gameId";
export const MANUALLY_ADJUST_TIME = "/playtime/manually-adjust-time";
export const SETTINGS_ROUTE = "/playtime/settings";
export const REPLAY_ROUTE = "/playtime/replay/:year";
export const TRACKING_LIST_ROUTE = "/playtime/tracking/list";
export const TRACKING_EDIT_ROUTE = "/playtime/tracking/edit/:gameId";
export const TRACKING_ADD_ROUTE = "/playtime/tracking/add";
export const ASSOCIATION_LIST_ROUTE = "/playtime/association/list";
export const ASSOCIATION_ADD_ROUTE = "/playtime/association/add";
/** The selector route is shared by the list and context-menu flows. */
export const $associationSelectionAnchor = atom<string | null>(null);

export function navigateToReplay(year?: number) {
	const replayYear = year || new Date().getFullYear();

	navigateToPage(REPLAY_ROUTE.replace(":year", replayYear.toString()));
}

export function navigateToPage(url: string) {
	Navigation.CloseSideMenus();
	Navigation.Navigate(url);
}

export function navigateToAssociationSelection(anchorGameId?: string) {
	$associationSelectionAnchor.set(anchorGameId ?? null);
	navigateToPage(ASSOCIATION_ADD_ROUTE);
}

export function navigateToExternalWeb(url: string) {
	Navigation.CloseSideMenus();
	Navigation.NavigateToExternalWeb(url);
}

export function navigateBack() {
	Navigation.CloseSideMenus();
	Navigation.NavigateBack();
}
