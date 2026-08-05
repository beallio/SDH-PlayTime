import getAppDetails from "./getAppDetails";
import logger from "@src/utils/logger";

const FLATPAK_LAUNCHERS = {
	heroic: "com.heroicgameslauncher.hgl",
	lutris: "net.lutris.lutris",
	bottles: "com.usebottles.bottles",
} as const;

const SHARED_OR_LAUNCHER_BINARIES = new Set([
	"bottles",
	"bottles.appimage",
	"bottles-cli",
	"cartridges",
	"flatpak",
	"gamescope",
	"gamehub",
	"heroic",
	"heroic.appimage",
	"itch",
	"legendary",
	"lutris",
	"minigalaxy",
	"proton",
	"rpcs3",
	"rpcs3.appimage",
	"retroarch",
	"ryujinx",
	"ryujinx.appimage",
	"steam",
	"wine",
	"wine64",
]);

const WRAPPER_SUFFIXES = [".desktop", ".py", ".sh"];

const DIRECT_PAYLOAD_SUFFIXES = [".exe", ".x86", ".x86_64"];

const ROM_FILE_SUFFIXES = new Set([
	".3ds",
	".bin",
	".chd",
	".cso",
	".cue",
	".d64",
	".gba",
	".gb",
	".gbc",
	".gcm",
	".gen",
	".iso",
	".mdf",
	".n64",
	".nds",
	".nes",
	".pbp",
	".rvz",
	".sfc",
	".smc",
	".vpk",
	".wbfs",
	".wii",
	".xci",
	".z64",
]);

const EMUDECK_LAUNCHER_GRAMMARS = {
	"dolphin-emu.sh": {
		romOptions: ["-e"],
		flagOptions: ["-b"],
		positionalRom: false,
	},
	"mgba.sh": { romOptions: ["-f"], flagOptions: [], positionalRom: false },
	"pcsx2-qt.sh": {
		romOptions: [],
		flagOptions: ["-batch", "-fullscreen"],
		positionalRom: true,
	},
	"ppsspp.sh": {
		romOptions: ["-g"],
		flagOptions: ["-f"],
		positionalRom: false,
	},
	"retroarch.sh": { romOptions: [], flagOptions: [], positionalRom: true },
} as const;

const EMULATOR_OPTIONS_WITH_OPERANDS = new Set([
	"--bios",
	"--config",
	"--core",
	"--log-file",
	"--metadata",
	"--save",
	"--shader",
	"--state",
	"-L",
]);

interface ParsedTokens {
	tokens: string[];
	hasUnterminatedQuote: boolean;
}

interface UniqueValue {
	value?: string;
	isAmbiguous: boolean;
}

function normalizeText(value: string | null | undefined): string | undefined {
	const normalized = value?.trim();
	return normalized ? normalized : undefined;
}

function decodeUriComponent(value: string): string {
	try {
		return decodeURIComponent(value);
	} catch {
		return value;
	}
}

function stripNestedQuotes(value: string): string {
	let result = value.trim();
	while (
		result.length >= 2 &&
		((result.startsWith('"') && result.endsWith('"')) ||
			(result.startsWith("'") && result.endsWith("'")))
	) {
		result = result.slice(1, -1).trim();
	}
	return result;
}

/**
 * Splits a Steam shortcut field without invoking a shell. Backslashes only escape
 * quotes, whitespace, and other backslashes; every other backslash is preserved.
 */
