import { describe, expect, test } from "bun:test";
import { classifyShortcutEvidence } from "@src/steam/utils/GamePaths";

interface ShortcutEvidenceFixture {
	id: string;
	source: {
		repository: string;
		commit: string;
		path: string;
	};
	input: ShortcutEvidenceInput;
	expected: {
		status: ShortcutClassificationStatus;
		launcherKind: ShortcutLauncherKind;
		payloadPath?: string;
		externalIdentityHints: ShortcutExternalIdentityHints;
	};
}

interface ShortcutEvidenceFixtureCorpus {
	schemaVersion: number;
	cases: ShortcutEvidenceFixture[];
}

const fixtureCorpus = (await Bun.file(
	new URL("../../fixtures/shortcut-evidence-cases.json", import.meta.url),
).json()) as ShortcutEvidenceFixtureCorpus;

describe("classifyShortcutEvidence", () => {
	test("keeps the reusable fixture corpus source-addressable", () => {
		expect(fixtureCorpus.schemaVersion).toBe(1);
		for (const fixture of fixtureCorpus.cases) {
			expect(fixture.source.repository).not.toBeEmpty();
			expect(fixture.source.commit).toMatch(/^[0-9a-f]{40}$/);
			expect(fixture.source.path).not.toBeEmpty();
		}
	});

	for (const fixture of fixtureCorpus.cases) {
		test(fixture.id, () => {
			const result = classifyShortcutEvidence(fixture.input);

			expect(result.status).toBe(fixture.expected.status);
			expect(result.launcherKind).toBe(fixture.expected.launcherKind);
			expect(result.externalIdentityHints).toEqual(
				fixture.expected.externalIdentityHints,
			);
			expect(result.payloadPath).toBe(fixture.expected.payloadPath);
		});
	}
});
