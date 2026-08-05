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

type GameResolutionLauncherKind = ShortcutLauncherKind;

type GameResolutionClassificationStatus = ShortcutClassificationStatus;

type GameResolutionNormalizedShortcutEvidence = NormalizedShortcutFields;

type GameResolutionMetadataStatus =
	| "not_requested"
	| "not_found"
	| "resolved"
	| "invalid";

type GameResolutionPayloadStatus = "reachable" | "unreachable" | "unknown";

type GameResolutionPayloadKind = "file" | "directory" | "unknown";

type GameResolutionProvenance =
	| "direct_executable"
	| "heroic_metadata"
	| "untrusted_hint"
	| "none";

type GameResolutionReasonCode =
	| "missing"
	| "ambiguous"
	| "unsupported"
	| "permission_denied"
	| "malformed"
	| "drive_disconnected"
	| "payload_missing"
	| "kind_mismatch"
	| "probe_failure"
	| "timeout";

interface GameResolutionRequest {
	launcherKind: GameResolutionLauncherKind;
	classificationStatus: GameResolutionClassificationStatus;
	normalized: GameResolutionNormalizedShortcutEvidence;
	metadataCandidates: string[];
}

interface GameResolutionResult {
	launcherKind: GameResolutionLauncherKind;
	classificationStatus: GameResolutionClassificationStatus;
	metadataStatus: GameResolutionMetadataStatus;
	payloadStatus: GameResolutionPayloadStatus;
	payloadKind: GameResolutionPayloadKind;
	provenance: GameResolutionProvenance;
	reasonCode: GameResolutionReasonCode | null;
	payloadPath: string | null;
}

interface GameResolutionBatchResponse {
	results: GameResolutionResult[];
	error: GameResolutionReasonCode | null;
}

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