function parseTokens(value: string | null | undefined): ParsedTokens {
	const input = normalizeText(value);
	if (!input) {
		return { tokens: [], hasUnterminatedQuote: false };
	}

	const tokens: string[] = [];
	let token = "";
	let quote: '"' | "'" | undefined;

	const pushToken = () => {
		const normalized = stripNestedQuotes(token);
		if (normalized) {
			tokens.push(normalized);
		}
		token = "";
	};

	for (let index = 0; index < input.length; index++) {
		const character = input[index];
		if (character === "\\") {
			const nextCharacter = input[index + 1];
			if (
				nextCharacter &&
				(nextCharacter === "\\" ||
					nextCharacter === '"' ||
					nextCharacter === "'" ||
					/\s/.test(nextCharacter))
			) {
				token += nextCharacter;
				index++;
			} else {
				token += character;
			}
			continue;
		}

		if (quote) {
			if (character === quote) {
				quote = undefined;
			} else {
				token += character;
			}
			continue;
		}

		if (character === '"' || character === "'") {
			quote = character;
			continue;
		}

		if (/\s/.test(character)) {
			pushToken();
			continue;
		}

		token += character;
	}

	pushToken();
	return { tokens, hasUnterminatedQuote: quote !== undefined };
}

export function normalizeShortcutEvidence(
	input: ShortcutEvidenceInput,
): NormalizedShortcutFields {
	const executable = parseTokens(input.strShortcutExe);
	const launchOptions = parseTokens(input.strShortcutLaunchOptions);
	const startDir = parseTokens(input.strShortcutStartDir);

	return {
		flatpakAppId: normalizeText(input.strFlatpakAppID),
		shortcutExe: normalizeText(input.strShortcutExe),
		shortcutLaunchOptions: normalizeText(input.strShortcutLaunchOptions),
		shortcutStartDir: normalizeText(input.strShortcutStartDir),
		executableTokens: executable.tokens,
		launchOptionTokens: launchOptions.tokens,
		startDirTokens: startDir.tokens,
		commandTokens: [...executable.tokens, ...launchOptions.tokens],
	};
}

function getExecutableToken(
	normalized: NormalizedShortcutFields,
): string | undefined {
	return normalized.executableTokens[0];
}

function basename(path: string | undefined): string | undefined {
	if (!path) {
		return;
	}
	return path.split(/[\\/]/).at(-1)?.toLowerCase();
}

function launcherStem(path: string | undefined): string | undefined {
	const name = basename(path);
	if (!name) {
		return;
	}

	return name
		.replace(/\.(?:appimage|exe|x86|x86_64)$/, "")
		.replace(/[-_]\d[\w.-]*$/, "");
}

function hasFlatpakLauncher(
	normalized: NormalizedShortcutFields,
	launcherId: string,
): boolean {
	const lowercaseLauncherId = launcherId.toLowerCase();
	return (
		basename(getExecutableToken(normalized)) === "flatpak" &&
		normalized.flatpakAppId?.toLowerCase() === lowercaseLauncherId &&
		normalized.launchOptionTokens[0] === "run" &&
		normalized.launchOptionTokens[1]?.toLowerCase() === lowercaseLauncherId
	);
}

function isHeroicExecutable(path: string | undefined): boolean {
	return launcherStem(path) === "heroic";
}

function isLutrisExecutable(path: string | undefined): boolean {
	const name = basename(path);
	return (
		launcherStem(path) === "lutris" || Boolean(name?.includes("lutris-wrapper"))
	);
}

function isBottlesExecutable(path: string | undefined): boolean {
	return basename(path) === "bottles-cli";
}

function isKnownLauncherBinary(path: string | undefined): boolean {
	const name = basename(path);
	const stem = launcherStem(path);
	if (!name) {
		return false;
	}
	return (
		SHARED_OR_LAUNCHER_BINARIES.has(name) ||
		SHARED_OR_LAUNCHER_BINARIES.has(stem ?? "") ||
		stem === "cemu" ||
		stem === "duckstation" ||
		name.includes("launcher") ||
		name.includes("lutris-wrapper") ||
		name.includes("emulator") ||
		name.startsWith("dolphin") ||
		name.startsWith("pcsx2") ||
		name.startsWith("ppsspp")
	);
}

function hasUnresolvedShellExpression(path: string): boolean {
	return path.includes("$") || path.includes("`");
}

