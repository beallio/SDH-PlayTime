import { describe, expect, it } from "bun:test";
import getEmudeckPathToGame from "@src/steam/utils/GamePaths";

describe("getEmudeckPathToGame legacy compatibility", () => {
	// The classifier may retain identity evidence, but this legacy helper must
	// never return an unproven ROM path to a checksum caller.
	it("does not return a classifier-only EmuDeck ROM path", () => {
		const command =
			'"/home/deck/Emulation/tools/launchers/dolphin-emu.sh" -e "/home/deck/ROMs/Game.iso"';

		expect(getEmudeckPathToGame(command)).toBeUndefined();
	});
});
