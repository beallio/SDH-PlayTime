import { afterEach, describe, expect, test } from "bun:test";
import getAppDetails, {
	getAppDetailsResult,
} from "@src/steam/utils/getAppDetails";

type TestAppDetailsRegistration = {
	unregister: () => void;
};

type TestSteamClient = {
	Apps?: {
		RegisterForAppDetails: (
			appId: number,
			callback: (details?: AppDetails) => void,
		) => TestAppDetailsRegistration;
	};
};

const steamGlobal = globalThis as unknown as {
	SteamClient?: TestSteamClient;
};

afterEach(() => {
	delete steamGlobal.SteamClient;
});

describe("getAppDetailsResult", () => {
	test("reports an unsupported Steam runtime without invoking a callback", async () => {
		await expect(getAppDetailsResult(1)).resolves.toEqual({
			status: "failure",
			reason: "unsupported-runtime",
		});
		await expect(getAppDetails(1)).resolves.toBeNull();
	});

	test("keeps a successful callback distinct from a missing callback payload", async () => {
		const details = {} as AppDetails;
		let unregisterCalls = 0;
		steamGlobal.SteamClient = {
			Apps: {
				RegisterForAppDetails: (_appId, callback) => {
					queueMicrotask(() => callback(details));
					return { unregister: () => unregisterCalls++ };
				},
			},
		};

		await expect(getAppDetailsResult(1)).resolves.toEqual({
			status: "success",
			details,
		});
		expect(unregisterCalls).toBe(1);

		steamGlobal.SteamClient.Apps = {
			RegisterForAppDetails: (_appId, callback) => {
				queueMicrotask(() => callback());
				return { unregister: () => undefined };
			},
		};

		await expect(getAppDetailsResult(1)).resolves.toEqual({
			status: "failure",
			reason: "missing-details",
		});
	});

	test("keeps registration and callback cleanup errors distinct", async () => {
		steamGlobal.SteamClient = {
			Apps: {
				RegisterForAppDetails: () => {
					throw new Error("registration failed");
				},
			},
		};

		await expect(getAppDetailsResult(1)).resolves.toEqual({
			status: "failure",
			reason: "registration-error",
		});

		steamGlobal.SteamClient.Apps = {
			RegisterForAppDetails: (_appId, callback) => {
				queueMicrotask(() => callback({} as AppDetails));
				return {
					unregister: () => {
						throw new Error("callback cleanup failed");
					},
				};
			},
		};

		await expect(getAppDetailsResult(1)).resolves.toEqual({
			status: "failure",
			reason: "callback-error",
		});
	});

	test("reports a timeout and preserves the nullable compatibility wrapper", async () => {
		let unregisterCalls = 0;
		steamGlobal.SteamClient = {
			Apps: {
				RegisterForAppDetails: () => ({
					unregister: () => unregisterCalls++,
				}),
			},
		};

		await expect(getAppDetailsResult(1, { timeoutMs: 1 })).resolves.toEqual({
			status: "failure",
			reason: "timeout",
		});
		expect(unregisterCalls).toBe(1);
		await expect(getAppDetails(1, { timeoutMs: 1 })).resolves.toBeNull();
	});
});
