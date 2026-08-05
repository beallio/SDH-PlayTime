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

const request: GameChecksumRequest = { appId: 2_147_483_649 };

describe("game checksum backend client", () => {
	beforeEach(() => {
		calls.length = 0;
		callHandler = async () => ({
			checksum: "payload-digest",
			status: "ready",
			reasonCode: null,
		});
	});

	test("sends only a bounded Steam app ID to the checksum coordinator", async () => {
		const response = await Backend.getGameChecksum(request);

		expect(response).toEqual({
			checksum: "payload-digest",
			status: "ready",
			reasonCode: null,
		});
		expect(calls).toEqual([[BACK_END_API.GET_GAME_CHECKSUM, request]]);
	});

	test("removes the legacy caller-path API from request schemas", async () => {
		expect(Backend).not.toHaveProperty("getFileSHA256");
		const [typescriptSchema, pythonSchema, backendSource] = await Promise.all([
			Bun.file(
				new URL("../types/backend.request.d.ts", import.meta.url),
			).text(),
			Bun.file(
				new URL("../../py_modules/schemas/request.py", import.meta.url),
			).text(),
			Bun.file(new URL("../app/backend.ts", import.meta.url)).text(),
		]);

		for (const source of [typescriptSchema, pythonSchema, backendSource]) {
			expect(source).not.toContain("GetFileSHA256DTO");
			expect(source).not.toContain("getFileSHA256");
		}
	});
});
