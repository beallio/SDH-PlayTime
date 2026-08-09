export const GITHUB_URL =
	"https://github.com/beallio/SDH-PlayTime-beallio-remix";

/** Release notes for a specific build; the tag exists for every shipped version. */
export function changelogUrlForVersion(version: string): string {
	return `${GITHUB_URL}/releases/tag/v${version}`;
}
