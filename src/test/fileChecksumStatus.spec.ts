import { describe, expect, test } from "bun:test";
import { getChecksumStatusPresentation } from "@src/pages/settings/checksums/status";

describe("checksum settings status", () => {
	test.each([
		["unsupported_shortcut", undefined, false, "Unsupported shortcut"],
		["missing_metadata", undefined, false, "Missing game metadata"],
		["payload_unavailable", undefined, false, "Game payload unavailable"],
		["hash_failure", undefined, false, "Checksum failed"],
		["ready", "digest", false, "Not saved"],
		["ready", "digest", true, "Saved"],
	] as const)("renders %s as %s", (status, checksum, saved, label) => {
		expect(
			getChecksumStatusPresentation(
				{ id: "1", name: "Game", checksum, status },
				saved,
			),
		).toMatchObject({ label });
	});
});
