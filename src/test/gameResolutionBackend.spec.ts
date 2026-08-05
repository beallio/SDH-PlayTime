import { beforeEach, describe, expect, mock, test } from "bun:test";
import { BACK_END_API } from "@src/constants";

const calls: unknown[][] = [];
let callHandler: (...args: unknown[]) => Promise<unknown>;

mock.module("@decky/api", () => ({
	call: async (...args: unknown[]) => {
		calls.push(args);
		return await callHandler(...args);
	},
}));

const { Backend } = await import("@src/app/backend");

const request: GameResolutionRequest = {
	launcherKind: "direct",
	classificationStatus: "recognized",
	normalized: {
		flatpakAppId: undefined,
		shortcutExe: '"/run/media/deck/SD Card/Games/Game.AppImage"',
		shortcutLaunchOptions: undefined,
		shortcutStartDir: undefined,
		executableTokens: ["/run/media/deck/SD Card/Games/Game.AppImage"],
		launchOptionTokens: [],
		startDirTokens: [],
		commandTokens: ["/run/media/deck/SD Card/Games/Game.AppImage"],
	},
	metadataCandidates: [],
};

describe("game resolution backend client", () => {
	beforeEach(() => {
		calls.length = 0;
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
					payloadPath: "/run/media/deck/SD Card/Games/Game.AppImage",
				},
			],
			error: null,
		});
	});

	test("uses the bounded game-resolution RPC and preserves its structured response", async () => {
		const response = await Backend.resolveGamePayloads([request]);

		expect(response.results[0]?.payloadPath).toBe(
			"/run/media/deck/SD Card/Games/Game.AppImage",
		);
		expect(calls).toEqual([[BACK_END_API.RESOLVE_GAME_PAYLOADS, [request]]]);
	});
});
