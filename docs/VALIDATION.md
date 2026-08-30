# Validation record

Date: 2026-08-30
Host: Windows Native
Codex CLI: 0.149.1
Python: CPython 3.14.6 (local validation)

## Automated suite

Command:

```text
uv run pytest -q
```

Result: 34 passed, 68% statement coverage (83 dependency deprecation warnings). The suite covers state transitions, dependency release and terminal-failure propagation, transactional admission behavior, priority, exclusive groups, persisted runtime parallelism, weekly drain/freeze semantics, model capability rejection, pending agent configuration, secret sanitization, HTTP API/dashboard rendering, emitted JavaScript syntax, Project-filtered conversation listing, durable new-conversation creation, runtime workspace roots, exact conversation-cwd preservation, raw first-message injection into an existing conversation, schema-v5 persistence, real temporary Git worktrees, existing Project workspace reuse, shared-session prompt injection, Task↔Thread many-to-many links, atomic YAML task-group import, Acceptance Runner behavior, Worker thread/turn/envelope persistence, quota wait/resume on the same Thread, historical quota-failure migration, and successful/blocked outcomes.

## Codex Project and existing workspace integration

The current Codex CLI generated protocol schema was inspected locally. It defines durable Project APIs, `thread/start.projectId`, `thread/start.runtimeWorkspaceRoots`, `thread/metadata/update.projectId`, and project-filtered `thread/list`. The current App Server returned an existing `Codex Harbor` Project whose root is exactly `E:\Tools\Codex_Harbor`.

Without starting a Turn, live `thread/metadata/update` calls assigned both the current development conversation and the historical T001 Thread to that existing Project. A project-filtered `thread/list` returned both IDs with the expected `projectId`; the current conversation retained cwd `E:\Tools\Codex_Harbor`. The historical T001 retained its old `C:\Users\19443\AppData\Local\CodexHarbor\worktrees\T001` cwd instead of being moved, protecting any legacy task state. New deterministic Worker coverage proves that two shared-session Tasks use one Thread, both operate in the registered existing workspace, inject the second prompt with prior-task context, and create no task worktree directories.

The earlier v2 validation used a read-only copy and left the live database unchanged. During the Project-conversation E2E run below, `harbor doctor` and the daemon safely migrated the live database through schema version 5. A recoverable pre-E2E snapshot is retained at `%LOCALAPPDATA%\CodexHarbor\backups\harbor-pre-e2e-20260830.db`.

## Project-driven creation and real example tasks

Three tasks were created through the live loopback API against the existing
`Codex Harbor` Project (`01a05029-18b6-7b32-bcce-6367259f1f3d`). The primary
workspace was the ignored E-drive fixture
`E:\Tools\Codex_Harbor\.harbor\e2e-project`; no task worktree was created under
the C-drive data directory.

| Task | Creation mode | Codex Thread | Result | Evidence |
|---|---|---|---|---|
| T002 | New conversation, two runtime workspace roots | `01a0534c-c43b-7300-8fc2-4957179f5d7e` | `SUCCEEDED`, 1 Turn, 0 failures | Read `context.txt` from the second root; wrote the exact token and `NEW_CONVERSATION_OK`; three acceptance commands passed |
| T003 | Existing conversation selected from the Project | same Thread as T002 | `SUCCEEDED`, 1 Turn, 0 failures | Appended `CONTINUATION_SAME_SESSION_OK`; retained the T002 conversation name and cwd; four acceptance commands passed |
| T004 | New conversation, no acceptance commands | `01a0534d-f199-7b30-a97c-9afb8ef5caa2` | `SUCCEEDED`, 1 Turn, 0 failures | Wrote `NO_ACCEPTANCE_COMMAND_OK`; normal Codex Turn completion was sufficient |

The Project-filtered live conversation list returned both new Threads with
source `vscode`, cwd equal to the E-drive fixture, and names prefixed `[T002]`
and `[T004]`. T003 deliberately did not rename the selected T002 conversation.
The persisted task rows have `direct_prompt=1`; T003 also has
`preserve_thread_name=1`. The live account remained available after the run
(77% of the five-hour window and 49% of the weekly window remained at the final
observation).

