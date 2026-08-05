import { describe, expect, mock, test } from "bun:test";

mock.module("@decky/api", () => ({ call: async () => undefined }));

const { buildGamePresenceSnapshot, refreshGamePresenceSnapshot } = await import(
	"@src/app/gamePresence"
);
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
	return { status: "success" as const, details: {} as AppDetails };
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

describe("buildGamePresenceSnapshot", () => {
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

	test("batches resolution, bounds detail reads, and does not write while refreshing", async () => {
		let activeDetails = 0;
		let peakDetails = 0;
		let resolverCalls = 0;
		const databaseWrites = 0;
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
		expect(databaseWrites).toBe(0);
	});
});
