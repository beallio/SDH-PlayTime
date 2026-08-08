import { describe, expect, mock, test } from "bun:test";

mock.module("@decky/api", () => ({
	call: async () => undefined,
}));

const { classifyShortcutEvidence, heroicLaunchSegments } = await import(
	"@src/steam/utils/GamePaths"
);

const SPECIAL_SCHEMES = new Set([
	"http:",
	"https:",
	"ws:",
	"wss:",
	"ftp:",
	"file:",
]);

class DeckUrl extends URL {
	get host(): string {
		return SPECIAL_SCHEMES.has(this.protocol) ? super.host : "";
	}

	get hostname(): string {
		return SPECIAL_SCHEMES.has(this.protocol) ? super.hostname : "";
	}

	get pathname(): string {
		if (SPECIAL_SCHEMES.has(this.protocol) || !super.host) {
			return super.pathname;
		}
		return `//${super.host}${super.pathname}`;
	}
}

function withDeckUrlParsing<T>(run: () => T): T {
	const realUrl = globalThis.URL;
	globalThis.URL = DeckUrl as unknown as typeof URL;
	try {
		return run();
	} finally {
		globalThis.URL = realUrl;
	}
}

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
	test("DeckUrl reproduces Steam Deck CEF parsing of heroic URIs", () => {
		const parsed = new DeckUrl(
			"heroic://launch?appName=4YuV2WARPPBTcq2Aatubw1&runner=sideload",
		);
		expect(parsed.protocol).toBe("heroic:");
		expect(parsed.host).toBe("");
		expect(parsed.pathname).toBe("//launch");
		expect(parsed.searchParams.get("appName")).toBe("4YuV2WARPPBTcq2Aatubw1");
	});

	test("recognizes a Heroic flatpak shortcut under Deck URL parsing", () => {
		const evidence = withDeckUrlParsing(() =>
			classifyShortcutEvidence({
				strShortcutExe: '"flatpak"',
				strShortcutLaunchOptions:
					'run com.heroicgameslauncher.hgl --no-gui --no-sandbox "heroic://launch?appName=4YuV2WARPPBTcq2Aatubw1&runner=sideload"',
				strShortcutStartDir: '"/usr/bin"',
				strFlatpakAppID: "",
			} as ShortcutEvidenceInput),
		);

		expect(evidence.status).toBe("recognized");
		expect(evidence.launcherKind).toBe("heroic");
		expect(evidence.externalIdentityHints).toEqual({
			heroicAppName: "4YuV2WARPPBTcq2Aatubw1",
			heroicRunner: "sideload",
		});
	});

	test("heroicLaunchSegments accepts the host-shaped launch URI", () => {
		expect(
			heroicLaunchSegments({
				protocol: "heroic:",
				host: "launch",
				pathname: "",
			}),
		).toEqual([]);
	});

	test("heroicLaunchSegments accepts the Deck-shaped launch URI", () => {
		expect(
			heroicLaunchSegments({
				protocol: "heroic:",
				host: "",
				pathname: "//launch",
			}),
		).toEqual([]);
	});

	test("heroicLaunchSegments parses host-shaped path segments", () => {
		expect(
			heroicLaunchSegments({
				protocol: "heroic:",
				host: "launch",
				pathname: "/legendary/GameId",
			}),
		).toEqual(["legendary", "GameId"]);
	});

	test("heroicLaunchSegments parses Deck-shaped path segments", () => {
		expect(
			heroicLaunchSegments({
				protocol: "heroic:",
				host: "",
				pathname: "//launch/legendary/GameId",
			}),
		).toEqual(["legendary", "GameId"]);
	});

	test("heroicLaunchSegments rejects a non-launch Heroic action", () => {
		expect(
			heroicLaunchSegments({
				protocol: "heroic:",
				host: "install",
				pathname: "",
			}),
		).toBeUndefined();
	});

	test("heroicLaunchSegments rejects a Deck-shaped non-launch action", () => {
		expect(
			heroicLaunchSegments({
				protocol: "heroic:",
				host: "",
				pathname: "//install",
			}),
		).toBeUndefined();
	});

	test("heroicLaunchSegments rejects Lutris URIs", () => {
		expect(
			heroicLaunchSegments({
				protocol: "lutris:",
				host: "rungameid",
				pathname: "/1",
			}),
		).toBeUndefined();
	});

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
