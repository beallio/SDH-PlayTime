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
	test("keeps a direct Windows shortcut target available to the checksum caller", async () => {
		setShortcutDetails({
			strShortcutExe: '"/run/media/deck/SD Card/Games/Game.exe"',
		});

		await expect(getPathToGame(1)).resolves.toBe(
			"/run/media/deck/SD Card/Games/Game.exe",
		);
	});

	test("does not return a shared Wine launcher to the checksum caller", async () => {
		setShortcutDetails({
			strShortcutExe: "/usr/bin/wine",
			strShortcutLaunchOptions: '"/home/deck/Games/Game.exe"',
		});

		await expect(getPathToGame(1)).resolves.toBeUndefined();
	});
});
