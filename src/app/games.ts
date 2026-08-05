import { toaster } from "@decky/api";
import { getGameChecksumRequest } from "@src/steam/utils/GamePaths";
import {
	$gameChecksumsLoadingState,
	$generatingChecksumForAppWithIndex,
	$isGeneratingChecksumForGames,
	$isLoadingChecksumFromDataBase,
	$nonSteamAppsCount,
	gameChecksums,
} from "@src/stores/games";
import { isNil } from "es-toolkit";
import logger from "@src/utils/logger";
import { Backend } from "./backend";
import { APP_TYPE } from "@src/constants";
import { $toggleUpdateInListeningComponents } from "@src/stores/ui";

export function getAllNonSteamAppIds() {
	if (isNil(collectionStore.deckDesktopApps)) {
		return appStore.allApps
			.filter((item) => item.app_type === APP_TYPE.THIRD_PARTY)
			.map((item) => Number.parseInt(item.gameid, 10));
	}

	return Array.from(collectionStore.deckDesktopApps.apps.keys());
}

export async function getFileSHA256(applicationId: number) {
	try {
		const shortcutEvidence = await getGameChecksumRequest(applicationId);
		const { display_name: displayName } =
			appStore.GetAppOverviewByAppID(applicationId);

		if (isNil(shortcutEvidence)) {
			logger.debug(
				"[getFileSHA256] unsupported shortcut evidence. App ID: ",
				applicationId,
			);

			return {
				id: `${applicationId}`,
				name: displayName,
				status: "unsupported_shortcut" as const,
			};
		}

		const result = await Backend.getGameChecksum(shortcutEvidence);

		return {
			id: `${applicationId}`,
			name: displayName,
			checksum: result.checksum ?? undefined,
			status: result.status,
		};
	} catch (error) {
		logger.error(error);

		return undefined;
	}
}

function checksumFailureMessage(status: GameChecksumStatus) {
	switch (status) {
		case "unsupported_shortcut":
			return "This shortcut is not supported for checksum detection.";
		case "missing_metadata":
			return "Game metadata needed for checksum detection is unavailable.";
		case "payload_unavailable":
			return "The game payload is unavailable for checksum detection.";
		case "hash_failure":
			return "An error happened while generating file checksum.";
		case "ready":
			return "File checksum is undefined.";
	}
}

export async function getNonSteamGamesChecksumFromDataBase() {
	$isLoadingChecksumFromDataBase.set(true);

	return await Backend.getGamesDictionary()
		.then((response) => {
			if (isNil(response)) {
				return;
			}

			const nonSteamKeys = new Set(getAllNonSteamAppIds());
			const onlyNonSteamGames = response
				.filter((game) => nonSteamKeys.has(Number.parseInt(game.game.id, 10)))
				.sort((a, b) => a.game.name.localeCompare(b.game.name))
				.map((item) => ({
					...item,
					...gameChecksums.nonSteam.get(item.game.id),
				}));

			for (const nonSteamGame of onlyNonSteamGames) {
				gameChecksums.dataBase.set(nonSteamGame.game.id, nonSteamGame);
			}
		})
		.finally(() => {
			$isLoadingChecksumFromDataBase.set(false);
		});
}

export async function getCurrentNonSteamGamesChecksum(
	allNonSteamAppIds: Array<number>,
) {
	if (gameChecksums.nonSteam.size !== 0) {
		return;
	}

	$isGeneratingChecksumForGames.set(true);

	for (const [index, applicationId] of allNonSteamAppIds.entries()) {
		$generatingChecksumForAppWithIndex.set(index);

		await getFileSHA256(applicationId).then((response) => {
			if (isNil(response)) {
				return;
			}

			gameChecksums.nonSteam.set(`${applicationId}`, response);
		});
	}

	$isGeneratingChecksumForGames.set(false);
}

export async function findGameWithSameChecksum(appId: number) {
	const fileSHA256 = await getFileSHA256(appId);

	const array = [...gameChecksums.dataBase].map((item) => item[1]);

	const gameWithSameSHA256 = array.find((item) =>
		item.files.find((checksum) => checksum.checksum === fileSHA256?.checksum),
	);

	return gameWithSameSHA256;
}

export async function initializeGameDetectionByChecksum() {
	if ($gameChecksumsLoadingState.get() === "loading") {
		return;
	}

	$gameChecksumsLoadingState.set("loading");

	const allNonSteamAppIds = getAllNonSteamAppIds();
	const allNonSteamAppIdsLength = allNonSteamAppIds.length;

	$nonSteamAppsCount.set(allNonSteamAppIdsLength);

	toaster.toast({
		title: "PlayTime",
		body: `Generating SHA256 for ${allNonSteamAppIdsLength} non-steam games.`,
	});

	await getNonSteamGamesChecksumFromDataBase();
	await getCurrentNonSteamGamesChecksum(allNonSteamAppIds);

	$gameChecksumsLoadingState.set("loaded");

	toaster.toast({
		title: "PlayTime",
		body: `Generated SHA256 for ${gameChecksums.nonSteam.size}/${allNonSteamAppIdsLength} non-steam games.`,
	});
}

export async function addGameChecksumById(gameId: string) {
	const checksum = await getFileSHA256(Number.parseInt(gameId, 10));

	if (isNil(checksum)) {
		toaster.toast({
			title: "PlayTime",
			body: "An error happened while generating file checksum",
		});

		return;
	}

	if (checksum.status !== "ready" || isNil(checksum.checksum)) {
		toaster.toast({
			title: "PlayTime",
			body: checksumFailureMessage(checksum.status),
		});

		return;
	}

	return await Backend.addGameChecksum(
		gameId,
		checksum.checksum,
		"SHA256",
		// NOTE(ynhhoJ): 16 MB
		16 * 1024 * 1024,
	).then(async () => {
		$toggleUpdateInListeningComponents.set(
			!$toggleUpdateInListeningComponents.get(),
		);

		toaster.toast({
			title: "PlayTime",
			body: `Saved checksum for ${checksum.name}`,
		});
	});
}
