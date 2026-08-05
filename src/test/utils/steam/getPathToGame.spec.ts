import { afterEach, describe, expect, test } from "bun:test";
import { getPathToGame } from "@src/steam/utils/GamePaths";

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
	test("requires injected regular-file evidence before returning a direct target", async () => {
		setShortcutDetails({
			strShortcutExe: '"/run/media/deck/SD Card/Games/Game.exe"',
		});

		await expect(getPathToGame(1)).resolves.toBeUndefined();

		await expect(
			getPathToGame(1, async (candidatePath) => {
				expect(candidatePath).toBe("/run/media/deck/SD Card/Games/Game.exe");
				return { isRegularFile: true, isSymbolicLink: false };
			}),
		).resolves.toBe("/run/media/deck/SD Card/Games/Game.exe");
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
