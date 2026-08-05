# SDH-PlayTime Agent Protocol

Protocol Version: 1

This file is the repository-specific adaptation of
`../project_template/AGENTS.md`. It adopts the parent template's planning,
test-first, safety, and verification intent while replacing incompatible
Python-only wrapper, cache, structure, and session-log requirements with
SDH-PlayTime's actual mixed TypeScript/Python Decky workflow.

## 1. Session initialization

Before modifying files, verify the repository root, active branch, working-tree
state, relevant dependency/config files, and the requested scope. Report this
handshake before implementation begins:

```text
AGENT_PROTOCOL_HANDSHAKE

Project Root: /home/beallio/Dropbox/Scripts/SDH-PlayTime
Detected Languages: TypeScript, TSX, Python, shell
Git Repository Present: Yes
Active Branch:
Task Boundary: Review | Plan | Implement | Release
Orchestration Root: scripts/orchestration

Confirmed Policies:
[ ] Verified repository and branch state
[ ] Preserved unrelated user changes
[ ] Read applicable plans/review notes
[ ] Selected relevant validation commands
[ ] Kept temporary work under /tmp where practical

STATUS: READY
```

If a field cannot be confirmed, resolve it before implementation. For a
read-only review, do not create this handshake as a durable file.

## 2. Repository identity and branch policy

This repository has two intentionally separate histories:

- `master` is a fast-forward mirror of `upstream/master`.
- `remix` is the Beallio Remix integration and release branch.

Read `CONTRIBUTING_UPSTREAM.md` before branch, merge, push, pull-request, or
release work. In particular:

- Start upstream contributions from `upstream/master` on `contrib/<slug>`.
- Never branch an upstream contribution from `remix`.
- Never merge `remix` into `master`.
- Keep remix-only documentation, branding, workflows, versioning, and
  `PATCHES.md` changes off contribution branches.
- Preserve contribution commits as immutable history; do not rebase or amend
  them to add remix-only work.
- Use Conventional Commits for new commits.

## 3. Scope and working-tree safety

- Treat existing tracked edits and untracked files as user-owned unless the
  task explicitly places them in scope.
- Do not use broad staging such as `git add .`.
- Do not delete, reset, clean, or overwrite unrelated work.
- Treat `review only`, `plan only`, `no writes`, `save then wait`, and similar
  boundaries as absolute until the user explicitly changes them.
- Use `/tmp/SDH-PlayTime/` for transient clones, generated proposals, staged
  database copies, logs, and other disposable work where practical.
- Do not point the PlayTime SQLite wrapper at a supposedly read-only live or
  backup database; initialization can write SQLite pragmas. Stage a copy under
  `/tmp` first.

## 4. Evidence gathering and low-level tools

Minimize direct broad use of low-level tools such as `grep`, `cat`, `find`, and
large file or log reads.

- Delegate routine searching, repository mapping, file inspection, and broad
  evidence gathering to subagents when the work can be bounded independently.
- Ask subagents to return only relevant paths, concise excerpts, key findings,
  and unresolved uncertainties.
- Use `gpt-5.6-terra` for low-level subagents handling routine searches, file
  inspection, log gathering, and bounded evidence collection. Keep higher-level
  design, synthesis, review, and orchestration decisions on the primary model
  unless the user explicitly requests another assignment.
- For direct targeted text searches, use `rg` rather than `grep`.
- For direct file discovery, use `rg --files` rather than `find`.
- The main agent may directly inspect a narrow source range when needed to
  verify a subagent finding, prepare an edit, or complete validation.
- Avoid repeating scans already performed by an authoritative explorer.

Read repository, device, database, and log evidence before asking avoidable
questions or proposing changes. For diagnostics, distinguish active failures
from reload, shutdown, or service-restart noise.

## 5. GitHub interaction

- Use `gh` for all github.com service operations, including repositories,
  pull requests, issues, releases, workflows, fork synchronization, and API
  queries.
- Use `git` for local repository operations and Git transport that `gh` does
  not support.
- Do not use browser tools, web search, `curl`, or direct GitHub API requests
  when `gh` can perform the operation.
- If `gh` authentication fails, stop and report the failure rather than
  silently switching to another GitHub access path.

## 6. Planning and orchestration

The shared engine is installed at `scripts/orchestration`, with project policy
in `orchestration.conf` and `scripts/orchestration-hooks/`.

