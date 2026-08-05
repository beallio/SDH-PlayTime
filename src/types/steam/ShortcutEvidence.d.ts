type ShortcutLauncherKind =
	| "direct"
	| "heroic"
	| "lutris"
	| "bottles"
	| "emudeck-srm"
	| "unknown";

type ShortcutClassificationStatus = "recognized" | "unknown" | "ambiguous";

interface ShortcutEvidenceInput {
	strFlatpakAppID?: string | null;
	strShortcutExe?: string | null;
	strShortcutLaunchOptions?: string | null;
	strShortcutStartDir?: string | null;
}

interface NormalizedShortcutFields {
	flatpakAppId?: string;
	shortcutExe?: string;
	shortcutLaunchOptions?: string;
	shortcutStartDir?: string;
	executableTokens: string[];
	launchOptionTokens: string[];
	startDirTokens: string[];
	commandTokens: string[];
}

interface ShortcutExternalIdentityHints {
	heroicAppName?: string;
	heroicRunner?: string;
	heroicAltExe?: string;
	lutrisGameId?: string;
	lutrisGameSlug?: string;
	bottlesBottle?: string;
	bottlesProgram?: string;
	bottlesName?: string;
	bottlesId?: string;
	bottlesExecutable?: string;
	romPath?: string;
}

interface ShortcutEvidenceClassification {
	status: ShortcutClassificationStatus;
	launcherKind: ShortcutLauncherKind;
	normalized: NormalizedShortcutFields;
	externalIdentityHints: ShortcutExternalIdentityHints;
	payloadPath?: string;
}

interface DirectPayloadFilesystemEvidence {
	isRegularFile: boolean;
	isSymbolicLink: boolean;
}

type DirectPayloadResolver = (
	candidatePath: string,
) =>
	| DirectPayloadFilesystemEvidence
	| undefined
	| Promise<DirectPayloadFilesystemEvidence | undefined>;

type AppDetailsFailureReason =
	| "unsupported-runtime"
	| "registration-error"
	| "callback-error"
	| "missing-details"
	| "timeout";

type AppDetailsResult =
	| {
			status: "success";
			details: AppDetails;
	  }
	| {
			status: "failure";
			reason: AppDetailsFailureReason;
	  };

interface GetAppDetailsOptions {
	timeoutMs?: number;
}
