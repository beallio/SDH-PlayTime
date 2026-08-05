import { APP_TYPE } from "@src/constants";
import type { AssociationCandidate } from "@src/types/association";
import { Backend } from "./backend";
import { classifyShortcutEvidence } from "@src/steam/utils/GamePaths";
import { getAppDetailsResult } from "@src/steam/utils/getAppDetails";

export type GamePresenceSource = "native_steam" | "non_steam";
export type GameInventoryStatus = "current" | "historical" | "unknown";
export type GameAvailabilityStatus =
	| "running"
	| "reachable"
	| "unreachable"
	| "unknown";
export type InventoryCompletenessStatus = "complete" | "incomplete";

export type GamePresenceReasonCode =
	| "omitted_from_complete_inventory"
	| "inventory_source_unknown"
	| "inventory_source_conflict"
	| "inventory_incomplete"
	| "native_install_probe_unavailable"
	| "native_install_probe_failed"
	| "native_install_state_unknown"
	| "native_not_installed"
	| "invalid_app_id"
	| "app_details_unsupported_runtime"
	| "app_details_registration_error"
	| "app_details_callback_error"
	| "app_details_missing_details"
	| "app_details_timeout"
	| "resolver_failed"
	| "resolver_incomplete"
	| "resolver_unknown"
	| "resolver_unreachable"
	| GameResolutionReasonCode;

export type GamePresenceReason = {
	code: GamePresenceReasonCode;
	source: GamePresenceSource | "resolver";
};

export type GameInventoryPresence = {
	status: GameInventoryStatus;
	reasons: GamePresenceReason[];
};

export type GameAvailabilityPresence = {
	status: GameAvailabilityStatus;
	reasons: GamePresenceReason[];
	label?: "Installed" | "Available on this Deck";
};

export type GamePresenceCandidate = {
	id: string;
	name: string;
	source: GamePresenceSource | "unknown";
	tracked: boolean;
	recentPlaytime: number;
	totalPlaytime: number;
	inventory: GameInventoryPresence;
	availability: GameAvailabilityPresence;
};

export type GamePresenceInventory = {
	status: "complete" | "loading" | "failed" | "missing";
	apps: ReadonlyArray<{ id: string; name: string }>;
};

export type GamePresenceInventoryCompleteness =
	| { status: "complete" }
	| { status: "incomplete"; reason: "loading" | "failed" | "missing" };

export type GamePresenceSnapshot = {
	inventories: Record<GamePresenceSource, GamePresenceInventoryCompleteness>;
	candidates: GamePresenceCandidate[];
};

export type GamePresenceRawCandidate = AssociationCandidate & {
	source?: GamePresenceSource;
	recentPlaytime?: number;
	totalPlaytime?: number;
};

export type NativeInstallEvidence =
	| { status: "installed" }
	| { status: "not_installed" }
	| { status: "unknown" };

export type NativeInstallProbe = (
	appId: number,
) => NativeInstallEvidence | Promise<NativeInstallEvidence>;

export type GamePresenceBuildInput = {
	candidates: ReadonlyArray<GamePresenceRawCandidate>;
	nativeInventory: GamePresenceInventory;
	nonSteamInventory: GamePresenceInventory;
	runningAppIds: ReadonlyArray<number | string>;
	getAppDetails: (appId: number) => Promise<AppDetailsResult>;
	nativeInstallProbe?: NativeInstallProbe;
	resolvePayloads: (
		requests: GameResolutionRequest[],
	) => Promise<GameResolutionBatchResponse>;
	detailConcurrency?: number;
};

export type GamePresenceRefreshInput = Omit<
	GamePresenceBuildInput,
	"candidates"
> & {
	getCandidates: () => Promise<ReadonlyArray<GamePresenceRawCandidate>>;
};

type CandidateSeed = {
	id: string;
	name: string;
	tracked: boolean;
	source?: GamePresenceSource;
	recentPlaytime: number;
	totalPlaytime: number;
};

type ReliableNativeInstallApi = {
	Apps?: {
		BIsAppInstalled?: (appId: number) => boolean;
	};
};

const sourceOrder: readonly GamePresenceSource[] = [
	"native_steam",
	"non_steam",
];
const DEFAULT_DETAIL_CONCURRENCY = 4;
const MAX_DETAIL_CONCURRENCY = 8;

