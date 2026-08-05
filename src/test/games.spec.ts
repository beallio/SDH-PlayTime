import { afterEach, beforeEach, describe, expect, mock, test } from "bun:test";

mock.module("@decky/api", () => ({
	call: async () => undefined,
	toaster: { toast: () => {} },
	routerHook: { addPatch: () => {}, removePatch: () => {} },
}));

const { Backend } = await import("@src/app/backend");
const { countReadyChecksums, getNonSteamGamesChecksumFromDataBase } =
	await import("@src/app/games");
const { gameChecksums } = await import("@src/stores/games");

describe("getNonSteamGamesChecksumFromDataBase", () => {
	let originalGetGamesDictionary: typeof Backend.getGamesDictionary;

	beforeEach(() => {
		originalGetGamesDictionary = Backend.getGamesDictionary;
		gameChecksums.dataBase.clear();
		gameChecksums.nonSteam.clear();

		// @ts-expect-error Mocking global store
		globalThis.collectionStore = {
			deckDesktopApps: {
				apps: new Map([[123, {}]]),
			},
		};

		Backend.getGamesDictionary = async () => [
			{ game: { id: "00123", name: "Non-Steam Game" }, files: [] },
			{ game: { id: "456", name: "Steam Game" }, files: [] },
		];
	});

	afterEach(() => {
		Backend.getGamesDictionary = originalGetGamesDictionary;
		gameChecksums.dataBase.clear();
		gameChecksums.nonSteam.clear();
		// @ts-expect-error Removing mocked global store
		delete globalThis.collectionStore;
	});

	test("filters the dictionary by non-Steam numeric IDs", async () => {
		await getNonSteamGamesChecksumFromDataBase();

		expect(gameChecksums.dataBase.has("00123")).toBe(true);
		expect(gameChecksums.dataBase.has("456")).toBe(false);
	});

	test("counts only generated checksum results as successful hashes", () => {
		expect(
			countReadyChecksums([
				{ id: "1", name: "Ready", checksum: "digest", status: "ready" },
				{ id: "2", name: "Unsupported", status: "unsupported_shortcut" },
				{ id: "3", name: "Missing", status: "missing_metadata" },
				{ id: "4", name: "Unavailable", status: "payload_unavailable" },
				{ id: "5", name: "Failure", status: "hash_failure" },
				{ id: "6", name: "Empty", status: "ready" },
			]),
		).toBe(1);
	});
});
