interface CollectionStore {
	userCollections: SteamCollection[];
	GetUserCollectionsByName: (name: string) => SteamCollection[];
	allAppsCollection: SteamCollection;
	/**
	 * NOTE(ynhhoJ): `null` on desktop mode
	 */
	deckDesktopApps?: SteamCollection;
	/**
	 * Steam's set of locally installed apps. Absent on some clients.
	 */
	localGamesCollection?: SteamCollection;
}