function inventoryCompleteness(
	inventory: GamePresenceInventory,
): GamePresenceInventoryCompleteness {
	return inventory.status === "complete"
		? { status: "complete" }
		: { status: "incomplete", reason: inventory.status };
}

function toFiniteNumber(value: number | undefined) {
	return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function toAppId(id: string) {
	const appId = Number(id);
	return Number.isSafeInteger(appId) && appId >= 0 ? appId : undefined;
}

function reason(
	code: GamePresenceReasonCode,
	source: GamePresenceReason["source"],
): GamePresenceReason {
	return { code, source };
}

function buildSeeds(input: GamePresenceBuildInput) {
	const seeds = new Map<string, CandidateSeed>();
	for (const candidate of input.candidates) {
		seeds.set(candidate.game.id, {
			id: candidate.game.id,
			name: candidate.game.name,
			tracked: true,
			source: candidate.source,
			recentPlaytime: toFiniteNumber(candidate.recentPlaytime),
			totalPlaytime: toFiniteNumber(
				candidate.totalPlaytime ?? candidate.duration,
			),
		});
	}

	for (const source of sourceOrder) {
		const inventory =
			source === "native_steam"
				? input.nativeInventory
				: input.nonSteamInventory;
		for (const app of inventory.apps) {
			const existing = seeds.get(app.id);
			if (existing) {
				if (!existing.source) {
					existing.source = source;
				}
				if (!existing.name || existing.name === "[Unknown name]") {
					existing.name = app.name;
				}
				continue;
			}

			seeds.set(app.id, {
				id: app.id,
				name: app.name,
				tracked: false,
				source,
				recentPlaytime: 0,
				totalPlaytime: 0,
			});
		}
	}
	return seeds;
}

function sourceMembership(input: GamePresenceBuildInput) {
	const memberships = new Map<string, Set<GamePresenceSource>>();
	for (const source of sourceOrder) {
		const inventory = inventoryFor(input, source);
		for (const app of inventory.apps) {
			let sources = memberships.get(app.id);
			if (!sources) {
				sources = new Set();
				memberships.set(app.id, sources);
			}
			sources.add(source);
		}
	}
	return memberships;
}

function inventoryFor(
	input: GamePresenceBuildInput,
	source: GamePresenceSource,
) {
	return source === "native_steam"
		? input.nativeInventory
		: input.nonSteamInventory;
}

function deriveInventory(
	seed: CandidateSeed,
	memberships: Map<string, Set<GamePresenceSource>>,
	input: GamePresenceBuildInput,
): {
	source: GamePresenceSource | "unknown";
	inventory: GameInventoryPresence;
} {
	const presentSources = sourceOrder.filter((source) =>
		memberships.get(seed.id)?.has(source),
	);
	if (presentSources.length > 1) {
		return {
			source: "unknown",
			inventory: {
				status: "unknown",
				reasons: [reason("inventory_source_conflict", "resolver")],
			},
		};
	}

	const presentSource = presentSources[0];
	if (presentSource) {
		if (seed.source && seed.source !== presentSource) {
			return {
				source: "unknown",
				inventory: {
					status: "unknown",
					reasons: [reason("inventory_source_conflict", "resolver")],
				},
			};
		}
		if (inventoryFor(input, presentSource).status !== "complete") {
			return {
				source: presentSource,
				inventory: {
					status: "unknown",
					reasons: [reason("inventory_incomplete", presentSource)],
				},
			};
		}
		return {
			source: presentSource,
			inventory: { status: "current", reasons: [] },
		};
	}

	if (!seed.source) {
		return {
			source: "unknown",
			inventory: {
				status: "unknown",
				reasons: [reason("inventory_source_unknown", "resolver")],
			},
		};
	}

	const inventory = inventoryFor(input, seed.source);
	if (inventory.status !== "complete") {
		return {
			source: seed.source,
			inventory: {
				status: "unknown",
				reasons: [reason("inventory_incomplete", seed.source)],
			},
		};
	}
	return {
		source: seed.source,
		inventory: {
			status: "historical",
			reasons: [reason("omitted_from_complete_inventory", seed.source)],
		},
	};
}

async function mapWithConcurrency<T, R>(
	values: ReadonlyArray<T>,
	limit: number,
	callback: (value: T) => Promise<R>,
): Promise<R[]> {
	const results = new Array<R>(values.length);
	let nextIndex = 0;
	const worker = async () => {
		while (nextIndex < values.length) {
			const index = nextIndex++;
			results[index] = await callback(values[index] as T);
		}
	};
	await Promise.all(
		Array.from({ length: Math.min(limit, values.length) }, () => worker()),
	);
	return results;
}

function detailsReason(
	reasonCode: AppDetailsFailureReason,
): GamePresenceReasonCode {
	return `app_details_${reasonCode.replace(/-/g, "_")}` as GamePresenceReasonCode;
}

function normalizeConcurrency(value: number | undefined) {
	if (!Number.isInteger(value) || value === undefined) {
		return DEFAULT_DETAIL_CONCURRENCY;
	}
	return Math.max(1, Math.min(MAX_DETAIL_CONCURRENCY, value));
}

/**
 * Builds a point-in-time, read-only presence snapshot. Resolver paths and shortcut
 * commands remain inside the resolver boundary and are intentionally absent here.
 */
export async function buildGamePresenceSnapshot(
	input: GamePresenceBuildInput,
): Promise<GamePresenceSnapshot> {
	const inventories = {
		native_steam: inventoryCompleteness(input.nativeInventory),
		non_steam: inventoryCompleteness(input.nonSteamInventory),
	};
	const memberships = sourceMembership(input);
	const runningIds = new Set(input.runningAppIds.map(String));
	const candidates: GamePresenceCandidate[] = [
		...buildSeeds(input).values(),
	].map((seed) => {
		const { source, inventory } = deriveInventory(seed, memberships, input);
		const running = source !== "unknown" && runningIds.has(seed.id);
		return {
			...seed,
			source,
			inventory,
			availability: running
				? { status: "running" as const, reasons: [] }
				: { status: "unknown" as const, reasons: [] },
		};
	});

	for (const candidate of candidates) {
		if (
			candidate.inventory.status !== "current" ||
			candidate.availability.status === "running" ||
			candidate.source !== "native_steam"
		) {
			continue;
		}
		const appId = toAppId(candidate.id);
		if (appId === undefined) {
			candidate.availability = {
				status: "unknown",
				reasons: [reason("invalid_app_id", "native_steam")],
			};
			continue;
		}
		if (!input.nativeInstallProbe) {
			candidate.availability = {
				status: "unknown",
				reasons: [reason("native_install_probe_unavailable", "native_steam")],
			};
			continue;
		}
		try {
			const evidence = await input.nativeInstallProbe(appId);
			candidate.availability =
				evidence.status === "installed"
					? { status: "reachable", reasons: [] }
					: evidence.status === "not_installed"
						? {
								status: "unreachable",
								reasons: [reason("native_not_installed", "native_steam")],
							}
						: {
								status: "unknown",
								reasons: [
									reason("native_install_state_unknown", "native_steam"),
								],
							};
		} catch {
			candidate.availability = {
				status: "unknown",
				reasons: [reason("native_install_probe_failed", "native_steam")],
			};
		}
	}

	const toResolve = candidates.filter(
		(candidate) =>
			candidate.inventory.status === "current" &&
			candidate.availability.status !== "running" &&
			candidate.source === "non_steam",
	);
	const detailCache = new Map<number, Promise<AppDetailsResult>>();
	const getCachedDetails = (appId: number) => {
		let details = detailCache.get(appId);
		if (!details) {
			details = input.getAppDetails(appId);
			detailCache.set(appId, details);
		}
		return details;
	};
	const resolutionCandidates: Array<{
		candidate: (typeof candidates)[number];
		request: GameResolutionRequest;
	}> = [];

	await mapWithConcurrency(
		toResolve,
		normalizeConcurrency(input.detailConcurrency),
		async (candidate) => {
			const appId = toAppId(candidate.id);
			if (appId === undefined) {
				candidate.availability = {
					status: "unknown",
					reasons: [reason("invalid_app_id", "non_steam")],
				};
				return;
			}
			let details: AppDetailsResult;
			try {
				details = await getCachedDetails(appId);
			} catch {
				candidate.availability = {
					status: "unknown",
					reasons: [reason("app_details_registration_error", "non_steam")],
				};
				return;
			}
			if (details.status === "failure") {
				candidate.availability = {
					status: "unknown",
					reasons: [reason(detailsReason(details.reason), "non_steam")],
				};
				return;
			}
			const evidence = classifyShortcutEvidence(details.details);
			resolutionCandidates.push({
				candidate,
				request: {
					launcherKind: evidence.launcherKind,
					classificationStatus: evidence.status,
					normalized: evidence.normalized,
					metadataCandidates: [],
				},
			});
		},
	);

	if (resolutionCandidates.length > 0) {
		try {
			const response = await input.resolvePayloads(
				resolutionCandidates.map(({ request }) => request),
			);
			for (const [index, { candidate }] of resolutionCandidates.entries()) {
				const result = response.error ? undefined : response.results[index];
				if (!result) {
					candidate.availability = {
						status: "unknown",
						reasons: [
							reason(
								response.error ? "resolver_failed" : "resolver_incomplete",
								"resolver",
							),
						],
					};
					continue;
				}
				candidate.availability =
					result.payloadStatus === "reachable"
						? { status: "reachable", reasons: [] }
						: result.payloadStatus === "unreachable"
							? {
									status: "unreachable",
									reasons: [
										reason(
											result.reasonCode ?? "resolver_unreachable",
											"resolver",
										),
									],
								}
							: {
									status: "unknown",
									reasons: [
										reason(result.reasonCode ?? "resolver_unknown", "resolver"),
									],
								};
			}
		} catch {
			for (const { candidate } of resolutionCandidates) {
				candidate.availability = {
					status: "unknown",
					reasons: [reason("resolver_failed", "resolver")],
				};
			}
		}
	}

	for (const candidate of candidates) {
		if (candidate.availability.status !== "reachable") {
			continue;
		}
		candidate.availability.label =
			candidate.source === "native_steam"
				? "Installed"
				: candidate.source === "non_steam"
					? "Available on this Deck"
					: undefined;
	}

	return { inventories, candidates };
}

function runtimeNativeInventory(): GamePresenceInventory {
	if (typeof appStore === "undefined" || !Array.isArray(appStore.allApps)) {
		return { status: "missing", apps: [] };
	}
	return {
		status: "complete",
		apps: appStore.allApps
			.filter((app) => app.app_type !== APP_TYPE.THIRD_PARTY)
			.map((app) => ({ id: String(app.appid), name: app.display_name })),
	};
}

function runtimeNonSteamInventory(): GamePresenceInventory {
	if (
		typeof collectionStore !== "undefined" &&
		collectionStore.deckDesktopApps
	) {
		return {
			status: "complete",
			apps: Array.from(collectionStore.deckDesktopApps.apps.values()).map(
				(app) => ({
					id: String(app.appid),
					name: app.display_name,
				}),
			),
		};
	}
	if (typeof appStore === "undefined" || !Array.isArray(appStore.allApps)) {
		return { status: "missing", apps: [] };
	}
	return {
		status: "complete",
		apps: appStore.allApps
			.filter((app) => app.app_type === APP_TYPE.THIRD_PARTY)
			.map((app) => ({ id: String(app.appid), name: app.display_name })),
	};
}

function runtimeRunningAppIds() {
	if (
		typeof SteamUIStore === "undefined" ||
		!Array.isArray(SteamUIStore.RunningApps)
	) {
		return [];
	}
	return SteamUIStore.RunningApps.map((app) => app.appid);
}

function runtimeNativeInstallProbe(): NativeInstallProbe | undefined {
	const runtime = globalThis as unknown as {
		SteamClient?: ReliableNativeInstallApi;
	};
	const probe = runtime.SteamClient?.Apps?.BIsAppInstalled;
	if (typeof probe !== "function") {
		return;
	}
	return (appId) => ({ status: probe(appId) ? "installed" : "not_installed" });
}

/** Refreshes caller-provided read sources without writing presence or associations. */
export async function refreshGamePresenceSnapshot(
	input: GamePresenceRefreshInput,
): Promise<GamePresenceSnapshot> {
	return await buildGamePresenceSnapshot({
		...input,
		candidates: await input.getCandidates(),
	});
}

/** Refreshes the current Steam runtime view without writing presence or associations. */
export async function refreshCurrentGamePresenceSnapshot(): Promise<GamePresenceSnapshot> {
	return await buildGamePresenceSnapshot({
		candidates: await Backend.getAssociationCandidates(),
		nativeInventory: runtimeNativeInventory(),
		nonSteamInventory: runtimeNonSteamInventory(),
		runningAppIds: runtimeRunningAppIds(),
		getAppDetails: getAppDetailsResult,
		nativeInstallProbe: runtimeNativeInstallProbe(),
		resolvePayloads: Backend.resolveGamePayloads,
	});
}
