# Developer guide

## Game-parent integration contract

Grouped records have one explicit canonical parent. Checksums can discover a component,
but never silently choose or replace its parent. The confirmation RPC validates the
complete component and its fingerprint in one transaction, then replaces its explicit
star atomically. A stale snapshot, unexpected member, duplicate selection, or failed
insert leaves the existing associations intact.

Presence is read-only. Inventory (`current`, `historical`, or `unknown`) and payload
availability (`running`, `reachable`, `unreachable`, or `unknown`) answer different
questions. Refresh may change either status but must not add associations, persist a
candidate, or request a checksum. A checksum is generated only after a resolver proves
a regular payload is reachable.

## Fixture-backed resolver support matrix

The table is the support boundary. A checked fixture is evidence for the listed shape,
not a blanket guarantee for a launcher family. Custom roots and variants not represented
by these fixtures remain `unknown` until they complete the extension procedure below.

| Resolver path | Verified shapes | Fixture and focused test | Fixture provenance | Local fence commits |
| --- | --- | --- | --- | --- |
| Direct | Direct Linux executable, AppImage, or Windows executable; external-drive disconnect/reconnect; regular-file proof | `py_modules/tests/fixtures/direct_game_resolution.json`, `py_modules/tests/game_parent_integration_test.py`, `py_modules/tests/game_resolution_test.py` | Local protocol fixture: direct resolution has no launcher metadata source and is proved only from bounded shortcut evidence plus a regular file. | `843740b29f4839564d1b1569849f306682b74f53` (resolver); `ddefdae2c2327a3b5c8c2f9af74dc71dd4989b3f`, `b1da6628e06679e3ae1b69bed1d91171122f595e` (hardening) |
| Heroic native | Source-backed Legendary and sideload metadata from the native Heroic config root | `py_modules/tests/fixtures/heroic_game_resolution.json`, `py_modules/tests/game_parent_integration_test.py`, `py_modules/tests/heroic_game_resolution_test.py` | `Heroic-Games-Launcher/HeroicGamesLauncher@d6366b34084be43369f24ff04a50dab39ce5a454` | `513c69c7339e55ea77297b23a31771099297209e` (adapter); `708771369ca5d0c2622b64fe205d0a5e767c3114`, `6d5203178d56a6b90b31351e063cb2250002d579` (hardening) |
| Heroic Flatpak | Recognized `com.heroicgameslauncher.hgl` shortcut with the source-backed legacy Legendary URI and Flatpak config root | `py_modules/tests/fixtures/heroic_game_resolution.json`, `py_modules/tests/heroic_game_resolution_test.py` | `Heroic-Games-Launcher/HeroicGamesLauncher@d6366b34084be43369f24ff04a50dab39ce5a454` | `513c69c7339e55ea77297b23a31771099297209e`; `6d5203178d56a6b90b31351e063cb2250002d579` |
| Heroic GOG or Nile | No source-addressable positive fixture in this release; treat as `unknown` | Negative coverage in `py_modules/tests/heroic_game_resolution_test.py` | None; adding support requires the deferred-adapter procedure below. | Fail-closed boundary retained by the commits above |
| Unsupported | Lutris, Bottles, EmuDeck/Steam ROM Manager, ambiguous wrappers, custom roots, or any unverified variant | `src/test/utils/steam/shortcutEvidenceClassifier.spec.ts`, `src/test/utils/steam/getPathToGame.spec.ts` | Not applicable; these paths are deliberately unsupported. | Fail-closed boundary retained by the commits above |

The fixture-provenance column is the evidence for a launcher claim. Local commits record
the implementation fences only; they are not upstream fixture provenance. When upstream
sourcing is required for a change, record the upstream commit or release identifier
alongside the new fixture; do not substitute a launcher name or an unverified current
installation for that evidence.

## Security, privacy, and logging rules

- Treat all frontend shortcut fields and metadata paths as untrusted hints. Keep size,
  depth, record-count, and path bounds in the backend; never scan unrelated roots.