function isLiteralDirectExecutableToken(path: string): boolean {
	return (
		!hasUnresolvedShellExpression(path) &&
		!/%[a-z][a-z0-9_]*%/i.test(path) &&
		!/[?*\[\]{}|&;<>]/.test(path)
	);
}

function isDirectPayload(path: string | undefined): path is string {
	if (
		!path?.startsWith("/") ||
		isKnownLauncherBinary(path) ||
		!isLiteralDirectExecutableToken(path)
	) {
		return false;
	}

	const lowercasePath = path.toLowerCase();
	if (
		/^\/(?:app\/bin|bin|sbin|usr\/(?:local\/)?bin)\//.test(lowercasePath) ||
		lowercasePath.includes("/emulation/tools/launchers/") ||
		lowercasePath.includes("/proton ") ||
		lowercasePath.includes("/steam/steamapps/common/proton") ||
		WRAPPER_SUFFIXES.some((suffix) => lowercasePath.endsWith(suffix))
	) {
		return false;
	}

	return DIRECT_PAYLOAD_SUFFIXES.some((suffix) =>
		lowercasePath.endsWith(suffix),
	);
}

function getEmudeckLauncherGrammar(path: string | undefined) {
	if (!path || !/\/emulation\/tools\/launchers\//i.test(path)) {
		return;
	}
	const launcherName = basename(path);
	return launcherName
		? EMUDECK_LAUNCHER_GRAMMARS[
				launcherName as keyof typeof EMUDECK_LAUNCHER_GRAMMARS
			]
		: undefined;
}

function isRomPath(token: string): boolean {
	const lowercaseToken = token.toLowerCase();
	return (
		token.startsWith("/") &&
		!hasUnresolvedShellExpression(token) &&
		!isKnownLauncherBinary(token) &&
		[...ROM_FILE_SUFFIXES].some((suffix) => lowercaseToken.endsWith(suffix))
	);
}

function uniqueValue(values: Array<string | undefined>): UniqueValue {
	const unique = [
		...new Set(values.filter((value): value is string => Boolean(value))),
	];
	return {
		value: unique.length === 1 ? unique[0] : undefined,
		isAmbiguous: unique.length > 1,
	};
}

function parseUrl(token: string): URL | undefined {
	try {
		return new URL(token);
	} catch {
		return;
	}
}

function getUrlValues(url: URL, names: string[]): string[] {
	return names.flatMap((name) => url.searchParams.getAll(name));
}

function recognized(
	launcherKind: ShortcutLauncherKind,
	externalIdentityHints: ShortcutExternalIdentityHints = {},
	payloadPath?: string,
): ShortcutEvidenceClassification {
	return {
		status: "recognized",
		launcherKind,
		normalized: {} as NormalizedShortcutFields,
		externalIdentityHints,
		payloadPath,
	};
}

function ambiguous(
	launcherKind: Exclude<ShortcutLauncherKind, "unknown">,
	externalIdentityHints: ShortcutExternalIdentityHints = {},
): ShortcutEvidenceClassification {
	return {
		status: "ambiguous",
		launcherKind,
		normalized: {} as NormalizedShortcutFields,
		externalIdentityHints,
	};
}

function unknown(): ShortcutEvidenceClassification {
	return {
		status: "unknown",
		launcherKind: "unknown",
		normalized: {} as NormalizedShortcutFields,
		externalIdentityHints: {},
	};
}

