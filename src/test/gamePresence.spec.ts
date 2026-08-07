import { afterEach, beforeEach, describe, expect, mock, test } from "bun:test";
import { APP_TYPE, BACK_END_API } from "@src/constants";

const backendCalls: unknown[][] = [];
let backendCallHandler: (...args: unknown[]) => Promise<unknown>;

mock.module("@decky/api", () => ({
	call: async (...args: unknown[]) => {
		backendCalls.push(args);
		return await backendCallHandler(...args);
	},
}));

const {
	buildGamePresenceSnapshot,
	refreshCurrentGamePresenceSnapshot,
	refreshGamePresenceSnapshot,
} = await import("@src/app/gamePresence");
type GamePresenceBuildInput =
	import("@src/app/gamePresence").GamePresenceBuildInput;

const nativeApp = {
	id: "10",
	name: "Native Game",
	source: "native_steam" as const,
};

const shortcutApp = {
	id: "20",
	name: "Shortcut Game",
	source: "non_steam" as const,
};

function detailsResult() {
	return {
		status: "success" as const,
		details: { strShortcutExe: '"/games/Game.exe"' } as AppDetails,
	};
}

function directDetails(appId: number) {
	return {
		status: "success" as const,
		details: {
			strShortcutExe: `"/games/${appId}.exe"`,
		} as AppDetails,
	};
}

function flatpakDetails(appId: number) {
	return {
		status: "success" as const,
		details: {
			strShortcutExe: "/usr/bin/flatpak",
			strShortcutLaunchOptions: `run com.example.flatpak.${appId}`,
			strFlatpakAppID: `com.example.flatpak.${appId}`,
		} as AppDetails,
	};
}

function flatpakDetailsFromLaunchHints(appId: number) {
	return {
		status: "success" as const,
		details: {
			strShortcutExe: "/usr/bin/flatpak",
			strShortcutLaunchOptions: `run --user --command=ludusavi com.example.flatpak.${appId}`,
		} as AppDetails,
	};
}

function reachableResult() {
	return {
		launcherKind: "direct" as const,
		classificationStatus: "recognized" as const,
		metadataStatus: "not_requested" as const,
		payloadStatus: "reachable" as const,
		payloadKind: "file" as const,
		provenance: "direct_executable" as const,
		reasonCode: null,
		payloadPath: "/verified/game.exe",
	};
}

function build(overrides: Partial<GamePresenceBuildInput> = {}) {
	return buildGamePresenceSnapshot({
		candidates: [],
		nativeInventory: { status: "complete", apps: [] },
		nonSteamInventory: { status: "complete", apps: [] },
		runningAppIds: [],
		getAppDetails: async () => detailsResult(),
		nativeInstallProbe: async () => ({ status: "installed" }),
		resolvePayloads: async (requests) => ({
			results: requests.map(() => ({
				launcherKind: "direct",
				classificationStatus: "recognized",
				metadataStatus: "not_requested",
				payloadStatus: "reachable",
				payloadKind: "file",
				provenance: "direct_executable",
				reasonCode: null,
				payloadPath: "/personal/path/that-must-not-leak",
			})),
			error: null,
		}),
		...overrides,
	});
}

type TestAppStoreEntry = {
	appid: number;
	display_name: string;
	app_type: number;
	installed?: boolean;
	per_client_data?: Array<{ is_available_on_current_platform: boolean }>;
};
type TestDeckDesktopApp = { appid: number; display_name: string };
type RuntimeTestFixtures = {
	appStore?: { allApps: TestAppStoreEntry[] };
	collectionStore?: {
		deckDesktopApps?: {
			apps: Map<number, TestDeckDesktopApp>;
		};
	};
	SteamClient?: { Apps?: { BIsAppInstalled: (appId: number) => boolean } };
};

function setRuntimeFixtures(fixture: Partial<RuntimeTestFixtures>) {
	Object.assign(globalThis as unknown as RuntimeTestFixtures, fixture);
}

