# SDH-PlayTime Beallio Remix

> [!IMPORTANT]
> This is an **unofficial, independent remix** of [upstream SDH-PlayTime](https://github.com/0u73r-h34v3n/SDH-PlayTime). It keeps the installed folder `SDH-PlayTime` and runtime/plugin identity **PlayTime** so an in-place upgrade keeps the same data and settings. It is not a separate Decky Store plugin.

<div align="center">

[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)

</div>

![PlayTime Logo](https://raw.githubusercontent.com/0u73r-h34v3n/PlayTime/refs/heads/master/assets/image.png)

PlayTime is a Steam Deck plugin that tracks time spent in Steam and non-Steam games. It offers weekly, monthly, and overall reports, imports data from SteamLessTimes and MetaDeck, and allows manual playtime adjustments. This remix preserves that product and runtime identity while carrying independently maintained changes.

## Releases and support boundary

This remix is distributed through [GitHub Releases](https://github.com/beallio/SDH-PlayTime-beallio-remix/releases) only. There is intentionally no separate Decky Store listing: installing a second Store identity would risk a second plugin installation and separate state.

- Prefer a versioned **stable** release, for example [`v3.3.0+beallio.1`](https://github.com/beallio/SDH-PlayTime-beallio-remix/releases/tag/v3.3.0+beallio.1), and download `SDH-PlayTime-beallio-remix-v3.3.0+beallio.1.zip` plus its `.sha256` file.
- [`remix-nightly`](https://github.com/beallio/SDH-PlayTime-beallio-remix/releases/tag/remix-nightly) is a rolling prerelease. Its expected files are `SDH-PlayTime-beallio-remix-nightly.zip` and `SDH-PlayTime-beallio-remix-nightly.zip.sha256`. It moves to newer commits and may regress; use it only when you can test and roll back.

The ZIP name is release-specific, but its contents always have exactly one `SDH-PlayTime/` root. That root is intentional and must not be renamed during installation.

## Safe Steam Deck in-place upgrade

These commands are for SteamOS Desktop Mode or an SSH shell as `deck`. They upgrade the existing `PlayTime` plugin **in place** at `/home/deck/homebrew/plugins/SDH-PlayTime`; they do not uninstall it, create another Decky Store entry, or run in this repository's development environment. Read the whole block before running it.

Choose a stable tag and its matching asset below. For a nightly, change only `RELEASE_TAG` and `ARCHIVE_NAME` to `remix-nightly` and `SDH-PlayTime-beallio-remix-nightly.zip` after accepting the rolling-build warning above.

```bash
set -euo pipefail

RELEASE_TAG='v3.3.0+beallio.1'
ARCHIVE_NAME='SDH-PlayTime-beallio-remix-v3.3.0+beallio.1.zip'
RELEASE_BASE="https://github.com/beallio/SDH-PlayTime-beallio-remix/releases/download/${RELEASE_TAG}"

PLUGIN_DIR='/home/deck/homebrew/plugins/SDH-PlayTime'
RUNTIME_DIR='/home/deck/homebrew/data/SDH-PlayTime'
SETTINGS_DIR='/home/deck/homebrew/settings/SDH-PlayTime'
BACKUP_PARENT='/home/deck/backups/SDH-PlayTime'
STAMP="$(date '+%Y%m%d-%H%M%S')"
BACKUP_DIR="${BACKUP_PARENT}/remix-upgrade-${STAMP}"
DOWNLOAD_DIR="/home/deck/Downloads/sdh-playtime-remix-${STAMP}"
ARCHIVE_PATH="${DOWNLOAD_DIR}/${ARCHIVE_NAME}"
CHECKSUM_PATH="${ARCHIVE_PATH}.sha256"
STAGING_DIR="${DOWNLOAD_DIR}/staging"

test -d "${PLUGIN_DIR}" || {
  echo "Expected existing PlayTime install at ${PLUGIN_DIR}; refusing to create a second identity." >&2
  exit 1
}

mkdir -p "${DOWNLOAD_DIR}" "${BACKUP_DIR}" "${STAGING_DIR}"
curl --fail --location --output "${ARCHIVE_PATH}" "${RELEASE_BASE}/${ARCHIVE_NAME}"
curl --fail --location --output "${CHECKSUM_PATH}" "${RELEASE_BASE}/${ARCHIVE_NAME}.sha256"
(
  cd "${DOWNLOAD_DIR}"
  sha256sum --check "$(basename "${CHECKSUM_PATH}")"
)
unzip -tq "${ARCHIVE_PATH}"

mapfile -t ZIP_ROOTS < <(zipinfo -1 "${ARCHIVE_PATH}" | awk -F/ 'NF { print $1 }' | sort -u)
test "${#ZIP_ROOTS[@]}" -eq 1
test "${ZIP_ROOTS[0]}" = 'SDH-PlayTime'
unzip -q "${ARCHIVE_PATH}" -d "${STAGING_DIR}"
test -f "${STAGING_DIR}/SDH-PlayTime/main.py"
test -f "${STAGING_DIR}/SDH-PlayTime/dist/index.js"
test -f "${STAGING_DIR}/SDH-PlayTime/py_modules/__init__.py"

sudo systemctl stop plugin_loader.service
if systemctl is-active --quiet plugin_loader.service; then
  echo 'plugin_loader.service did not stop; refusing to replace plugin files.' >&2
  exit 1
fi

sudo mkdir -p "${BACKUP_DIR}/plugin"
sudo rsync -a "${PLUGIN_DIR}/" "${BACKUP_DIR}/plugin/"
if test -d "${RUNTIME_DIR}"; then
  sudo mkdir -p "${BACKUP_DIR}/runtime"
  sudo rsync -a "${RUNTIME_DIR}/" "${BACKUP_DIR}/runtime/"
fi
if test -d "${SETTINGS_DIR}"; then
  sudo mkdir -p "${BACKUP_DIR}/settings"
  sudo rsync -a "${SETTINGS_DIR}/" "${BACKUP_DIR}/settings/"
fi

test -f "${BACKUP_DIR}/plugin/main.py" || {
  echo "Backup verification failed: ${BACKUP_DIR}/plugin/main.py is missing." >&2
  exit 1
}

sudo rsync -a --delete "${STAGING_DIR}/SDH-PlayTime/" "${PLUGIN_DIR}/"
sudo chown -R deck:deck "${PLUGIN_DIR}"
sudo systemctl start plugin_loader.service
sudo systemctl is-active --quiet plugin_loader.service
sudo systemctl status --no-pager plugin_loader.service
```

The plugin stores playtime databases under its Decky runtime directory, including the legacy `storage.db` and per-user `users/<SteamID>/storage.db` files. Its frontend settings use the established `decky-loader-SDH-Playtime` storage key. The upgrade above deliberately replaces only `PLUGIN_DIR`; it backs up runtime/settings paths and leaves them in place.

If the loader does not become active, roll back the plugin files from the timestamped backup, then restart and inspect its status:

```bash
set -euo pipefail

PLUGIN_DIR='/home/deck/homebrew/plugins/SDH-PlayTime'
BACKUP_DIR='/home/deck/backups/SDH-PlayTime/remix-upgrade-REPLACE_WITH_TIMESTAMP'

test -d "${BACKUP_DIR}/plugin" || {
  echo "Backup not found: ${BACKUP_DIR}/plugin" >&2
  exit 1
}
sudo systemctl stop plugin_loader.service
sudo rsync -a --delete "${BACKUP_DIR}/plugin/" "${PLUGIN_DIR}/"
sudo chown -R deck:deck "${PLUGIN_DIR}"
sudo systemctl start plugin_loader.service
sudo systemctl status --no-pager plugin_loader.service
```

Do not restore the backed-up runtime or settings directory for a simple code rollback: the in-place upgrade does not replace them. Keep the timestamped backup until PlayTime works normally in Gaming Mode.

## Features

- Weekly and monthly reports to show gaming habits over time.
- An overall playtime summary for Steam and non-Steam games.
- Data migration from SteamLessTimes and MetaDeck.
- Manual playtime adjustments and configurable presentation.
- Custom non-Steam cover art; see [Custom Covers](docs/covers.md).

## Grouped games and non-Steam shortcut status

PlayTime can present records that refer to the same game as one grouped record. The
grouped-games screen keeps two independent facts visible:

- **Inventory status** says whether Steam currently reports the record on this Deck:
  `current`, `historical`, or `unknown` when inventory evidence is incomplete.
- **Availability status** says whether the payload can be used now: `running`,
  `reachable`, `unreachable`, or `unknown`.

These are deliberately separate. A game can be historical but still have saved
playtime, or current while an external drive is disconnected. Use Refresh to obtain
new read-only inventory and availability evidence; Refresh does not rewrite an
association, discard history, or generate a checksum.

The parent shown as a recommendation is only a suggestion. It is based on the current
component and presence evidence and is never silently persisted. Confirming the group
is the deliberate action that selects its canonical parent. That parent can have zero
recorded time, and remains canonical even if a later checksum, refresh, or different
representative would otherwise sort first. Reparent, detach, and dissolve actions are
explicit reviewable operations; grouped history is retained when a member disappears
from the current library.

For non-Steam shortcuts, a shortcut entry or launcher executable is not proof that a
game is installed. PlayTime accepts a checksum only after its backend resolver proves
the actual regular payload is reachable. Supported resolver paths are direct Linux
executables, AppImages, and Windows executables with direct-game evidence, plus
recognized Heroic native or Flatpak shortcuts using source-backed Legendary or sideload
metadata. Heroic GOG and Nile variants do not yet have a source-addressable positive
fixture, so they remain `unknown`. A missing payload, ambiguous shortcut, custom root,
or other unverified launcher variant remains visible as `unknown` or `unreachable` and
is not automatically selected or hashed.

Lutris, Bottles, and EmuDeck/Steam ROM Manager are intentionally unsupported in this
release. They stay fail-closed: PlayTime does not infer a payload, invoke their
launchers, or treat them as a confirmed installation. If a direct or Heroic game is on
an external drive, disconnecting the drive changes availability to `unreachable`; it
does not remove playtime or reparent the group. Reconnect the drive and Refresh before
requesting a checksum.

Live Deck validation is deferred until representative installations are available. The
maintainer checklist is in [DEVELOPER.md](DEVELOPER.md); it records the launcher version
and configuration variant before any support claim is expanded.

## Development and upstream contributions

This remix uses pnpm 10, Bun, and Python through ephemeral `uv`. Release packaging and CI are described by the repository tooling; end-user installations should use GitHub Release archives rather than building from source.

For a change suitable for upstream, follow [Upstream contribution flow](CONTRIBUTING_UPSTREAM.md). For remix-only differences and their status, see the durable [patch ledger](PATCHES.md).

## Credits and support

This remix is based on [SDH-PlayTime by its upstream contributors](https://github.com/0u73r-h34v3n/SDH-PlayTime). Credit remains with the original authors, contributors, Decky Loader, and the broader Steam Deck homebrew community.

For upstream PlayTime discussion, see the [PlayTime support thread](https://discord.com/channels/960281551428522045/1087800823846813716) in the [Decky Loader Discord](https://discord.com/invite/U88fbeHyzt). Upstream support and remix support are separate boundaries.
