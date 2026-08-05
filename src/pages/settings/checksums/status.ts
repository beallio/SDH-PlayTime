export type ChecksumStatusPresentation = {
	label: string;
	tone: "error" | "warning" | "success";
};

export function getChecksumStatusPresentation(
	game: LocalNonSteamGame,
	hasChecksumSaved: boolean,
): ChecksumStatusPresentation {
	switch (game.status) {
		case "unsupported_shortcut":
			return { label: "Unsupported shortcut", tone: "error" };
		case "missing_metadata":
			return { label: "Missing game metadata", tone: "error" };
		case "payload_unavailable":
			return { label: "Game payload unavailable", tone: "error" };
		case "hash_failure":
			return { label: "Checksum failed", tone: "error" };
		case "ready":
			return hasChecksumSaved
				? { label: "Saved", tone: "success" }
				: { label: "Not saved", tone: "warning" };
		default:
			return { label: "Checksum not generated", tone: "error" };
	}
}
