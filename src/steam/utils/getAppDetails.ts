import logger from "@src/utils/logger";

const DEFAULT_TIMEOUT_MS = 300;

function getAppDetailsRegistration():
	| ((
			appId: number,
			callback: (appDetails?: AppDetails) => void,
	  ) => Unregisterable)
	| undefined {
	if (typeof SteamClient === "undefined") {
		return;
	}

	const registerForAppDetails = SteamClient.Apps?.RegisterForAppDetails;
	return typeof registerForAppDetails === "function"
		? registerForAppDetails.bind(SteamClient.Apps)
		: undefined;
}

/**
 * Retrieves app details while retaining the reason Steam could not provide them.
 * This only observes Steam's callback API; it does not retry, evaluate commands,
 * or infer installation state.
 */
export async function getAppDetailsResult(
	appId: number,
	{ timeoutMs = DEFAULT_TIMEOUT_MS }: GetAppDetailsOptions = {},
): Promise<AppDetailsResult> {
	const registerForAppDetails = getAppDetailsRegistration();
	if (!registerForAppDetails) {
		return { status: "failure", reason: "unsupported-runtime" };
	}

	return await new Promise((resolve) => {
		let settled = false;
		let registrationReady = false;
		let callbackReceived = false;
		let callbackDetails: AppDetails | undefined;
		let timeoutId: ReturnType<typeof setTimeout> | undefined;
		let unregister: (() => void) | undefined;

		const settle = (
			result: AppDetailsResult,
			cleanupFailureReason: Extract<
				AppDetailsFailureReason,
				"registration-error" | "callback-error"
			>,
		) => {
			if (settled) {
				return;
			}

			settled = true;
			if (timeoutId !== undefined) {
				clearTimeout(timeoutId);
			}

			try {
				unregister?.();
			} catch (error) {
				logger.debug("[utils][getAppDetails] Cleanup error: ", error);
				resolve({ status: "failure", reason: cleanupFailureReason });
				return;
			}

			resolve(result);
		};

		const resolveCallback = (details?: AppDetails) => {
			const result: AppDetailsResult = details
				? { status: "success", details }
				: { status: "failure", reason: "missing-details" };
			settle(result, "callback-error");
		};

		try {
			const registration = registerForAppDetails(appId, (details) => {
				if (!registrationReady) {
					callbackReceived = true;
					callbackDetails = details;
					return;
				}

				resolveCallback(details);
			});

			if (typeof registration?.unregister !== "function") {
				settle(
					{ status: "failure", reason: "registration-error" },
					"registration-error",
				);
				return;
			}

			unregister = registration.unregister;
			registrationReady = true;

			if (callbackReceived) {
				resolveCallback(callbackDetails);
				return;
			}

			timeoutId = setTimeout(() => {
				settle({ status: "failure", reason: "timeout" }, "registration-error");
			}, timeoutMs);
		} catch (error) {
			logger.debug("[utils][getAppDetails] Registration error: ", error);
			settle(
				{ status: "failure", reason: "registration-error" },
				"registration-error",
			);
		}
	});
}

/**
 * Compatibility wrapper for existing nullable callers.
 */
export default async function getAppDetails(
	appId: number,
	options?: GetAppDetailsOptions,
): Promise<AppDetails | null> {
	const result = await getAppDetailsResult(appId, options);
	return result.status === "success" ? result.details : null;
}
