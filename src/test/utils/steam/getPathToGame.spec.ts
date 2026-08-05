import { afterEach, beforeEach, describe, expect, mock, test } from "bun:test";

const calls: unknown[][] = [];
let callHandler: (...args: unknown[]) => Promise<unknown>;

mock.module("@decky/api", () => ({
	call: async (...args: unknown[]) => {
		calls.push(args);
		return await callHandler(...args);
	},
}));

const { getPathToGame } = await import("@src/steam/utils/GamePaths");

type TestSteamClient = {
	Apps: {
		RegisterForAppDetails: (
			appId: number,
			callback: (details: AppDetails) => void,
		) => { unregister: () => void };
	};
};

const steamGlobal = globalThis as unknown as {
	SteamClient?: TestSteamClient;
};

afterEach(() => {
	delete steamGlobal.SteamClient;
});

beforeEach(() => {
	calls.length = 0;
	callHandler = async () => ({ results: [], error: null });
});

function setShortcutDetails(shortcut: ShortcutEvidenceInput) {
	steamGlobal.SteamClient = {
		Apps: {
			RegisterForAppDetails: (_appId, callback) => {
				queueMicrotask(() => callback(shortcut as AppDetails));
				return { unregister: () => undefined };
			},
		},
	};
}

describe("getPathToGame compatibility", () => {
	test("uses a backend-verified regular direct payload before returning it", async () => {
		setShortcutDetails({
			strShortcutExe: '"/run/media/deck/SD Card/Games/Game.exe"',
		});
		callHandler = async () => ({
			results: [
				{
					launcherKind: "direct",
					classificationStatus: "recognized",
					metadataStatus: "not_requested",
					payloadStatus: "reachable",
					payloadKind: "file",
					provenance: "direct_executable",
					reasonCode: null,
					payloadPath: "/run/media/deck/SD Card/Games/Game.exe",
				},
			],
			error: null,
		});

		await expect(getPathToGame(1)).resolves.toBe(
			"/run/media/deck/SD Card/Games/Game.exe",
		);
		expect(calls).toHaveLength(1);
		expect(calls[0]?.[1]).toEqual([
			expect.objectContaining({
				launcherKind: "direct",
				classificationStatus: "recognized",
				metadataCandidates: [],
			}),
		]);
	});

	test("does not return a direct shortcut target when filesystem evidence reports a symlink", async () => {
		setShortcutDetails({
			strShortcutExe: '"/run/media/deck/SD Card/Games/Game.exe"',
		});

		await expect(
			getPathToGame(1, async () => ({
				isRegularFile: true,
				isSymbolicLink: true,
			})),
		).resolves.toBeUndefined();
	});

	test("does not return a shared Wine launcher to the checksum caller", async () => {
		setShortcutDetails({
			strShortcutExe: "/usr/bin/wine",
			strShortcutLaunchOptions: '"/home/deck/Games/Game.exe"',
		});

		await expect(getPathToGame(1)).resolves.toBeUndefined();
	});

	for (const executable of [
		"/home/deck/.local/bin/UbisoftConnect-latest.exe",
		"/home/deck/.local/bin/DuckStation-master.exe",
	]) {
		test(`does not resolve a separator-suffixed shared tool: ${executable}`, async () => {
			setShortcutDetails({ strShortcutExe: executable });
			let resolverCalled = false;

			await expect(
				getPathToGame(1, async () => {
					resolverCalled = true;
					return { isRegularFile: true, isSymbolicLink: false };
				}),
			).resolves.toBeUndefined();

			expect(resolverCalled).toBeFalse();
		});
	}
});
