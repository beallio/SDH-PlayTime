import type { RouterHook, Toaster } from "@decky/api";
import * as deckyApi from "@decky/api";
import { error } from "@src/utils/logger";

const FALLBACK_ROUTER_HOOK: RouterHook = {
	addRoute: () => {
		error("PlayTime: routerHook unavailable; route registration skipped.");
	},
	removeRoute: () => {},
	addPatch: (_path, patch) => patch,
	removePatch: () => {},
	addGlobalComponent: () => {
		error("PlayTime: routerHook unavailable; global components skipped.");
	},
	removeGlobalComponent: () => {},
};

const maybeRouterHook = ((): RouterHook | undefined => {
	return (
		(deckyApi as { routerHook?: RouterHook }).routerHook ??
		(deckyApi as { default?: { routerHook?: RouterHook } }).default?.routerHook
	);
})();

export const routerHook = maybeRouterHook ?? FALLBACK_ROUTER_HOOK;

export const toaster = (deckyApi as { toaster: Toaster }).toaster;