function classifyHeroic(
	normalized: NormalizedShortcutFields,
): ShortcutEvidenceClassification | undefined {
	const executable = getExecutableToken(normalized);
	const heroicUrls = normalized.launchOptionTokens
		.map(parseUrl)
		.filter(
			(url): url is URL => url?.protocol === "heroic:" && url.host === "launch",
		);
	const isHeroicLauncher =
		hasFlatpakLauncher(normalized, FLATPAK_LAUNCHERS.heroic) ||
		isHeroicExecutable(executable);

	if (!isHeroicLauncher) {
		return;
	}

	const appNames: string[] = [];
	const runners: string[] = [];
	const alternateExecutables: string[] = [];
	let invalidPath = false;

	for (const url of heroicUrls) {
		appNames.push(...getUrlValues(url, ["appName", "appId", "appID"]));
		runners.push(...getUrlValues(url, ["runner"]));
		alternateExecutables.push(...getUrlValues(url, ["altExe"]));

		const segments = url.pathname.split("/").filter(Boolean);
		if (segments.length === 1) {
			appNames.push(decodeUriComponent(segments[0]));
		} else if (segments.length === 2) {
			runners.push(decodeUriComponent(segments[0]));
			appNames.push(decodeUriComponent(segments[1]));
		} else if (segments.length > 2) {
			invalidPath = true;
		}
	}

	const appName = uniqueValue(appNames);
	const runner = uniqueValue(runners);
	const altExe = uniqueValue(alternateExecutables);
	if (
		invalidPath ||
		appName.isAmbiguous ||
		runner.isAmbiguous ||
		altExe.isAmbiguous ||
		!appName.value
	) {
		return ambiguous("heroic");
	}

	return recognized("heroic", {
		heroicAppName: appName.value,
		...(runner.value ? { heroicRunner: runner.value } : {}),
		...(altExe.value ? { heroicAltExe: altExe.value } : {}),
	});
}

function classifyLutris(
	normalized: NormalizedShortcutFields,
): ShortcutEvidenceClassification | undefined {
	const executable = getExecutableToken(normalized);
	const lutrisUrls = normalized.launchOptionTokens
		.map(parseUrl)
		.filter((url): url is URL => url?.protocol === "lutris:");
	const isLutrisLauncher =
		hasFlatpakLauncher(normalized, FLATPAK_LAUNCHERS.lutris) ||
		isLutrisExecutable(executable);

	if (!isLutrisLauncher) {
		return;
	}

	const gameIds: string[] = [];
	const gameSlugs: string[] = [];
	let invalidPath = false;
	for (const url of lutrisUrls) {
		const segments = url.pathname.split("/").filter(Boolean);
		const action = url.host || segments.shift();
		if (segments.length !== 1) {
			invalidPath = true;
			continue;
		}

		if (action === "rungameid" && /^\d+$/.test(segments[0])) {
			gameIds.push(segments[0]);
		} else if (action === "rungame" && segments[0]) {
			gameSlugs.push(decodeUriComponent(segments[0]));
		} else {
			invalidPath = true;
		}
	}

	const gameId = uniqueValue(gameIds);
	const gameSlug = uniqueValue(gameSlugs);
	if (
		invalidPath ||
		gameId.isAmbiguous ||
		gameSlug.isAmbiguous ||
		(gameId.value && gameSlug.value) ||
		(!gameId.value && !gameSlug.value)
	) {
		return ambiguous("lutris");
	}

	return recognized("lutris", {
		...(gameId.value ? { lutrisGameId: gameId.value } : {}),
		...(gameSlug.value ? { lutrisGameSlug: gameSlug.value } : {}),
	});
}

function optionValues(tokens: string[], aliases: string[]): string[] {
	const values: string[] = [];
	for (let index = 0; index < tokens.length; index++) {
		const token = tokens[index];
		if (token === "--") {
			break;
		}
		for (const alias of aliases) {
			if (token === alias && tokens[index + 1] && tokens[index + 1] !== "--") {
				values.push(tokens[index + 1]);
				index++;
				break;
			}
			if (token.startsWith(`${alias}=`)) {
				const value = stripNestedQuotes(token.slice(alias.length + 1));
				if (value) {
					values.push(value);
				}
				break;
			}
		}
	}
	return values;
}