The fixture remains Git-ignored for inspection. Its source commit is unchanged;
only `result.txt` and `no-acceptance.txt` are untracked test outputs. The daemon
was shut down cleanly after recording the results.

## Real 5-hour limit incident and repair

The user's persisted `T001` supplied a real App Server error containing `codexErrorInfo: usageLimitExceeded`. Five Turns had been incorrectly classified as `AGENT_FAILURE`, exhausting `max_attempts` and leaving the Task `FAILED`. The root cause was a text classifier that recognized older 5-hour phrases but not the current structured error marker.

The v3 migration and state-machine fix were validated against an online SQLite backup, not the live database. The copied `T001` migrated from `FAILED` to `WAIT_QUOTA`; all five historical records became `RATE_LIMIT_5H`/`WAIT_QUOTA`, `failure_count` became zero, and the existing Root Thread ID remained unchanged. The live database was deliberately left untouched while the old daemon continued running.

A deterministic end-to-end regression then simulated the first Codex Turn returning the exact real error, quota becoming available, and a new Worker claiming the task. Evidence after completion: two retained execution records (`turn-quota`, `turn-resumed`), one Root Thread shared by both, `failure_count=0`, and a successful `thread/resume` path rather than a new session.

The current live App Server also accepted `thread/name/set` for T001 without starting a Turn. A following `thread/read` returned the same durable Thread ID, the assigned `[T001] ...` name, and source `vscode`, confirming that Harbor is using the Codex-visible thread store rather than a detached transcript.

## Codex App Server Phase 0

Command:

```text
uv run python tools/app_server_poc.py --workspace .
```

Observed result: passed.

- Process A completed a durable thread start and first turn.
- Process A exited.
- A distinct Process B resumed and read the same thread ID.
- Persisted history contained the first turn.
- Process B completed a second turn on that thread.

The local evidence JSON is intentionally Git-ignored because it contains machine-local process and thread identifiers.

## Real Harbor task

An isolated temporary Git repository and Harbor data directory were used. Harbor created `harbor/T001` in its owned worktree, persisted the Root Thread before completion, ran a real Codex turn that created the requested file, executed the configured PowerShell acceptance command, and recorded `SUCCEEDED` after one Attempt. The source repository was untouched.

This run found a false Weekly Reset classification caused by a provider revising a future reset estimate. The classifier was corrected to require that observation time has crossed the old reset boundary in addition to window identity and reset-time advancement; a regression test was added.

## Doctor and Local API

`harbor doctor` passed Python, SQLite, Git, Codex executable resolution, App Server initialization, account read, dynamic Model Registry (six models observed), execution backend, database, and filesystem checks.

A real daemon served the dashboard at `127.0.0.1:8765`; `/api/pool`, `/api/models`, `/api/codex/projects`, project-filtered conversation loading, Project-driven task creation, task detail view, and the plugin's loopback API helper were exercised successfully. Repeated quota refreshes left the pool `RUNNING`, confirming the Weekly Reset regression fix against the live structured provider.

The follow-up card-based task board was rendered in both light and dark themes with Microsoft Edge at 1600×1100. A populated preview verified lifecycle-lane placement and exact task status badges. A Simplified Chinese render additionally verified translated static/dynamic UI, the persistent language selector, and quota cards whose primary value is the remaining allowance. The integration suite parses the emitted JavaScript with Node.js so Python string escaping cannot silently break browser startup again.

After the Project-driven redesign, Edge DevTools Protocol QA opened the actual
creation dialog against the live daemon. It loaded nine Projects and four
conversations for the selected Codex Harbor Project. The existing-conversation
view displayed the conversation name, cwd, and preview; switching to new mode
hid that panel, showed the workspace-root editor, and populated the Project root
as the initial primary directory. Dark-theme screenshots are retained under the
Git-ignored `.harbor/` directory.

## Unverified release boundaries

The following require longer-duration or additional-host release qualification and are not claimed by this Windows session:

- observation across the reset half of a real 5-hour exhaustion/reset cycle and a real weekly reset;
- destructive daemon/worker/Codex kill testing during a nontrivial in-progress code change;
- host reboot plus OS service autostart;
- Linux Native and WSL2 host matrices;
- Windows service packaging and Windows Native beta soak testing.

Fake providers and deterministic tests cover these state transitions, but they are not substitutes for the named live qualification.