- Do not invoke a shell, subprocess, launcher CLI, URL, mount operation, or game while
  resolving a payload. The resolver reads bounded metadata and probes only the candidate
  selected by the recognized grammar.
- Use `py_modules.safe_yaml.safe_load` for any YAML metadata. It accepts the vendored,
  pure-Python PyYAML safe loader only, rejects aliases and oversized/deep structures,
  and must never use an unsafe loader or execute YAML tags.
- Do not log launch commands, payload paths, home-directory paths, account IDs, or
  metadata contents at normal levels. Error responses expose structured reason codes,
  not personal paths.
- Do not resolve by first match. Multiple candidate payloads, conflicting launcher
  evidence, or mismatched metadata are ambiguous and must fail closed.

## Adding a deferred adapter

1. Add a source-addressable fixture for a real, versioned launcher shape and record the
   upstream repository commit or release that supplied it.
2. Extend the frontend classifier only enough to emit bounded launcher evidence. Keep
   unknown forms ambiguous; no caller path may become a payload fallback.
3. Add a dependency-injected backend adapter with bounded metadata reads, safe parsing,
   no execution, and a resolver result that proves a regular reachable payload.
4. Add focused negative tests for shell syntax, traversal, duplicate/conflicting keys,
   unbounded scans, custom roots, absent volumes, first-match ambiguity, and no leaked
   paths. Add positive fixture tests only for the verified variant.
5. Update this matrix, user support wording, archive requirements, and the release
   archive test. Keep the variant `unknown` until all gates and live verification pass.

## Updating the vendored archive dependency

1. Deliberately change the single pin in `requirements-vendored.txt` and record the
   upstream source archive SHA-256 in `tools/release_archive.py`.
2. Replace only the reviewed pure-Python runtime, metadata, and license files. Update
   every exact `VENDORED_PYYAML_FILE_HASHES` entry; do not package tests, caches,
   installer metadata, Cython sources, or native extensions.
3. Extend `tests/test_release_archive.py` and `tests/test_vendored_safe_yaml.py` for the
   new manifest. Build a clean archive, extract it outside the checkout, and import the
   backend with host PyYAML unavailable.
4. Run the focused commands below and the full quality gate before changing release
   automation or publishing an archive.

## Focused verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  py_modules.tests.main_test.TestPlugin.test_grouped_confirmation_projects_one_canonical_parent_everywhere \
  py_modules.tests.main_test.TestPlugin.test_grouped_confirmation_rpc_rejects_stale_state_and_rolls_back \
  py_modules.tests.game_checksum_test \
  py_modules.tests.heroic_game_resolution_test
bun test src/test/cachables.spec.ts src/test/steamPlayTimePatches.spec.ts src/test/gamePresence.spec.ts
TZ=America/Los_Angeles bun test src/test/cachables.spec.ts src/test/steamPlayTimePatches.spec.ts
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_release_archive tests.test_vendored_safe_yaml
scripts/orchestration/run-quality-gates
```

## Deferred live Steam Deck checklist

Run this only on a Deck with representative native Steam, direct-shortcut, and Heroic
installations, including an external drive. Do not launch a game solely for this check.

- Record SteamOS, Decky Loader, PlayTime, launcher, runner, Flatpak, and configuration
  versions before testing; unrecorded variants remain unverified.
- Navigate the grouped-games flow with a gamepad. Verify long and duplicate labels,
  the native install-state capability, two independent status axes, warnings, and
  Refresh behavior.
- Verify native, direct, and Heroic groups through recommendation, confirmation,
  reparent, detach, dissolve, and removal. Confirm historical records retain their
  playtime and the explicitly confirmed parent remains canonical.
- Disconnect and reconnect the external drive. Confirm current inventory remains
  visible, availability changes without a database write, no checksum is generated
  while unavailable, and checksum resumes only after a reachable payload is proved.
- Record the exact shortcut and metadata variant for every successful result. Escalate
  unsupported, ambiguous, custom-root, Lutris, Bottles, and EmuDeck/SRM cases as
  `unknown`; do not advertise them as supported.
