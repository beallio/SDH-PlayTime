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

	for (const executable of [
		"/home/deck/Games/NativeGame",
		"/home/deck/Games/Space Game.AppImage",
	]) {
		test(`sends safe direct candidates to the backend proof boundary: ${executable}`, async () => {
			setShortcutDetails({
				strShortcutExe: executable.includes(" ")
					? `"${executable}"`
					: executable,
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
						payloadPath: executable,
					},
				],
				error: null,
			});

			await expect(getPathToGame(1)).resolves.toBe(executable);
			expect(calls).toHaveLength(1);
		});
	}

	test("does not return a direct shortcut target when backend evidence rejects it", async () => {
		setShortcutDetails({
			strShortcutExe: '"/run/media/deck/SD Card/Games/Game.exe"',
		});
		callHandler = async () => ({
			results: [
				{
					launcherKind: "direct",
					classificationStatus: "recognized",
					metadataStatus: "not_requested",
					payloadStatus: "unknown",
					payloadKind: "unknown",
					provenance: "untrusted_hint",
					reasonCode: "unsupported",
					payloadPath: null,
				},
			],
			error: null,
		});

		await expect(getPathToGame(1)).resolves.toBeUndefined();
		expect(calls).toHaveLength(1);
	});

	test("does not return a shared Wine launcher to the checksum caller", async () => {
		setShortcutDetails({
			strShortcutExe: "/usr/bin/wine",
			strShortcutLaunchOptions: '"/home/deck/Games/Game.exe"',
		});

		await expect(getPathToGame(1)).resolves.toBeUndefined();
	});

	test("uses a backend-verified Heroic payload rather than the launcher", async () => {
		setShortcutDetails({
			strShortcutExe: "/opt/Heroic/heroic",
			strShortcutLaunchOptions:
				"heroic://launch?appName=normal-game&runner=legendary",
		});
		callHandler = async () => ({
			results: [
				{
					launcherKind: "heroic",
					classificationStatus: "recognized",
					metadataStatus: "resolved",
					payloadStatus: "reachable",
					payloadKind: "file",
					provenance: "heroic_metadata",
					reasonCode: null,
					payloadPath: "/home/deck/Games/Normal Game/Binaries/NormalGame.exe",
				},
			],
			error: null,
		});

		await expect(getPathToGame(1)).resolves.toBe(
			"/home/deck/Games/Normal Game/Binaries/NormalGame.exe",
		);
		expect(calls[0]?.[1]).toEqual([
			expect.objectContaining({
				launcherKind: "heroic",
				classificationStatus: "recognized",
			}),
		]);
	});

	test("returns undefined when a Flatpak launch command resolves to a directory payload", async () => {
		setShortcutDetails({
			strShortcutExe: "/usr/bin/flatpak",
			strShortcutLaunchOptions: "run org.example.some-game",
			strFlatpakAppID: "org.example.some-game",
		});
		callHandler = async () => ({
			results: [
				{
					launcherKind: "flatpak",
					classificationStatus: "recognized",
					metadataStatus: "not_requested",
					payloadStatus: "reachable",
					payloadKind: "directory",
					provenance: "untrusted_hint",
					reasonCode: null,
					payloadPath: "/home/deck/.var/app/org.example.some-game",
				},
			],
			error: null,
		});

		await expect(getPathToGame(1)).resolves.toBeUndefined();
		expect(calls[0]?.[1]).toEqual([
			expect.objectContaining({
				launcherKind: "flatpak",
				classificationStatus: "recognized",
			}),
		]);
	});

	for (const executable of [
		"/home/deck/.local/bin/UbisoftConnect-latest.exe",
		"/home/deck/.local/bin/DuckStation-master.exe",
	]) {
		test(`does not resolve a separator-suffixed shared tool: ${executable}`, async () => {
			setShortcutDetails({ strShortcutExe: executable });

			await expect(getPathToGame(1)).resolves.toBeUndefined();

			expect(calls).toHaveLength(0);
		});
	}

	test("never returns an unsupported EmuDeck ROM path to a checksum caller", async () => {
		setShortcutDetails({
			strShortcutExe: "/home/deck/Emulation/tools/launchers/retroarch.sh",
			strShortcutLaunchOptions: '"/home/deck/ROMs/Chrono Trigger.smc"',
		});

		await expect(getPathToGame(1)).resolves.toBeUndefined();
		expect(calls).toHaveLength(0);
	});
});