- Save implementation plans under `docs/plans/`.
- Use `scripts/orchestration/new-plan <slug> <title>` when scaffolding an
  orchestration plan.
- Fill every required section and validate with
  `scripts/orchestration/validate-plan <slug>` before implementation.
- Use the `orchestrated-implementation` skill for a user-authorized
  plan/implement/review/finalize workflow.
- Keep review notes under `docs/review/` and commit a review note before
  continuing an implementer round.
- Do not start an implementer, merge, push, publish, or release merely because
  a plan was requested.
- Before starting a new orchestration run, verify that local overrides target
  the intended base branch; stale overrides from an earlier feature must not be
  reused silently.

## 7. Implementation lifecycle

For modifying tasks, follow:

```text
ANALYZE -> PLAN -> TEST (RED) -> IMPLEMENT (GREEN) -> REFACTOR -> VALIDATE
```

- Add or update a focused regression test before the behavior change whenever
  the behavior is testable.
- Demonstrate that the new test fails for the expected reason before the fix.
- Implement the smallest coherent change that satisfies the test and plan.
- Preserve existing public behavior outside the approved scope.
- Refactor only while the focused and relevant suites remain green.
- Do not weaken tests, guards, or validation merely to make a change pass.
- Do not commit unless the user or active orchestration workflow authorizes it.

## 8. Dependency and API verification

- Verify frontend dependencies through `package.json` and `pnpm-lock.yaml`.
- Do not modify dependency versions or lockfiles unless required by the task.
- Prefer `pnpm install --frozen-lockfile` for a clean dependency install.
- Use ephemeral `uv` execution for the repository's pytest suite; do not create
  a repository virtual environment or run `pip install` for routine validation.
  The authoritative orchestration hook separately runs its established
  `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest` gate.
- Treat Steam/Decky runtime interfaces as unstable internal APIs. Verify local
  declarations, existing call sites, and live behavior when correctness depends
  on runtime-only fields.
- Never infer that a non-Steam game is installed merely because its Steam
  shortcut or launcher exists. Launcher metadata and the resolved game payload
  must be verified separately; unsupported cases remain `unknown`.

## 9. Validation commands

Choose validation proportionate to the change. The normal complete suite is:

```bash
uv run --with pytest pytest
bun test
pnpm exec tsc --noEmit
pnpm exec biome format .
pnpm exec biome lint .
pnpm build
```

The repository's orchestration quality gate is invoked with:

```bash
scripts/orchestration/run-quality-gates
```

For a focused change, run the smallest relevant negative control and focused
test first, then expand to the complete applicable suite before claiming the
feature ready. Before committing, also run `git diff --check` and inspect the
exact staged paths.

Do not claim a command passed unless it was run successfully in the current
worktree. If a required command is unavailable, say so and report the narrower
evidence that was obtained.

## 10. Database and live-device safety

- Treat per-user databases under `users/<steam-id>/storage.db` as authoritative;
  do not default to the legacy root database.
- Keep live and backup data read-only during diagnosis.
- Before an authorized live database update, create and verify a recoverable
  backup, stop/check both Steam and `plugin_loader.service`, verify no process
  holds the database, and fail closed on uncertainty.
- Restore service state on both success and failure, then verify database
  integrity, foreign keys, installed files, and relevant logs.
- Never launch a game merely to test whether a shortcut is reachable unless the
  user explicitly asks for that external action.

## 11. Documentation and definition of done

Update documentation when behavior, user workflow, development procedure, or
release policy changes. Keep user-facing installation/use guidance in `README.md`
and contributor/release mechanics in the dedicated maintainer documentation.

A modifying task is complete only when:

```text
[ ] Scope and plan requirements are satisfied
[ ] Focused negative control was demonstrated where applicable
[ ] Relevant frontend and backend tests pass
[ ] TypeScript and Biome checks pass where applicable
[ ] Production build passes where applicable
[ ] git diff --check passes
[ ] Unrelated user changes remain untouched
[ ] User-facing or maintainer documentation is updated when needed
[ ] Final response names changed files, verification, and remaining risks
```

## 12. Failure recovery

When a command or test fails:

1. Capture the relevant error without dumping unrelated logs.
2. Identify the failing component and reproduce it with the narrowest useful
   test or command.
3. Fix the root cause rather than retrying blindly.
4. Re-run the focused test, then the broader applicable gates.
5. If the failure reveals a scope or safety conflict, stop and request
   direction instead of silently broadening the task.
