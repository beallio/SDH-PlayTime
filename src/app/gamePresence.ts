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
	| "resolver_inconsistent"
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
	/** Present only when recognized shortcut evidence identified a supported launcher. */
	launcherKind?: "direct" | "heroic" | "flatpak";
	tracked: boolean;
	recentPlaytime: number;
	totalPlaytime: number;
	inventory: GameInventoryPresence;
	availability: GameAvailabilityPresence;
};

export type GamePresenceInventory = {
	status: "complete" | "loading" | "partial" | "failed" | "missing";
	apps: ReadonlyArray<{ id: string; name: string }>;
};

export type GamePresenceInventoryCompleteness =
	| { status: "complete" }
	| {
			status: "incomplete";
			reason: "loading" | "partial" | "failed" | "missing";
	  };

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

type FlatpakInstallProbe = (flatpakAppId: string) => Promise<boolean>;

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
	checkFlatpakInstall?: FlatpakInstallProbe;
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

/**
 * Optional, read-only overrides for the production Steam runtime adapter. A caller may
 * provide inventory status only when it has authoritative load-completion evidence.
 */
export type GamePresenceRuntimeAdapter = {
	nativeInventory?: () => GamePresenceInventory;
	nonSteamInventory?: () => GamePresenceInventory;
	runningAppIds?: () => ReadonlyArray<number | string>;
	getAppDetails?: (appId: number) => Promise<AppDetailsResult>;
	nativeInstallProbe?: NativeInstallProbe;
	checkFlatpakInstall?: FlatpakInstallProbe;
};

type CandidateSeed = {
	id: string;
	name: string;
	tracked: boolean;
	source?: GamePresenceSource;
	sourceInferred: boolean;
	recentPlaytime: number;
	totalPlaytime: number;
};

type ReliableNativeInstallApi = {
	Apps?: {
		BIsAppInstalled?: (appId: number) => boolean;
	};
};

type RuntimeAppStoreGame = {
	appid: number;
	app_type?: number;
	installed?: boolean;
	is_installed?: boolean;
};

const sourceOrder: readonly GamePresenceSource[] = [
	"native_steam",
	"non_steam",
];
const DEFAULT_DETAIL_CONCURRENCY = 4;
const MAX_DETAIL_CONCURRENCY = 8;
/** Steam shortcut IDs are CRC32 values with bit 31 set; native Steam AppIDs do not. */
const STEAM_SHORTCUT_HIGH_BIT = 0x80000000;
/** Keep every client call inside the backend coordinator's declared maximum. */
const MAX_RESOLUTION_BATCH_SIZE = 32;

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
	if (!Number.isSafeInteger(appId)) {
		return;
	}
	const normalizedAppId = appId < 0 ? appId >>> 0 : appId;
	return Number.isSafeInteger(normalizedAppId) ? normalizedAppId : undefined;
}

function toSteamCallbackAppId(appId: number) {
	return appId > 0x7fffffff ? appId - 0x100000000 : appId;
}

function normalizeAppIdForInventory(appId: number) {
	if (!Number.isSafeInteger(appId)) {
		return;
	}
	return String(appId < 0 ? appId >>> 0 : appId);
}

function normalizeIdString(id: string) {
	const appId = Number(id);
	return Number.isSafeInteger(appId)
		? String(appId < 0 ? appId >>> 0 : appId)
		: id;
}

/**
 * Derive the source of a retained tracked row from its stored Steam AppID, not from
 * mutable display text or playtime. Steam creates shortcut IDs as
 * `crc32(exe + appname) | 0x80000000`; non-numeric and out-of-range legacy IDs stay
 * unknown so they can never become historical by inference.
 */
