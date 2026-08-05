import getAppDetails from "./getAppDetails";
import logger from "@src/utils/logger";

const FLATPAK_LAUNCHERS = {
	heroic: "com.heroicgameslauncher.hgl",
	lutris: "net.lutris.lutris",
	bottles: "com.usebottles.bottles",
} as const;

const SHARED_OR_LAUNCHER_BINARIES = new Set([
	"bottles",
	"bottles-cli",
	"flatpak",
	"heroic",
	"heroic.appimage",
	"lutris",
	"proton",
	"retroarch",
	"steam",
	"wine",
	"wine64",
]);

const WRAPPER_SUFFIXES = [".desktop", ".py", ".sh"];

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
	return decodeUriComponent(result);
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

function hasFlatpakLauncher(
	normalized: NormalizedShortcutFields,
	launcherId: string,
): boolean {
	const lowercaseLauncherId = launcherId.toLowerCase();
	return (
		normalized.flatpakAppId?.toLowerCase() === lowercaseLauncherId ||
		normalized.commandTokens.some(
			(token) => token.toLowerCase() === lowercaseLauncherId,
		)
	);
}

function isKnownLauncherBinary(path: string | undefined): boolean {
	const name = basename(path);
	if (!name) {
		return false;
	}
	return (
		SHARED_OR_LAUNCHER_BINARIES.has(name) ||
		name.includes("lutris-wrapper") ||
		name.includes("emulator") ||
		name.startsWith("dolphin") ||
		name.startsWith("pcsx2") ||
		name.startsWith("ppsspp")
	);
}

function isDirectPayload(path: string | undefined): path is string {
	if (!path?.startsWith("/") || isKnownLauncherBinary(path)) {
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

	return (
		lowercasePath.endsWith(".appimage") ||
		lowercasePath.endsWith(".exe") ||
		lowercasePath.endsWith(".x86") ||
		lowercasePath.endsWith(".x86_64") ||
		!basename(path)?.includes(".")
	);
}

function isEmudeckLauncher(path: string | undefined): boolean {
	if (!path) {
		return false;
	}
	return /\/emulation\/tools\/launchers\/[^/]+\.(?:sh|appimage)$/i.test(path);
}

function isRomPath(token: string): boolean {
	const lowercaseToken = token.toLowerCase();
	return (
		/^\/.+\.[a-z0-9]{1,10}$/i.test(token) &&
		!isKnownLauncherBinary(token) &&
		![
			".appimage",
			".dll",
			".dylib",
			".exe",
			".sh",
			".so",
			".x86",
			".x86_64",
		].some((suffix) => lowercaseToken.endsWith(suffix))
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
	return names.flatMap((name) =>
		url.searchParams.getAll(name).map((value) => decodeUriComponent(value)),
	);
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
	const heroicUrls = normalized.commandTokens
		.map(parseUrl)
		.filter(
			(url): url is URL => url?.protocol === "heroic:" && url.host === "launch",
		);
	const isHeroicLauncher =
		hasFlatpakLauncher(normalized, FLATPAK_LAUNCHERS.heroic) ||
		basename(executable)?.startsWith("heroic") ||
		heroicUrls.length > 0;

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
	const lutrisUrls = normalized.commandTokens
		.map(parseUrl)
		.filter((url): url is URL => url?.protocol === "lutris:");
	const isLutrisLauncher =
		hasFlatpakLauncher(normalized, FLATPAK_LAUNCHERS.lutris) ||
		basename(executable)?.startsWith("lutris") ||
		basename(executable)?.includes("lutris-wrapper") ||
		lutrisUrls.length > 0;

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
	const hasBottlesCommand = normalized.commandTokens.some(
		(token) => basename(token) === "bottles-cli",
	);
	const isBottlesLauncher =
		hasFlatpakLauncher(normalized, FLATPAK_LAUNCHERS.bottles) ||
		basename(executable) === "bottles-cli" ||
		hasBottlesCommand;

	if (!isBottlesLauncher) {
		return;
	}

	const commandIndex = normalized.commandTokens.findIndex(
		(token) => basename(token) === "bottles-cli",
	);
	const tokens =
		commandIndex >= 0
			? normalized.commandTokens.slice(commandIndex + 1)
			: normalized.launchOptionTokens;
	if (!tokens.includes("run")) {
		return ambiguous("bottles");
	}

	const bottle = uniqueValue(optionValues(tokens, ["-b", "--bottle"]));
	const program = uniqueValue(optionValues(tokens, ["-p", "--program"]));
	const name = uniqueValue(optionValues(tokens, ["--name"]));
	const id = uniqueValue(optionValues(tokens, ["--id", "--program-id"]));
	const executableValue = uniqueValue(
		optionValues(tokens, ["-e", "--executable"]),
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
	if (!isEmudeckLauncher(getExecutableToken(normalized))) {
		return;
	}

	const romPath = uniqueValue(
		normalized.commandTokens.filter((token) => isRomPath(token)),
	);
	if (romPath.isAmbiguous || !romPath.value) {
		return ambiguous("emudeck-srm");
	}

	return recognized("emudeck-srm", { romPath: romPath.value }, romPath.value);
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

	for (const parser of parsers) {
		const result = parser(normalized);
		if (result) {
			return { ...result, normalized };
		}
	}

	const directPayload = getExecutableToken(normalized);
	if (isDirectPayload(directPayload)) {
		return {
			...recognized("direct", {}, directPayload),
			normalized,
		};
	}

	return { ...unknown(), normalized };
}

// NOTE(ynhhoJ): https://github.com/0u73r-h34v3n/chrono-deck/blob/master/src/utils/steam/getPathToGameFileByLaunchCommand.ts
export default function getEmudeckPathToGame(launchCommand: string) {
	const evidence = classifyShortcutEvidence({ strShortcutExe: launchCommand });
	return evidence.launcherKind === "emudeck-srm"
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
