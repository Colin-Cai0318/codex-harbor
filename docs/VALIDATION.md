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

Result: 30 passed, with 67% statement coverage. The suite covers state transitions, dependency release and terminal-failure propagation, transactional admission behavior, priority, exclusive groups, persisted runtime parallelism, weekly drain/freeze semantics, model capability rejection, pending agent configuration, secret sanitization, HTTP API/dashboard rendering, JavaScript syntax validation, real temporary Git worktrees, existing Project workspace reuse, shared-session prompt injection, Task↔Thread many-to-many links, atomic YAML task-group import, Acceptance Runner behavior, Worker thread/turn/envelope persistence, quota wait/resume on the same Thread, historical quota-failure migration, and successful/blocked outcomes.

## Codex Project and existing workspace integration

The current Codex CLI generated protocol schema was inspected locally. It defines durable Project APIs, `thread/start.projectId`, `thread/start.runtimeWorkspaceRoots`, `thread/metadata/update.projectId`, and project-filtered `thread/list`. The current App Server returned an existing `Codex Harbor` Project whose root is exactly `E:\Tools\Codex_Harbor`.

Without starting a Turn, live `thread/metadata/update` calls assigned both the current development conversation and the historical T001 Thread to that existing Project. A project-filtered `thread/list` returned both IDs with the expected `projectId`; the current conversation retained cwd `E:\Tools\Codex_Harbor`. The historical T001 retained its old `C:\Users\19443\AppData\Local\CodexHarbor\worktrees\T001` cwd instead of being moved, protecting any legacy task state. New deterministic Worker coverage proves that two shared-session Tasks use one Thread, both operate in the registered existing workspace, inject the second prompt with prior-task context, and create no task worktree directories.

The user's live v2 database was opened read-only and copied through SQLite's online backup API into a process-scoped temporary directory. Migrating that copy produced schema versions 1–4, retained T001's Root Thread link, populated `task_thread_links`, and marked its historical worktree as legacy Harbor-owned. The temporary backup was removed automatically; the live database was not migrated during this validation because no daemon was running and starting one would change task state.

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

A real daemon served the dashboard at `127.0.0.1:8765`; `/api/pool`, `/api/models`, the create-task form, task detail view, and the plugin's loopback API helper were exercised successfully. Repeated quota refreshes left the pool `RUNNING`, confirming the Weekly Reset regression fix against the live structured provider.

The follow-up card-based task board was rendered in both light and dark themes with Microsoft Edge at 1600×1100. A populated preview verified lifecycle-lane placement and exact task status badges. A Simplified Chinese render additionally verified translated static/dynamic UI, the persistent language selector, and quota cards whose primary value is the remaining allowance. The integration suite parses the emitted JavaScript with Node.js so Python string escaping cannot silently break browser startup again.

## Unverified release boundaries

The following require longer-duration or additional-host release qualification and are not claimed by this Windows session:

- observation across the reset half of a real 5-hour exhaustion/reset cycle and a real weekly reset;
- destructive daemon/worker/Codex kill testing during a nontrivial in-progress code change;
- host reboot plus OS service autostart;
- Linux Native and WSL2 host matrices;
- Windows service packaging and Windows Native beta soak testing.

Fake providers and deterministic tests cover these state transitions, but they are not substitutes for the named live qualification.