function sourceFromStoredSteamAppId(
	id: string,
): GamePresenceSource | undefined {
	const appId = Number(id);
	if (!Number.isSafeInteger(appId)) {
		return;
	}
	const normalizedAppId = appId < 0 ? appId >>> 0 : appId;
	if (normalizedAppId > 0xffffffff) {
		return;
	}
	return normalizedAppId >= STEAM_SHORTCUT_HIGH_BIT
		? "non_steam"
		: "native_steam";
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
		const candidateId = normalizeIdString(candidate.game.id);
		seeds.set(candidateId, {
			id: candidateId,
			name: candidate.game.name,
			tracked: true,
			source: candidate.source ?? sourceFromStoredSteamAppId(candidateId),
			sourceInferred: candidate.source === undefined,
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
				sourceInferred: false,
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
		if (seed.source) {
			if (seed.source !== presentSource && !seed.sourceInferred) {
				return {
					source: "unknown",
					inventory: {
						status: "unknown",
						reasons: [reason("inventory_source_conflict", "resolver")],
					},
				};
			}
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
	callback: (value: T, index: number) => Promise<R>,
): Promise<R[]> {
	const results = new Array<R>(values.length);
	let nextIndex = 0;
	const worker = async () => {
		while (nextIndex < values.length) {
			const index = nextIndex++;
			results[index] = await callback(values[index] as T, index);
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

function markResolverUnknown(
	candidate: GamePresenceCandidate,
	code: "resolver_failed" | "resolver_incomplete" | "resolver_inconsistent",
) {
	candidate.availability = {
		status: "unknown",
		reasons: [reason(code, "resolver")],
	};
}

function resolverResultMatchesRequest(
	result: GameResolutionResult,
	request: GameResolutionRequest,
) {
	return (
		result.launcherKind === request.launcherKind &&
		result.classificationStatus === request.classificationStatus
	);
}

function hasConfirmedRegularPayload(
	result: GameResolutionResult,
	request: GameResolutionRequest,
) {
	if (
		!resolverResultMatchesRequest(result, request) ||
		result.payloadStatus !== "reachable" ||
		((request.launcherKind === "direct" || request.launcherKind === "heroic") &&
			result.payloadKind !== "file") ||
		(request.launcherKind === "flatpak" &&
			result.payloadKind !== "directory") ||
		typeof result.payloadPath !== "string" ||
		result.payloadPath.length === 0
	) {
		return false;
	}
	return request.launcherKind === "direct"
		? result.metadataStatus === "not_requested" &&
				result.provenance === "direct_executable"
		: request.launcherKind === "heroic"
			? result.metadataStatus === "resolved" &&
				result.provenance === "heroic_metadata"
			: request.launcherKind === "flatpak"
				? result.metadataStatus === "not_requested" &&
					result.provenance === "untrusted_hint"
				: false;
}

function makeFlatpakInstallProbeRequest(
	flatpakAppId: string,
): GameResolutionRequest {
	return {
		launcherKind: "flatpak",
		classificationStatus: "recognized",
		normalized: {
			flatpakAppId,
			executableTokens: ["/usr/bin/flatpak"],
			launchOptionTokens: ["run", flatpakAppId],
			startDirTokens: [],
			commandTokens: ["/usr/bin/flatpak"],
		},
		metadataCandidates: [],
	};
}

async function checkFlatpakInstallWithResolverFallback(
	flatpakAppId: string,
	resolvePayloads: GamePresenceBuildInput["resolvePayloads"],
): Promise<boolean> {
	const request = makeFlatpakInstallProbeRequest(flatpakAppId);
	const response = await resolvePayloads([request]);
	if (response.error) {
		throw new Error(response.error);
	}
	if (response.results.length !== 1) {
		throw new Error("incomplete flatpak probe payload batch");
	}
	const result = response.results[0];
	if (!result || !resolverResultMatchesRequest(result, request)) {
		throw new Error("inconsistent flatpak probe payload result");
	}
	if (result.payloadStatus === "reachable") {
		if (hasConfirmedRegularPayload(result, request)) {
			return true;
		}
		throw new Error("incomplete flatpak probe payload");
	}
	if (
		result.payloadStatus === "unreachable" &&
		result.reasonCode === "payload_missing"
	) {
		return false;
	}
	throw new Error(result.reasonCode ?? "resolver_unreachable");
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
			if (evidence.status === "not_installed") {
				candidate.inventory = {
					status: "unknown",
					reasons: [reason("native_not_installed", "native_steam")],
				};
			}
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
	const flatpakInstallProbe = input.checkFlatpakInstall;
	const detailCache = new Map<number, Promise<AppDetailsResult>>();
	const getCachedDetails = (appId: number) => {
		let details = detailCache.get(appId);
		if (!details) {
			details = input.getAppDetails(appId);
			detailCache.set(appId, details);
		}
		return details;
	};
	const resolutionCandidates: Array<
		| {
				candidate: (typeof candidates)[number];
				flatpakAppId?: string;
				request: GameResolutionRequest;
		  }
		| undefined
	> = new Array(toResolve.length);

	await mapWithConcurrency(
		toResolve,
		normalizeConcurrency(input.detailConcurrency),
		async (candidate, index) => {
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
				details = await getCachedDetails(toSteamCallbackAppId(appId));
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
			if (
				evidence.status !== "recognized" ||
				(evidence.launcherKind !== "direct" &&
					evidence.launcherKind !== "heroic" &&
					evidence.launcherKind !== "flatpak")
			) {
				candidate.availability = {
					status: "unknown",
					reasons: [reason("resolver_unknown", "resolver")],
				};
				return;
			}
			candidate.launcherKind = evidence.launcherKind;
			resolutionCandidates[index] = {
				candidate,
				flatpakAppId: evidence.normalized.flatpakAppId,
				request: {
					launcherKind: evidence.launcherKind,
					classificationStatus: evidence.status,
					normalized: evidence.normalized,
					metadataCandidates: [],
				},
			};
		},
	);

	const resolvableCandidates = resolutionCandidates.filter(
		(
			candidate,
		): candidate is {
			candidate: GamePresenceCandidate;
			flatpakAppId?: string;
			request: GameResolutionRequest;
		} => candidate !== undefined,
	);
	const flatpakProbeCandidates: Array<{
		candidate: GamePresenceCandidate;
		flatpakAppId: string;
	}> = [];
	for (
		let start = 0;
		start < resolvableCandidates.length;
		start += MAX_RESOLUTION_BATCH_SIZE
	) {
		const batch = resolvableCandidates.slice(
			start,
			start + MAX_RESOLUTION_BATCH_SIZE,
		);
		try {
			const response = await input.resolvePayloads(
				batch.map(({ request }) => request),
			);
			if (response.error) {
				for (const { candidate } of batch) {
					markResolverUnknown(candidate, "resolver_failed");
				}
				continue;
			}
			if (response.results.length !== batch.length) {
				for (const { candidate } of batch) {
					markResolverUnknown(candidate, "resolver_incomplete");
				}
				continue;
			}
			for (const [
				index,
				{ candidate, request, flatpakAppId },
			] of batch.entries()) {
				const result = response.results[index];
				if (!result || !resolverResultMatchesRequest(result, request)) {
					markResolverUnknown(candidate, "resolver_inconsistent");
					continue;
				}
				if (result.payloadStatus === "reachable") {
					candidate.availability = hasConfirmedRegularPayload(result, request)
						? { status: "reachable", reasons: [] }
						: {
								status: "unknown",
								reasons: [reason("resolver_inconsistent", "resolver")],
							};
					continue;
				}
				if (
					request.launcherKind === "flatpak" &&
					result.payloadStatus === "unknown" &&
					typeof flatpakAppId === "string" &&
					flatpakAppId.length > 0 &&
					flatpakInstallProbe
				) {
					flatpakProbeCandidates.push({
						candidate,
						flatpakAppId,
					});
					continue;
				}
				candidate.availability =
					result.payloadStatus === "unreachable"
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
			for (const { candidate } of batch) {
				markResolverUnknown(candidate, "resolver_failed");
			}
		}
	}

	if (flatpakProbeCandidates.length > 0) {
		const flatpakChecks = await Promise.allSettled(
			flatpakProbeCandidates.map(async ({ candidate, flatpakAppId }) => ({
				candidate,
				installed: await flatpakInstallProbe?.(flatpakAppId),
			})),
		);
		for (const check of flatpakChecks) {
			if (check.status !== "fulfilled") {
				continue;
			}
			if (
				check.value.candidate.availability.status !== "unknown" ||
				check.value.installed === undefined
			) {
				continue;
			}
			check.value.candidate.availability = check.value.installed
				? { status: "reachable", reasons: [] }
				: {
						status: "unreachable",
						reasons: [reason("resolver_unreachable", "resolver")],
					};
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
		// Runtime `allApps` provides an authoritative, cache-backed view in practice.
		status: "complete",
		apps: appStore.allApps
			.filter((app) => app.app_type !== APP_TYPE.THIRD_PARTY)
			.flatMap((app) => {
				const id = normalizeAppIdForInventory(app.appid);
				return id ? [{ id, name: app.display_name }] : [];
			}),
	};
}

function runtimeNonSteamInventory(): GamePresenceInventory {
	const deckDesktopApps =
		typeof collectionStore !== "undefined"
			? collectionStore.deckDesktopApps
			: null;
	const deckDesktopRows =
		deckDesktopApps?.apps instanceof Map
			? Array.from(deckDesktopApps.apps.values())
			: [];
	if (typeof appStore === "undefined" || !Array.isArray(appStore.allApps)) {
		return {
			status: deckDesktopRows.length > 0 ? "complete" : "missing",
			apps: deckDesktopRows
				.map((app) => {
					const id = normalizeAppIdForInventory(app.appid);
					return id ? { id, name: app.display_name } : undefined;
				})
				.filter(
					(app): app is { id: string; name: string } => app !== undefined,
				),
		};
	}

	const appsById = new Map<string, { id: string; name: string }>();
	for (const app of deckDesktopRows) {
		const id = normalizeAppIdForInventory(app.appid);
		if (id && !appsById.has(id)) {
			appsById.set(id, { id, name: app.display_name });
		}
	}
	for (const app of appStore.allApps) {
		if (app.app_type !== APP_TYPE.THIRD_PARTY) {
			continue;
		}
		const id = normalizeAppIdForInventory(app.appid);
		if (id && !appsById.has(id)) {
			appsById.set(id, { id, name: app.display_name });
		}
	}

	return {
		status: "complete",
		apps: [...appsById.values()],
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
		appStore?: {
			allApps?: RuntimeAppStoreGame[];
		};
		collectionStore?: {
			localGamesCollection?: {
				allApps?: Array<{ appid: number }>;
			};
		};
	};
	const probe = runtime.SteamClient?.Apps?.BIsAppInstalled;
	if (typeof probe !== "function") {
		const appStoreGames = Array.isArray(runtime.appStore?.allApps)
			? runtime.appStore.allApps
			: undefined;
		const localGameAppIds = Array.isArray(
			runtime.collectionStore?.localGamesCollection?.allApps,
		)
			? new Set(
					runtime.collectionStore.localGamesCollection.allApps.map(
						(app) => app.appid,
					),
				)
			: undefined;
		if (!appStoreGames && !localGameAppIds) {
			return;
		}

		return (appId: number) => {
			const app = appStoreGames?.find(
				(game) =>
					game.appid === appId || game.appid === toSteamCallbackAppId(appId),
			);
			if (typeof app?.installed === "boolean") {
				return { status: app.installed ? "installed" : "not_installed" };
			}
			if (typeof app?.is_installed === "boolean") {
				return {
					status: app.is_installed ? "installed" : "not_installed",
				};
			}
			if (localGameAppIds) {
				return {
					status:
						localGameAppIds.has(appId) ||
						localGameAppIds.has(toSteamCallbackAppId(appId))
							? "installed"
							: "not_installed",
				};
			}
			return { status: "unknown" };
		};
	}
	return (appId) => ({ status: probe(appId) ? "installed" : "not_installed" });
}

async function runtimeGetAppDetails(appId: number): Promise<AppDetailsResult> {
	const directResult = await getAppDetailsResult(appId);
	if (directResult.status === "success") {
		return directResult;
	}

	const catalogAppId = appId < 0 ? appId >>> 0 : appId;
	try {
		const shortcutDetails = await Backend.getShortcutAppDetails(catalogAppId);
		return shortcutDetails.status === "success" && shortcutDetails.details
			? shortcutDetails
			: directResult;
	} catch {
		return directResult;
	}
}

function runtimeFlatpakInstallProbe(
	resolvePayloads: GamePresenceBuildInput["resolvePayloads"],
): FlatpakInstallProbe {
	return async (flatpakAppId: string) => {
		try {
			return await Backend.isFlatpakAppInstalled(flatpakAppId);
		} catch {
			return await checkFlatpakInstallWithResolverFallback(
				flatpakAppId,
				resolvePayloads,
			);
		}
	};
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
export async function refreshCurrentGamePresenceSnapshot(
	runtime: GamePresenceRuntimeAdapter = {},
): Promise<GamePresenceSnapshot> {
	return await buildGamePresenceSnapshot({
		candidates: await Backend.getAssociationCandidates(),
		nativeInventory: runtime.nativeInventory?.() ?? runtimeNativeInventory(),
		nonSteamInventory:
			runtime.nonSteamInventory?.() ?? runtimeNonSteamInventory(),
		runningAppIds: runtime.runningAppIds?.() ?? runtimeRunningAppIds(),
		getAppDetails: runtime.getAppDetails ?? runtimeGetAppDetails,
		nativeInstallProbe:
			runtime.nativeInstallProbe ?? runtimeNativeInstallProbe(),
		checkFlatpakInstall:
			runtime.checkFlatpakInstall ??
			runtimeFlatpakInstallProbe((requests) =>
				Backend.resolveGamePayloads(requests),
			),
		resolvePayloads: Backend.resolveGamePayloads,
	});
}