function classifyBottles(
	normalized: NormalizedShortcutFields,
): ShortcutEvidenceClassification | undefined {
	const executable = getExecutableToken(normalized);
	const isBottlesLauncher =
		hasFlatpakLauncher(normalized, FLATPAK_LAUNCHERS.bottles) ||
		isBottlesExecutable(executable);

	if (!isBottlesLauncher) {
		return;
	}

	const tokens = isBottlesExecutable(executable)
		? normalized.launchOptionTokens
		: normalized.launchOptionTokens.slice(2);
	if (tokens[0] !== "bottles-cli" && !isBottlesExecutable(executable)) {
		return ambiguous("bottles");
	}
	const runTokens = isBottlesExecutable(executable) ? tokens : tokens.slice(1);
	if (runTokens[0] !== "run") {
		return ambiguous("bottles");
	}
	const options = runTokens.slice(1);

	const bottle = uniqueValue(optionValues(options, ["-b", "--bottle"]));
	const program = uniqueValue(optionValues(options, ["-p", "--program"]));
	const name = uniqueValue(optionValues(options, ["--name"]));
	const id = uniqueValue(optionValues(options, ["--id", "--program-id"]));
	const executableValue = uniqueValue(
		optionValues(options, ["-e", "--executable"]),
	);
	const identityHints = [
		program.value,
		name.value,
		id.value,
		executableValue.value,
	].filter((value): value is string => Boolean(value));

	if (
		bottle.isAmbiguous ||
		program.isAmbiguous ||
		name.isAmbiguous ||
		id.isAmbiguous ||
		executableValue.isAmbiguous ||
		!bottle.value ||
		identityHints.length !== 1
	) {
		return ambiguous(
			"bottles",
			bottle.value ? { bottlesBottle: bottle.value } : {},
		);
	}

	return recognized("bottles", {
		bottlesBottle: bottle.value,
		...(program.value ? { bottlesProgram: program.value } : {}),
		...(name.value ? { bottlesName: name.value } : {}),
		...(id.value ? { bottlesId: id.value } : {}),
		...(executableValue.value
			? { bottlesExecutable: executableValue.value }
			: {}),
	});
}

function classifyEmudeck(
	normalized: NormalizedShortcutFields,
): ShortcutEvidenceClassification | undefined {
	const grammar = getEmudeckLauncherGrammar(getExecutableToken(normalized));
	if (!grammar) {
		return;
	}

	const romCandidates: string[] = [];
	const tokens = normalized.launchOptionTokens;
	for (let index = 0; index < tokens.length; index++) {
		const token = tokens[index];
		if (token === "--") {
			break;
		}

		if (grammar.romOptions.includes(token as never)) {
			const candidate = tokens[index + 1];
			if (candidate && isRomPath(candidate)) {
				romCandidates.push(candidate);
			}
			index++;
			continue;
		}

		if (EMULATOR_OPTIONS_WITH_OPERANDS.has(token)) {
			index++;
			continue;
		}

		if (token.startsWith("-")) {
			if (grammar.flagOptions.includes(token as never)) {
				continue;
			}
			return ambiguous("emudeck-srm");
		}

		if (grammar.positionalRom && isRomPath(token)) {
			romCandidates.push(token);
		}
	}

	const romPath = uniqueValue(romCandidates);
	if (romPath.isAmbiguous || !romPath.value) {
		return ambiguous("emudeck-srm");
	}

	return recognized("emudeck-srm", { romPath: romPath.value }, romPath.value);
}

function launcherAnchors(
	normalized: NormalizedShortcutFields,
): Exclude<ShortcutLauncherKind, "direct" | "emudeck-srm" | "unknown">[] {
	const executable = getExecutableToken(normalized);
	const anchors: Exclude<
		ShortcutLauncherKind,
		"direct" | "emudeck-srm" | "unknown"
	>[] = [];
	if (
		isHeroicExecutable(executable) ||
		hasFlatpakLauncher(normalized, FLATPAK_LAUNCHERS.heroic)
	) {
		anchors.push("heroic");
	}
	if (
		isLutrisExecutable(executable) ||
		hasFlatpakLauncher(normalized, FLATPAK_LAUNCHERS.lutris)
	) {
		anchors.push("lutris");
	}
	if (
		isBottlesExecutable(executable) ||
		hasFlatpakLauncher(normalized, FLATPAK_LAUNCHERS.bottles)
	) {
		anchors.push("bottles");
	}
	return anchors;
}

