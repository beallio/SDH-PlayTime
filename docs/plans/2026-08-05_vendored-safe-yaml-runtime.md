# Plan: Vendored Safe YAML Runtime (vendored-safe-yaml-runtime)

## Context

Lutris and Bottles metadata is YAML, but the Decky backend cannot depend on a package
being installed on SteamOS and must not fetch dependencies at runtime. Vendor the
reviewed pure-Python portion of PyYAML 6.0.3 with license and archive validation,
following the local SDH-ludusavi vendoring pattern. This unit adds no launcher resolver
or runtime YAML call site; it establishes a reproducible, importable, safe dependency
boundary for later plans.

**Slug used throughout this plan:** `vendored-safe-yaml-runtime`

---

## Orchestration Contract

**Slug:** `vendored-safe-yaml-runtime`

**Plan file:**

```text
docs/plans/2026-08-05_vendored-safe-yaml-runtime.md
```

**Implementation branch:**

```text
feat/vendored-safe-yaml-runtime
```

**Round-complete marker:**

```text
/tmp/SDH-PlayTime/vendored-safe-yaml-runtime_finished
```

**Finalized marker:**

```text
/tmp/SDH-PlayTime/vendored-safe-yaml-runtime_finalized
```

**Review notes:**

```text
docs/review/vendored-safe-yaml-runtime-review-*.md
```

Each review note ends with exactly one status trailer:

```text
STATUS: CHANGES_REQUESTED
```

or:

```text
STATUS: APPROVED
```

---

## Required Agent Protocol

1. Use the **implementer** skill.
2. Work from the repository root.
3. Branch from `remix`.
4. Commit this plan as the first commit on the implementation branch.
5. Follow TDD where behavior changes are testable.
6. Run quality gates before marking any round complete.
7. Do not write your own review.
8. Do not create files under `docs/review/`.
9. Do not delete files under `docs/review/`.
10. Review notes are durable audit records and must be committed.
11. Resolving a review note means:
    - implement the requested changes;
    - run quality gates;
    - commit the code/docs changes;
    - commit the review note itself if it is not already committed;
    - recreate the round-complete marker.
12. After finalization, stop polling and exit cleanly.

---

## Scope discipline

- Implement only the units the plan lists. Do not modify files outside the plan's scope.
- Do not change runtime behavior beyond what the plan specifies. A `refactor` or
  `cleanup` commit must preserve observable behavior.
- Never edit a test's expected value to make a behavior change pass. If a test
  legitimately must change, that change must be required by the plan or a review
  note, and you must record the rationale in the session log.
- If you spot an unrelated improvement, do not make it here — note it in the
  session log for a separate plan.

---

## Setup

Start from `remix`:

```bash
git checkout remix
git pull --ff-only origin remix
git checkout -b feat/vendored-safe-yaml-runtime
```

Commit this plan first:

```bash
git add docs/plans/2026-08-05_vendored-safe-yaml-runtime.md
git commit -m "docs(plan): add vendored-safe-yaml-runtime implementation plan"
```

---

## Implementation Tasks

1. Add a single declared backend dependency pin for `PyYAML==6.0.3` and vendor only the
   pure-Python runtime package, one matching `.dist-info`, and required license metadata
   under a dedicated backend dependency path. Exclude compiled extensions, caches,
   installers, tests, and unrelated build output.
2. Provide one project-owned wrapper that exposes only `safe_load` for bytes/text under
   an explicit maximum size and rejects non-mapping roots when resolver metadata expects
   a mapping. Resolver code must not import or call unsafe/general-object loaders.
3. Update `NOTICE.md` or the repository's equivalent notice surface with the dependency,
   version, purpose, copyright, license, and included license path.
4. Update `tools/release_archive.py` and its tests so package, `.dist-info`, wrapper, and
   license files are explicitly included. Reject absent, duplicate, version-mismatched,
   compiled, cache, or development-only dependency files.
5. Update `.github/workflows/remix-release.yml` and other active build workflows only as
   needed so the same checked-in vendored files are validated; never install with pip on
   the Deck or during plugin startup.
6. Add tests that import from a clean extracted plugin archive, compare the declared pin
   with packaged metadata, exercise safe mapping/list/scalar/malformed input behavior,
   and prove unsafe Python object tags cannot construct objects.
