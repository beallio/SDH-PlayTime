# Ludusavi / SDH-PlayTime Deck checkpoint (2026-08-07)

## Where we are
- User-facing report: Ludusavi still not shown as installed despite recent flatpak/shortcut fallback code.
- No code changes requested in this step; this note captures current state only.

## Repo/code status observed
- Branch: `remix`
- Uncommitted changes already present in working tree:
  - `main.py`
  - `src/app/gamePresence.ts`
  - `src/app/backend.ts`
  - `src/constants.ts`
  - `src/steam/utils/getAppDetails.ts`
  - `src/test/gamePresence.spec.ts`
  - `py_modules/tests/main_test.py`
- New runtime fallback exists in `src/app/gamePresence.ts`:
  - `runtimeGetAppDetails` tries `getAppDetailsResult(appId)` and on `registration-error` falls back to `Backend.getShortcutAppDetails(catalogAppId)`.
  - `catalogAppId` conversion uses `appId < 0 ? appId >>> 0 : appId`.
  - `refreshCurrentGamePresenceSnapshot` default path includes this fallback.
- Backend exposes `get_shortcut_app_details` via `src/app/constants.ts` and `src/main.py`.

## Deck-side checks completed
- Verified plugin process currently not running:
  - `ps -ef | rg -i "plugin_loader|loader|decky"` did not include `SDH-PlayTime` python process.
- `homebrew/logs/SDH-PlayTime/` contains multiple logs ending with repeated lifecycle unload/uninstall events for PlayTime (`09:12:53`, `09:18:07`, `10:13:00`, `10:37:09`), suggesting plugin was unloaded/removed repeatedly and currently not active.
- Latest plugin logs include `_set_current_user` entries but no clear load/start errors; no active process indicates plugin likely not currently loaded in `plugin_loader` context.
- `plugin.json` version on deck: `3.3.0+beallio.10`.
- Main plugin code on deck includes `get_shortcut_app_details` method.

## Database check on deck
- DB inspected: `/home/deck/homebrew/data/SDH-PlayTime/storage.db`.
- `game_dict` does **not** contain any Ludusavi rows.
  - `SELECT game_id,name FROM game_dict WHERE name LIKE '%Ludusavi%'` returned `[]`.
- Tracking status for known Ludusavi candidate ids also absent.
  - `SELECT game_id,status... WHERE game_id='3867646107'` returned empty.
- `game_dict` does include `3245664592 -> Heroic Games Launcher` (existing non-steam/shortcut-like row not Ludusavi).
- No per-user subfolder databases found under `/home/deck/homebrew/data/SDH-PlayTime` (only root `storage.db`).

## Most likely current failure mode
- The “not installed” UI symptom is consistent with plugin not being loaded in Decky + DB not containing Ludusavi `game_dict` tracking row.
- Without plugin process, no backend RPC (`get_association_candidates` / new `get_shortcut_app_details`) can be exercised even though frontend code is updated.

## Suggested next resume actions
1. Re-enable/reinstall/update PlayTime plugin in Deck so `SDH-PlayTime` is active in `PluginLoader` process list.
2. Confirm by checking:
   - `ps -ef | rg 'Decky|PlayTime'` shows a `SDH-PlayTime` Python process.
   - `homebrew/logs/SDH-PlayTime/latest` has startup not immediate unload.
3. In UI/association flow, confirm candidate for Ludusavi exists:
   - `game_dict` row present in storage DB and status row optional.
   - If missing, add mapping via PlayTime association/normal path first, then validate availability.
4. Once plugin active, re-run scan and capture candidate snapshot/availability JSON for Ludusavi (`game_id` around `3867646107`, if that is extracted shortcut unsigned ID).