function launcherProtocols(
	normalized: NormalizedShortcutFields,
): Array<"heroic" | "lutris"> {
	const protocols = new Set<"heroic" | "lutris">();
	for (const token of normalized.commandTokens) {
		const url = parseUrl(token);
		if (url?.protocol === "heroic:" && url.host === "launch") {
			protocols.add("heroic");
		}
		if (url?.protocol === "lutris:") {
			protocols.add("lutris");
		}
	}
	return [...protocols];
}

/**
 * Classifies untrusted Steam shortcut evidence. The result never reports a known
 * launcher, wrapper, emulator, Flatpak, Wine, or Proton binary as a game payload.
 */
export function classifyShortcutEvidence(
	input: ShortcutEvidenceInput,
): ShortcutEvidenceClassification {
	const normalized = normalizeShortcutEvidence(input);
	const parsers = [
		classifyHeroic,
		classifyLutris,
		classifyBottles,
		classifyEmudeck,
	];
	const hasUnterminatedQuote = [
		input.strShortcutExe,
		input.strShortcutLaunchOptions,
		input.strShortcutStartDir,
	].some((value) => parseTokens(value).hasUnterminatedQuote);

	if (hasUnterminatedQuote) {
		return { ...unknown(), normalized };
	}

	const anchors = launcherAnchors(normalized);
	const protocols = launcherProtocols(normalized);
	if (anchors.length > 1 || protocols.length > 1) {
		return {
			...ambiguous(anchors[0] ?? protocols[0] ?? "heroic"),
			normalized,
		};
	}
	if (protocols.some((protocol) => !anchors.includes(protocol))) {
		return anchors[0]
			? { ...ambiguous(anchors[0]), normalized }
			: { ...unknown(), normalized };
	}

	for (const parser of parsers) {
		const result = parser(normalized);
		if (result) {
			return { ...result, normalized };
		}
	}

	const directPayload = getExecutableToken(normalized);
	if (
		normalized.executableTokens.length === 1 &&
		isDirectPayload(directPayload)
	) {
		return {
			...recognized("direct", {}, directPayload),
			normalized,
		};
	}

	return { ...unknown(), normalized };
}

// NOTE(ynhhoJ): https://github.com/0u73r-h34v3n/chrono-deck/blob/master/src/utils/steam/getPathToGameFileByLaunchCommand.ts
export default function getEmudeckPathToGame(launchCommand: string) {
	const normalized = normalizeShortcutEvidence({
		strShortcutExe: launchCommand,
	});
	if (parseTokens(launchCommand).hasUnterminatedQuote) {
		return;
	}
	const [executable, ...launchOptionTokens] = normalized.executableTokens;
	const evidence = classifyEmudeck({
		...normalized,
		executableTokens: executable ? [executable] : [],
		launchOptionTokens,
		commandTokens: executable ? [executable, ...launchOptionTokens] : [],
	});
	return evidence?.launcherKind === "emudeck-srm"
		? evidence.payloadPath
		: undefined;
}

export async function getPathToGame(applicationId: number) {
	const appDetails = await getAppDetails(applicationId);
	if (!appDetails) {
		return;
	}

	const evidence = classifyShortcutEvidence(appDetails);
	if (!evidence.payloadPath) {
		logger.error("Unsupported pathToGame:", {
			strShortcutExe: appDetails.strShortcutExe,
			strShortcutLaunchOptions: appDetails.strShortcutLaunchOptions,
		});
	}

	return evidence.payloadPath;
}