7. Keep the vendored diff reviewable: preserve upstream files verbatim, isolate all
   project policy in the wrapper/tests, and document the exact PyYAML release source.

---

## Quality Gates

Run before marking any round complete:

```bash
scripts/orchestration/run-quality-gates
scripts/orchestration/check-review-notes-not-deleted
git status --short
```

The round is not complete unless:

1. all requested implementation work is done;
2. all relevant tests pass;
3. build/typecheck gates pass;
4. review notes have not been deleted;
5. the working tree is clean;
6. all code/docs changes are committed.

---

## Verification

1. Build and validate the release archive, extract it into a clean temporary directory,
   and import the wrapper with system site packages disabled.
2. Verify packaged metadata reports 6.0.3, exactly one distribution metadata directory
   exists, and required license material is present.
3. Verify `safe_load` parses representative Lutris/Bottles mappings and rejects unsafe
   tags, excessive input, malformed YAML, and unexpected roots.

No on-device verification is required; archive parity is the acceptance boundary.

---

## Mark Round Complete

When the implementation round is complete and the working tree is clean, run:

```bash
scripts/orchestration/mark-finished vendored-safe-yaml-runtime
```

This writes:

```text
/tmp/SDH-PlayTime/vendored-safe-yaml-runtime_finished
```

Then exit cleanly. If this process exits, the orchestrator will resume you through
`scripts/orchestration/continue-implementer vendored-safe-yaml-runtime`.

---

## Review Polling Loop

After marking the round complete, check existing review notes first, then poll for new review notes if you remain active:

```text
docs/review/vendored-safe-yaml-runtime-review-*.md
```

When a review note exists or a new review note appears:

1. Read the full review note.
2. If the note ends with:

   ```text
   STATUS: CHANGES_REQUESTED
   ```

   then resume work.

3. Clear the round-complete marker:

   ```bash
   scripts/orchestration/clear-finished vendored-safe-yaml-runtime
   ```

4. Address every requested change.
5. Run quality gates:

   ```bash
   scripts/orchestration/run-quality-gates
   scripts/orchestration/check-review-notes-not-deleted
   ```

6. Commit code/docs fixes.
7. Commit the review-note file itself if it is not already committed:

   ```bash
   git add docs/review/vendored-safe-yaml-runtime-review-*.md
   git commit -m "docs(review): record vendored-safe-yaml-runtime review notes"
   ```

8. Recreate the round-complete marker:

   ```bash
   scripts/orchestration/mark-finished vendored-safe-yaml-runtime
   ```

9. Either continue polling or exit cleanly. If you exit, the orchestrator will resume you with `scripts/orchestration/continue-implementer vendored-safe-yaml-runtime` after the next review note is created.

---

## Approval Handling

If the latest review note ends with:

```text
STATUS: APPROVED
```

then:

1. Confirm every previous review item has been addressed.
2. Confirm all review notes are committed:

   ```bash
   scripts/orchestration/check-review-notes-committed vendored-safe-yaml-runtime
   ```

3. Confirm the working tree is clean:

   ```bash
   git status --short
   ```

4. Finalize:

   ```bash
   scripts/orchestration/finalize vendored-safe-yaml-runtime
   ```

5. Confirm the finalized marker exists:

   ```text
   /tmp/SDH-PlayTime/vendored-safe-yaml-runtime_finalized
   ```

6. Stop polling and exit cleanly.

---

## Review Rules

Do not write your own review.

Do not create files under:

```text
docs/review/
```

Do not delete files under:

```text
docs/review/
```

Only the orchestrator writes review notes. Your job is to read them, resolve them, commit them as audit records, and continue the loop.

---

## Finalization Rules

Only finalize after a review note with:

```text
STATUS: APPROVED
```

Finalization is performed with:

```bash
scripts/orchestration/finalize vendored-safe-yaml-runtime
```

Do not manually merge into `remix` unless the finalize script fails and the user/orchestrator explicitly instructs you to recover manually.

Leave both markers in place after finalization:

```text
/tmp/SDH-PlayTime/vendored-safe-yaml-runtime_finished
/tmp/SDH-PlayTime/vendored-safe-yaml-runtime_finalized
```

Any project-specific release step runs from the project's
`scripts/orchestration-hooks/finalize-release` hook, invoked by finalize.
