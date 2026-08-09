import { describe, expect, test } from "bun:test";
import { GITHUB_URL, changelogUrlForVersion } from "@src/app/links";

describe("PlayTime links", () => {
	test("points at the remix repository", () => {
		expect(GITHUB_URL).toBe(
			"https://github.com/beallio/SDH-PlayTime-beallio-remix",
		);
		expect(GITHUB_URL).not.toContain("0u73r-h34v3n");
	});

	test("builds the release notes URL for the current build", () => {
		expect(changelogUrlForVersion("3.3.1-beallio.12")).toBe(
			"https://github.com/beallio/SDH-PlayTime-beallio-remix/releases/tag/v3.3.1-beallio.12",
		);
	});

	test("builds release notes URLs for other versions", () => {
		expect(changelogUrlForVersion("3.3.2")).toEndWith("/releases/tag/v3.3.2");
	});

	test("does not use a changelog file URL", () => {
		expect(changelogUrlForVersion("3.3.1-beallio.12")).not.toContain(
			"blob/master",
		);
	});
});
