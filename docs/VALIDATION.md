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

Result: 19 passed. The suite covers state transitions, dependency release, transactional admission behavior, priority, exclusive groups, weekly drain/freeze semantics, model capability rejection, pending agent configuration, secret sanitization, HTTP API/dashboard rendering, real temporary Git worktrees, Acceptance Runner behavior, Worker thread/attempt/envelope persistence, and successful/blocked outcomes.

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

## Unverified release boundaries

The following require longer-duration or additional-host release qualification and are not claimed by this Windows session:

- observation across a real 5-hour exhaustion/reset and a real weekly reset;
- destructive daemon/worker/Codex kill testing during a nontrivial in-progress code change;
- host reboot plus OS service autostart;
- Linux Native and WSL2 host matrices;
- Windows service packaging and Windows Native beta soak testing.

Fake providers and deterministic tests cover these state transitions, but they are not substitutes for the named live qualification.
