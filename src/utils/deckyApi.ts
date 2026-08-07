import type {
	RouterHook,
	ToastData,
	ToastNotification,
	Toaster,
} from "@decky/api";
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
	const deckyApiAny = deckyApi as Record<string, unknown>;
	const deckyApiDefault = deckyApiAny.default;
	if ("routerHook" in deckyApiAny) {
		return deckyApiAny.routerHook as RouterHook;
	}
	if (
		typeof deckyApiDefault === "object" &&
		deckyApiDefault !== null &&
		typeof (deckyApiDefault as { routerHook?: unknown }).routerHook !==
			"undefined"
	) {
		return (deckyApiDefault as { routerHook?: RouterHook }).routerHook;
	}
	return undefined;
})();

export const routerHook = maybeRouterHook ?? FALLBACK_ROUTER_HOOK;

const FALLBACK_TOASTER: Toaster = {
	toast: (_toast: ToastData): ToastNotification => {
		return {
			data: _toast,
			dismiss: () => {},
		};
	},
};

const maybeToaster = (deckyApi as { toaster?: Toaster }).toaster;

export const toaster = maybeToaster ?? FALLBACK_TOASTER;