describe("buildGamePresenceSnapshot", () => {
	afterEach(() => {
		for (const key of ["appStore", "collectionStore", "SteamClient"] as const) {
			delete (globalThis as unknown as Record<string, unknown>)[key];
		}
	});

	beforeEach(() => {
		backendCalls.length = 0;
		backendCallHandler = async () => undefined;
	});

	test("derives historical source from the stored Steam AppID when the backend sends only game and duration", async () => {
		const rawCandidates = [
			{ game: { id: "10", name: "Removed native" }, duration: 1 },
			{
				game: { id: String(0x80000001), name: "Removed shortcut" },
				duration: 2,
			},
		];
		const sourceOnly = await refreshGamePresenceSnapshot({
			nativeInventory: { status: "complete", apps: [] },
			nonSteamInventory: { status: "loading", apps: [] },
			runningAppIds: [],
			getAppDetails: async () => detailsResult(),
			nativeInstallProbe: async () => ({ status: "installed" }),
			resolvePayloads: async () => ({ results: [], error: null }),
			getCandidates: async () => rawCandidates,
		});

		expect(
			sourceOnly.candidates.map((candidate) => [
				candidate.source,
				candidate.inventory.status,
			]),
		).toEqual([
			["native_steam", "historical"],
			["non_steam", "unknown"],
		]);

		const reversedCompleteness = await refreshGamePresenceSnapshot({
			nativeInventory: { status: "failed", apps: [] },
			nonSteamInventory: { status: "complete", apps: [] },
			runningAppIds: [],
			getAppDetails: async () => detailsResult(),
			nativeInstallProbe: async () => ({ status: "installed" }),
			resolvePayloads: async () => ({ results: [], error: null }),
			getCandidates: async () => rawCandidates,
		});

		expect(
			reversedCompleteness.candidates.map(
				(candidate) => candidate.inventory.status,
			),
		).toEqual(["unknown", "historical"]);
	});

	test("keeps source completeness independent while deriving current, historical, and unknown inventory", async () => {
		const snapshot = await build({
			candidates: [
				{
					game: { id: "10", name: "Native Game" },
					duration: 8,
					source: "native_steam",
				},
				{
					game: { id: "20", name: "Removed Shortcut" },
					duration: 99,
					source: "non_steam",
				},
				{
					game: { id: "30", name: "Unknown Shortcut" },
					duration: 1,
					source: "non_steam",
				},
			],
			nativeInventory: { status: "complete", apps: [nativeApp] },
			nonSteamInventory: { status: "loading", apps: [shortcutApp] },
		});

		expect(snapshot.inventories).toEqual({
			native_steam: { status: "complete" },
			non_steam: { status: "incomplete", reason: "loading" },
		});
		expect(
			snapshot.candidates.map((candidate) => [
				candidate.id,
				candidate.inventory.status,
			]),
		).toEqual([
			["10", "current"],
			["20", "unknown"],
			["30", "unknown"],
		]);
		expect(snapshot.candidates[0]?.availability).toMatchObject({
			status: "reachable",
			label: "Installed",
		});

		const complete = await build({
			candidates: [
				{
					game: { id: "20", name: "Removed Shortcut" },
					duration: 99,
					source: "non_steam",
				},
			],
		});
		expect(complete.candidates[0]?.inventory).toEqual({
			status: "historical",
			reasons: [
				{ code: "omitted_from_complete_inventory", source: "non_steam" },
			],
		});
	});

	test("includes live library entries without tracked rows and uses reliable native install evidence only", async () => {
		const snapshot = await build({
			nativeInventory: { status: "complete", apps: [nativeApp] },
			nonSteamInventory: { status: "complete", apps: [shortcutApp] },
			nativeInstallProbe: undefined,
		});

		expect(
			snapshot.candidates.map((candidate) => [candidate.id, candidate.tracked]),
		).toEqual([
			["10", false],
			["20", false],
		]);
		expect(snapshot.candidates[0]?.availability).toEqual({
			status: "unknown",
			reasons: [
				{ code: "native_install_probe_unavailable", source: "native_steam" },
			],
		});
		expect(snapshot.candidates[1]?.availability).toMatchObject({
			status: "reachable",
			label: "Available on this Deck",
		});
		expect(JSON.stringify(snapshot)).not.toContain(
			"/personal/path/that-must-not-leak",
		);
	});

	test("carries recognized direct and Heroic launcher kinds into the presence snapshot", async () => {
		const snapshot = await build({
			candidates: [
				{
					game: { id: "20", name: "Direct shortcut" },
					duration: 1,
					source: "non_steam",
				},
				{
					game: { id: "21", name: "Heroic shortcut" },
					duration: 1,
					source: "non_steam",
				},
			],
			nonSteamInventory: {
				status: "complete",
				apps: [
					{ id: "20", name: "Direct shortcut" },
					{ id: "21", name: "Heroic shortcut" },
				],
			},
			getAppDetails: async (appId) =>
				appId === 20
					? directDetails(appId)
					: {
							status: "success" as const,
							details: {
								strShortcutExe: "/opt/Heroic/heroic",
								strShortcutLaunchOptions:
									"heroic://launch?appName=space%20game&runner=legendary",
							} as AppDetails,
						},
			resolvePayloads: async (requests) => ({
				results: requests.map((request) =>
					request.launcherKind === "direct"
						? reachableResult()
						: {
								launcherKind: "heroic" as const,
								classificationStatus: "recognized" as const,
								metadataStatus: "resolved" as const,
								payloadStatus: "reachable" as const,
								payloadKind: "file" as const,
								provenance: "heroic_metadata" as const,
								reasonCode: null,
								payloadPath: "/verified/heroic-game.exe",
							},
				),
				error: null,
			}),
		});

		expect(
			snapshot.candidates.map((candidate) => [
				candidate.id,
				candidate.launcherKind,
			]),
		).toEqual([
			["20", "direct"],
			["21", "heroic"],
		]);
	});

	test("supports Flatpak resolver outcomes for completed non-Steam inventory", async () => {
		const nonSteamId = String(0x80000001);
		const snapshot = await build({
			candidates: [
				{ game: { id: nonSteamId, name: "Flatpak Shortcut" }, duration: 1 },
			],
			nonSteamInventory: {
				status: "complete",
				apps: [{ id: nonSteamId, name: "Flatpak Shortcut" }],
			},
			getAppDetails: async () => flatpakDetails(1234),
			resolvePayloads: async () => ({
				results: [
					{
						launcherKind: "flatpak",
						classificationStatus: "recognized",
						metadataStatus: "not_requested",
						payloadStatus: "reachable",
						payloadKind: "directory",
						provenance: "untrusted_hint",
						reasonCode: null,
						payloadPath: "/var/lib/flatpak/app/com.example.flatpak.1234",
					},
				],
				error: null,
			}),
		});

		expect(snapshot.candidates).toHaveLength(1);
		expect(snapshot.candidates[0]).toMatchObject({
			id: nonSteamId,
			source: "non_steam",
			inventory: { status: "current", reasons: [] },
			launcherKind: "flatpak",
			availability: {
				status: "reachable",
				label: "Available on this Deck",
			},
		});
	});

	test("falls back to flatpak install probe when payload is malformed", async () => {
		const nonSteamId = String(0x80000001);
		const snapshot = await build({
			candidates: [
				{ game: { id: nonSteamId, name: "Flatpak Shortcut" }, duration: 1 },
			],
			nonSteamInventory: {
				status: "complete",
				apps: [{ id: nonSteamId, name: "Flatpak Shortcut" }],
			},
			getAppDetails: async () => flatpakDetails(1234),
			resolvePayloads: async () => ({
				results: [
					{
						launcherKind: "flatpak",
						classificationStatus: "recognized",
						metadataStatus: "not_requested",
						payloadStatus: "unknown",
						payloadKind: "directory",
						provenance: "untrusted_hint",
						reasonCode: "malformed",
						payloadPath: null,
					},
				],
				error: null,
			}),
			checkFlatpakInstall: async () => true,
		});

		expect(snapshot.candidates[0]).toMatchObject({
			id: nonSteamId,
			source: "non_steam",
			availability: {
				status: "reachable",
				label: "Available on this Deck",
			},
		});
	});

	test("hydrates flatpak evidence from launch hints when explicit flatpak ID is missing", async () => {
		const nonSteamId = String(0x80000001);
		let flatpakProbeAttempts = 0;
		const snapshot = await build({
			candidates: [
				{ game: { id: nonSteamId, name: "Flatpak Shortcut" }, duration: 1 },
			],
			nonSteamInventory: {
				status: "complete",
				apps: [{ id: nonSteamId, name: "Flatpak Shortcut" }],
			},
			getAppDetails: async () => flatpakDetailsFromLaunchHints(1234),
			resolvePayloads: async () => ({
				results: [
					{
						launcherKind: "flatpak",
						classificationStatus: "recognized",
						metadataStatus: "not_requested",
						payloadStatus: "unknown",
						payloadKind: "directory",
						provenance: "untrusted_hint",
						reasonCode: "malformed",
						payloadPath: null,
					},
				],
				error: null,
			}),
			checkFlatpakInstall: async () => {
				flatpakProbeAttempts += 1;
				return true;
			},
		});

		expect(snapshot.candidates[0]).toMatchObject({
			id: nonSteamId,
			source: "non_steam",
			availability: {
				status: "reachable",
				label: "Available on this Deck",
			},
		});
		expect(flatpakProbeAttempts).toBe(1);
	});

	test("preserves flatpak unknown state when flatpak probe is rejected", async () => {
		const nonSteamId = String(0x80000001);
		const snapshot = await build({
			candidates: [
				{ game: { id: nonSteamId, name: "Flatpak Shortcut" }, duration: 1 },
			],
			nonSteamInventory: {
				status: "complete",
				apps: [{ id: nonSteamId, name: "Flatpak Shortcut" }],
			},
			getAppDetails: async () => flatpakDetails(1234),
			resolvePayloads: async () => ({
				results: [
					{
						launcherKind: "flatpak",
						classificationStatus: "recognized",
						metadataStatus: "not_requested",
						payloadStatus: "unknown",
						payloadKind: "directory",
						provenance: "untrusted_hint",
						reasonCode: "malformed",
						payloadPath: null,
					},
				],
				error: null,
			}),
			checkFlatpakInstall: async () => {
				throw new Error("probe unavailable");
			},
		});

		expect(snapshot.candidates[0]).toMatchObject({
			id: nonSteamId,
			availability: {
				status: "unknown",
				reasons: [],
			},
		});
	});

	test("preserves inventory while a shortcut drive disconnects and reconnects", async () => {
		const input: Pick<
			GamePresenceBuildInput,
			"candidates" | "nonSteamInventory"
		> = {
			candidates: [
				{
					game: { id: "20", name: "Shortcut Game" },
					duration: 12,
					source: "non_steam",
				},
			],
			nonSteamInventory: { status: "complete" as const, apps: [shortcutApp] },
		};
		const disconnected = await build({
			...input,
			resolvePayloads: async (requests) => ({
				results: requests.map(() => ({
					launcherKind: "direct",
					classificationStatus: "recognized",
					metadataStatus: "not_requested",
					payloadStatus: "unreachable",
					payloadKind: "unknown",
					provenance: "none",
					reasonCode: "drive_disconnected",
					payloadPath: null,
				})),
				error: null,
			}),
		});
		const reconnected = await build(input);

		expect(disconnected.candidates[0]?.inventory.status).toBe("current");
		expect(disconnected.candidates[0]?.availability).toEqual({
			status: "unreachable",
			reasons: [{ code: "drive_disconnected", source: "resolver" }],
		});
		expect(reconnected.candidates[0]?.inventory.status).toBe("current");
		expect(reconnected.candidates[0]?.availability.status).toBe("reachable");
	});

	test("batches resolution into 32-entry requests, preserves correlation, and fails only a malformed batch closed", async () => {
		const shortcutIds = Array.from({ length: 65 }, (_, index) =>
			String(0x80000000 + index + 1),
		);
		const batches: number[] = [];
		const snapshot = await build({
			candidates: shortcutIds.map((id) => ({
				game: { id, name: `Shortcut ${id}` },
				duration: 1,
			})),
			nonSteamInventory: {
				status: "complete",
				apps: shortcutIds.map((id) => ({ id, name: `Shortcut ${id}` })),
			},
			getAppDetails: async (appId) => directDetails(appId),
			resolvePayloads: async (requests) => {
				batches.push(requests.length);
				if (batches.length === 2) {
					return { results: [], error: "timeout" };
				}
				return { results: requests.map(() => reachableResult()), error: null };
			},
		});

		expect(batches).toEqual([32, 32, 1]);
		expect(snapshot.candidates[0]?.availability.status).toBe("reachable");
		expect(snapshot.candidates[31]?.availability.status).toBe("reachable");
		expect(snapshot.candidates[32]?.availability).toEqual({
			status: "unknown",
			reasons: [{ code: "resolver_failed", source: "resolver" }],
		});
		expect(snapshot.candidates[64]?.availability.status).toBe("reachable");

		const thirtyThreeBatches: number[] = [];
		await build({
			candidates: shortcutIds.slice(0, 33).map((id) => ({
				game: { id, name: `Shortcut ${id}` },
				duration: 1,
			})),
			nonSteamInventory: {
				status: "complete",
				apps: shortcutIds
					.slice(0, 33)
					.map((id) => ({ id, name: `Shortcut ${id}` })),
			},
			getAppDetails: async (appId) => directDetails(appId),
			resolvePayloads: async (requests) => {
				thirtyThreeBatches.push(requests.length);
				return { results: requests.map(() => reachableResult()), error: null };
			},
		});
		expect(thirtyThreeBatches).toEqual([32, 1]);

		const resolveByRequestIdentity = async (
			requests: GameResolutionRequest[],
		) => ({
			results: requests.map((request) => {
				const appId = Number(
					request.normalized.executableTokens[0]?.match(/\d+/)?.[0],
				);
				return appId % 2 === 0
					? reachableResult()
					: {
							...reachableResult(),
							payloadStatus: "unreachable" as const,
							payloadKind: "unknown" as const,
							reasonCode: "payload_missing" as const,
							payloadPath: null,
						};
			}),
			error: null,
		});
		const orderIndependentInput = shortcutIds.slice(0, 33);
		const fromOrder = async (ids: string[]) =>
			await build({
				candidates: ids.map((id) => ({
					game: { id, name: `Shortcut ${id}` },
					duration: 1,
				})),
				nonSteamInventory: {
					status: "complete",
					apps: ids.map((id) => ({ id, name: `Shortcut ${id}` })),
				},
				getAppDetails: async (appId) => directDetails(appId),
				resolvePayloads: resolveByRequestIdentity,
			});
		const ordered = await fromOrder(orderIndependentInput);
		const reversed = await fromOrder([...orderIndependentInput].reverse());
		const availabilityById = (candidates: typeof ordered.candidates) =>
			Object.fromEntries(
				candidates.map((candidate) => [
					candidate.id,
					candidate.availability.status,
				]),
			);
		expect(availabilityById(reversed.candidates)).toEqual(
			availabilityById(ordered.candidates),
		);
	});

	test("rejects resolver result-count and payload-proof mismatches without leaking payload paths", async () => {
		const snapshot = await build({
			candidates: [
				{
					game: { id: String(0x80000001), name: "Missing proof" },
					duration: 1,
				},
				{ game: { id: String(0x80000002), name: "Directory" }, duration: 1 },
			],
			nonSteamInventory: {
				status: "complete",
				apps: [
					{ id: String(0x80000001), name: "Missing proof" },
					{ id: String(0x80000002), name: "Directory" },
				],
			},
			getAppDetails: async (appId) => directDetails(appId),
			resolvePayloads: async () => ({
				results: [
					{ ...reachableResult(), payloadPath: null },
					{ ...reachableResult(), payloadKind: "directory" as const },
				],
				error: null,
			}),
		});

		expect(
			snapshot.candidates.map((candidate) => candidate.availability.status),
		).toEqual(["unknown", "unknown"]);
		expect(JSON.stringify(snapshot)).not.toContain("/verified/game.exe");

		const malformed = await build({
			candidates: [
				{ game: { id: String(0x80000003), name: "Malformed" }, duration: 1 },
			],
			nonSteamInventory: {
				status: "complete",
				apps: [{ id: String(0x80000003), name: "Malformed" }],
			},
			getAppDetails: async (appId) => directDetails(appId),
			resolvePayloads: async () => ({
				results: [reachableResult(), reachableResult()],
				error: null,
			}),
		});
		expect(malformed.candidates[0]?.availability).toEqual({
			status: "unknown",
			reasons: [{ code: "resolver_incomplete", source: "resolver" }],
		});

		const missing = await build({
			candidates: [
				{
					game: { id: String(0x80000004), name: "Missing result" },
					duration: 1,
				},
			],
			nonSteamInventory: {
				status: "complete",
				apps: [{ id: String(0x80000004), name: "Missing result" }],
			},
			getAppDetails: async (appId) => directDetails(appId),
			resolvePayloads: async () => ({ results: [], error: null }),
		});
		expect(missing.candidates[0]?.availability).toEqual({
			status: "unknown",
			reasons: [{ code: "resolver_incomplete", source: "resolver" }],
		});
	});

	test("uses explicit runtime inventory completeness and performs no candidate, association, or checksum writes", async () => {
		const appId = String(0x80000001);
		const inventoryStatuses = [
			"loading",
			"partial",
			"failed",
			"missing",
			"complete",
		] as const;
		for (const status of inventoryStatuses) {
			backendCallHandler = async (method: unknown) => {
				if (method === BACK_END_API.GET_ASSOCIATION_CANDIDATES) {
					return [
						{ game: { id: appId, name: "Runtime Shortcut" }, duration: 1 },
					];
				}
				if (method === BACK_END_API.RESOLVE_GAME_PAYLOADS) {
					return { results: [reachableResult()], error: null };
				}
				throw new Error(`unexpected write or read RPC: ${String(method)}`);
			};
			const snapshot = await refreshCurrentGamePresenceSnapshot({
				nativeInventory: () => ({ status: "complete", apps: [] }),
				nonSteamInventory: () => ({
					status,
					apps: [{ id: appId, name: "Runtime Shortcut" }],
				}),
				runningAppIds: () => [],
				getAppDetails: async (numericId) => directDetails(numericId),
			});
			expect(snapshot.candidates[0]?.inventory.status).toBe(
				status === "complete" ? "current" : "unknown",
			);
			expect(snapshot.candidates[0]?.availability.status).toBe(
				status === "complete" ? "reachable" : "unknown",
			);
			const removed = await refreshCurrentGamePresenceSnapshot({
				nativeInventory: () => ({ status: "complete", apps: [] }),
				nonSteamInventory: () => ({ status, apps: [] }),
				runningAppIds: () => [],
				getAppDetails: async (numericId) => directDetails(numericId),
			});
			expect(removed.candidates[0]?.inventory.status).toBe(
				status === "complete" ? "historical" : "unknown",
			);
			expect(removed.candidates[0]?.availability.status).toBe("unknown");
		}

		const writeMethods: ReadonlySet<string> = new Set([
			BACK_END_API.SAVE_GAME_CHECKSUM,
			BACK_END_API.SAVE_GAME_CHECKSUM_BULK,
			BACK_END_API.CONFIRM_GAME_ASSOCIATION_COMPONENT,
			BACK_END_API.ADD_TIME,
		]);
		expect(
			backendCalls.filter(
				([method]) => typeof method === "string" && writeMethods.has(method),
			),
		).toEqual([]);
	});

	test("marks native entries with explicit not-installed evidence as unavailable inventory", async () => {
		backendCallHandler = async (method: unknown) => {
			if (method === BACK_END_API.GET_ASSOCIATION_CANDIDATES) {
				return [
					{
						game: { id: "10", name: "Uninstalled Runtime Game" },
						duration: 12,
					},
				];
			}
			if (method === BACK_END_API.RESOLVE_GAME_PAYLOADS) {
				return { results: [reachableResult()], error: null };
			}
			throw new Error(`unexpected write or read RPC: ${String(method)}`);
		};

		setRuntimeFixtures({
			appStore: {
				allApps: [
					{
						appid: 10,
						display_name: "Uninstalled Runtime Game",
						app_type: 0,
					},
				],
			},
			SteamClient: {
				Apps: {
					BIsAppInstalled: () => false,
				},
			},
		});

		const snapshot = await refreshCurrentGamePresenceSnapshot({
			getAppDetails: async () => {
				return {
					status: "failure",
					reason: "missing-details",
				};
			},
		});

		expect(snapshot.candidates).toHaveLength(1);
		expect(snapshot.candidates[0]).toMatchObject({
			id: "10",
			source: "native_steam",
			inventory: {
				status: "unknown",
				reasons: [{ code: "native_not_installed", source: "native_steam" }],
			},
			availability: {
				status: "unreachable",
				reasons: [{ code: "native_not_installed", source: "native_steam" }],
			},
		});
	});

	test("uses complete runtime inventory snapshots by default for installed Steam and non-Steam visibility", async () => {
		const nonSteamId = String(0x80000001);
		backendCallHandler = async (method: unknown) => {
			if (method === BACK_END_API.GET_ASSOCIATION_CANDIDATES) {
				return [
					{ game: { id: "10", name: "Native Runtime Game" }, duration: 12 },
					{
						game: { id: nonSteamId, name: "Shortcut Runtime Game" },
						duration: 1,
					},
				];
			}
			if (method === BACK_END_API.RESOLVE_GAME_PAYLOADS) {
				return { results: [reachableResult()], error: null };
			}
			throw new Error(`unexpected write or read RPC: ${String(method)}`);
		};

		setRuntimeFixtures({
			appStore: {
				allApps: [
					{
						appid: 10,
						display_name: "Native Runtime Game",
						app_type: 0,
					},
				],
			},
			collectionStore: {
				deckDesktopApps: {
					apps: new Map([
						[
							0x80000001,
							{
								appid: 0x80000001,
								display_name: "Shortcut Runtime Game",
							},
						],
					]),
				},
			},
			SteamClient: {
				Apps: {
					BIsAppInstalled: (appId: number) => appId === 10,
				},
			},
		});

		const snapshot = await refreshCurrentGamePresenceSnapshot({
			getAppDetails: async (appId) => directDetails(appId),
		});

		expect(snapshot.inventories).toEqual({
			native_steam: { status: "complete" },
			non_steam: { status: "complete" },
		});
		expect(snapshot.candidates).toHaveLength(2);
		const candidatesById = Object.fromEntries(
			snapshot.candidates.map((candidate) => [candidate.id, candidate]),
		);
		expect(candidatesById["10"]?.source).toBe("native_steam");
		expect(candidatesById["10"]?.inventory).toEqual({
			status: "current",
			reasons: [],
		});
		expect(candidatesById["10"]?.availability).toEqual({
			status: "reachable",
			reasons: [],
			label: "Installed",
		});
		expect(candidatesById[nonSteamId]?.source).toBe("non_steam");
		expect(candidatesById[nonSteamId]?.inventory).toEqual({
			status: "current",
			reasons: [],
		});
		expect(candidatesById[nonSteamId]?.availability).toEqual({
			status: "reachable",
			reasons: [],
			label: "Available on this Deck",
		});
		expect(candidatesById[nonSteamId]?.launcherKind).toBe("direct");
	});

	test("falls back to appStore for non-Steam runtime inventory when Deck desktop apps collection is empty", async () => {
		const nonSteamId = String(0x80000001);
		backendCallHandler = async (method: unknown) => {
			if (method === BACK_END_API.GET_ASSOCIATION_CANDIDATES) {
				return [
					{ game: { id: "10", name: "Native Runtime Game" }, duration: 12 },
					{
						game: { id: nonSteamId, name: "Shortcut Runtime Game" },
						duration: 1,
					},
				];
			}
			if (method === BACK_END_API.RESOLVE_GAME_PAYLOADS) {
				return { results: [reachableResult()], error: null };
			}
			throw new Error(`unexpected write or read RPC: ${String(method)}`);
		};

		setRuntimeFixtures({
			appStore: {
				allApps: [
					{
						appid: 10,
						display_name: "Native Runtime Game",
						app_type: 0,
					},
					{
						appid: 0x80000001,
						display_name: "Shortcut Runtime Game",
						app_type: APP_TYPE.THIRD_PARTY,
					},
				],
			},
			collectionStore: {
				deckDesktopApps: {
					apps: new Map(),
				},
			},
			SteamClient: {
				Apps: {
					BIsAppInstalled: (appId: number) => appId === 10,
				},
			},
		});

		const snapshot = await refreshCurrentGamePresenceSnapshot({
			getAppDetails: async (appId) => directDetails(appId),
		});

		const candidatesById = Object.fromEntries(
			snapshot.candidates.map((candidate) => [candidate.id, candidate]),
		);
		expect(candidatesById[nonSteamId]?.source).toBe("non_steam");
		expect(candidatesById[nonSteamId]?.inventory).toEqual({
			status: "current",
			reasons: [],
		});
		expect(candidatesById[nonSteamId]?.availability).toEqual({
			status: "reachable",
			reasons: [],
			label: "Available on this Deck",
		});
	});

	test("recovers flatpak availability when is_flatpak_app_installed is unavailable", async () => {
		const nonSteamId = String(0x80000001);
		let flatpakProbeAttempts = 0;
		backendCallHandler = async (method: unknown) => {
			if (method === BACK_END_API.GET_ASSOCIATION_CANDIDATES) {
				return [
					{
						game: {
							id: nonSteamId,
							name: "Flatpak Runtime Game",
						},
						duration: 1,
					},
				];
			}
			if (method === BACK_END_API.RESOLVE_GAME_PAYLOADS) {
				flatpakProbeAttempts += 1;
				if (flatpakProbeAttempts === 1) {
					return {
						results: [
							{
								launcherKind: "flatpak",
								classificationStatus: "recognized",
								metadataStatus: "not_requested",
								payloadStatus: "unknown",
								payloadKind: "directory",
								provenance: "untrusted_hint",
								reasonCode: "malformed",
								payloadPath: null,
							},
						],
						error: null,
					};
				}
				return {
					results: [
						{
							launcherKind: "flatpak",
							classificationStatus: "recognized",
							metadataStatus: "not_requested",
							payloadStatus: "reachable",
							payloadKind: "directory",
							provenance: "untrusted_hint",
							reasonCode: null,
							payloadPath: "/var/lib/flatpak/app/com.example.flatpak.1234",
						},
					],
					error: null,
				};
			}
			if (method === BACK_END_API.IS_FLATPAK_APP_INSTALLED) {
				throw new Error("METHOD_REJECTED");
			}
			throw new Error(`unexpected write or read RPC: ${String(method)}`);
		};

		setRuntimeFixtures({
			appStore: {
				allApps: [
					{
						appid: 0x80000001,
						display_name: "Flatpak Runtime Game",
						app_type: APP_TYPE.THIRD_PARTY,
					},
				],
			},
			collectionStore: {
				deckDesktopApps: {
					apps: new Map(),
				},
			},
		});

		const snapshot = await refreshCurrentGamePresenceSnapshot({
			getAppDetails: async () => flatpakDetails(1234),
		});

		expect(snapshot.candidates).toHaveLength(1);
		expect(snapshot.candidates[0]).toMatchObject({
			id: nonSteamId,
			source: "non_steam",
			availability: {
				status: "reachable",
				reasons: [],
				label: "Available on this Deck",
			},
		});
		expect(flatpakProbeAttempts).toBe(2);
	});

	test("falls back to appStore install metadata when BIsAppInstalled is unavailable", async () => {
		backendCallHandler = async (method: unknown) => {
			if (method === BACK_END_API.GET_ASSOCIATION_CANDIDATES) {
				return [
					{ game: { id: "10", name: "Native Runtime Game" }, duration: 12 },
				];
			}
			if (method === BACK_END_API.RESOLVE_GAME_PAYLOADS) {
				return { results: [reachableResult()], error: null };
			}
			throw new Error(`unexpected write or read RPC: ${String(method)}`);
		};

		setRuntimeFixtures({
			appStore: {
				allApps: [
					{
						appid: 10,
						display_name: "Native Runtime Game",
						app_type: 0,
						installed: true,
					},
				],
			},
		});

		const snapshot = await refreshCurrentGamePresenceSnapshot({
			getAppDetails: async () => {
				return {
					status: "failure",
					reason: "missing-details",
				};
			},
		});

		expect(snapshot.candidates).toHaveLength(1);
		expect(snapshot.candidates[0]?.source).toBe("native_steam");
		expect(snapshot.candidates[0]?.inventory).toEqual({
			status: "current",
			reasons: [],
		});
		expect(snapshot.candidates[0]?.availability).toEqual({
			status: "reachable",
			reasons: [],
			label: "Installed",
		});
	});

	test("falls back to appStore per_client_data install metadata when direct probe is unavailable", async () => {
		backendCallHandler = async (method: unknown) => {
			if (method === BACK_END_API.GET_ASSOCIATION_CANDIDATES) {
				return [
					{ game: { id: "10", name: "Native Runtime Game" }, duration: 12 },
				];
			}
			if (method === BACK_END_API.RESOLVE_GAME_PAYLOADS) {
				return { results: [reachableResult()], error: null };
			}
			throw new Error(`unexpected write or read RPC: ${String(method)}`);
		};

		setRuntimeFixtures({
			appStore: {
				allApps: [
					{
						appid: 10,
						display_name: "Native Runtime Game",
						app_type: 0,
						per_client_data: [{ is_available_on_current_platform: true }],
					},
				],
			},
		});

		const reachableSnapshot = await refreshCurrentGamePresenceSnapshot({
			getAppDetails: async () => {
				return {
					status: "failure",
					reason: "missing-details",
				};
			},
		});

		expect(reachableSnapshot.candidates).toHaveLength(1);
		expect(reachableSnapshot.candidates[0]?.availability).toEqual({
			status: "reachable",
			reasons: [],
			label: "Installed",
		});

		setRuntimeFixtures({
			appStore: {
				allApps: [
					{
						appid: 10,
						display_name: "Native Runtime Game",
						app_type: 0,
						per_client_data: [{ is_available_on_current_platform: false }],
					},
				],
			},
		});

		const unreachableSnapshot = await refreshCurrentGamePresenceSnapshot({
			getAppDetails: async () => {
				return {
					status: "failure",
					reason: "missing-details",
				};
			},
		});

		expect(unreachableSnapshot.candidates).toHaveLength(1);
		expect(unreachableSnapshot.candidates[0]?.availability).toEqual({
			status: "unreachable",
			reasons: [{ code: "native_not_installed", source: "native_steam" }],
		});
	});

	test("bounds detail reads and does not write while refreshing caller-provided sources", async () => {
		let activeDetails = 0;
		let peakDetails = 0;
		let resolverCalls = 0;
		const refreshInput: GamePresenceBuildInput = {
			candidates: [
				{
					game: { id: "20", name: "Shortcut Game" },
					duration: 1,
					source: "non_steam",
				},
				{
					game: { id: "21", name: "Second Shortcut" },
					duration: 1,
					source: "non_steam",
				},
			],
			nonSteamInventory: {
				status: "complete",
				apps: [
					shortcutApp,
					{ ...shortcutApp, id: "21", name: "Second Shortcut" },
				],
			},
			nativeInventory: { status: "complete", apps: [] },
			runningAppIds: [],
			detailConcurrency: 1,
			getAppDetails: async () => {
				activeDetails++;
				peakDetails = Math.max(peakDetails, activeDetails);
				await Promise.resolve();
				activeDetails--;
				return detailsResult();
			},
			resolvePayloads: async (requests) => {
				resolverCalls++;
				return {
					results: requests.map(() => ({
						launcherKind: "direct",
						classificationStatus: "recognized",
						metadataStatus: "not_requested",
						payloadStatus: "reachable",
						payloadKind: "file",
						provenance: "direct_executable",
						reasonCode: null,
						payloadPath: null,
					})),
					error: null,
				};
			},
		};
		const snapshot = await build(refreshInput);
		const refreshed = await refreshGamePresenceSnapshot({
			...refreshInput,
			getCandidates: async () => refreshInput.candidates,
		});

		expect(snapshot.candidates).toHaveLength(2);
		expect(refreshed.candidates).toHaveLength(2);
		expect(peakDetails).toBe(1);
		expect(resolverCalls).toBe(2);
	});
});
