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

describe("game checksum backend client", () => {
	beforeEach(() => {
		calls.length = 0;
		callHandler = async () => ({
			checksum: "payload-digest",
			status: "ready",
			reasonCode: null,
		});
	});

	test("sends bounded shortcut evidence to the checksum coordinator", async () => {
		const response = await Backend.getGameChecksum(request);

		expect(response).toEqual({
			checksum: "payload-digest",
			status: "ready",
			reasonCode: null,
		});
		expect(calls).toEqual([[BACK_END_API.GET_GAME_CHECKSUM, request]]);
	});

	test("does not retain the caller-path checksum RPC", () => {
		expect(Backend).not.toHaveProperty("getFileSHA256");
	});
});
