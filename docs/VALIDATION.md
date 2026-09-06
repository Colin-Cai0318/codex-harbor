# Validation record

Latest check (2026-09-06): **84 passed, 87% statement coverage**. See the
[maintenance review](REVIEW-2026-09-06.md) for the new concurrency and recovery
regressions. The dated results below describe the earlier August validation.

Date: 2026-08-30 (updated 2026-08-31)
Host: Windows Native
Codex CLI: 0.149.1
Python: CPython 3.14.6 (local validation)

## Automated suite

Command:

```text
uv run pytest -q
```

Result: 73 passed, 86% statement coverage (335 dependency deprecation warnings on Python 3.14). The suite covers state transitions, dependency release and terminal-failure propagation, transactional admission behavior, priority, exclusive groups, persisted runtime parallelism, weekly drain/freeze/resume semantics, structured Codex quota parsing, model capability rejection, pending agent configuration, secret sanitization, HTTP API/dashboard rendering, emitted JavaScript syntax, Project-filtered conversation listing, durable new-conversation creation, runtime workspace roots, exact conversation-cwd preservation, raw first-message injection into an existing conversation, schema-v5 persistence, real temporary Git worktrees, existing Project workspace reuse, shared-session prompt injection, Task↔Thread many-to-many links, atomic YAML task-group import, Acceptance Runner behavior, Worker thread/turn/envelope persistence, quota wait/resume on the same Thread, historical quota-failure migration, successful/blocked outcomes, and the fault-injection matrix below.

## Simulated quota lifecycle (2026-08-31)

The quota tests use an isolated temporary SQLite database, `FakeQuotaProvider`,
and tasks explicitly configured with `gpt-5.6-luna`/`low`. They do not edit the
live account windows or consume model quota.

### Five-hour reset

1. A Luna task was linked to `thread-before-limit`, moved to `WAIT_QUOTA` with
   `RATE_LIMIT_5H`, and given an elapsed `resume_at`.
2. While the primary five-hour window remained unavailable, a real
   `Scheduler.tick()` left it in `WAIT_QUOTA` and started no Worker.
3. The provider was advanced to a new available window. The next scheduler tick
   changed `WAIT_QUOTA → READY`, claimed the task, and completed it.
4. The Root Thread remained `thread-before-limit`; `failure_count` remained 0;
   the completing Worker observed requested model `gpt-5.6-luna`.

The existing Worker regression was also changed to Luna/low. It retains the
real `usageLimitExceeded` fixture, records two Attempts, and proves that a new
Worker calls `thread/resume` on the same `thread-quota` after availability
returns. Both Attempts retain effective model `gpt-5.6-luna` and reasoning
`low`.

### Weekly reset, automatic freeze, and manual resume

1. The simulated weekly boundary was crossed while T001 was `RUNNING` and T002
   was `READY`. The scheduler changed the pool to `DRAINING`, marked only T001
   as grandfathered, and did not start T002.
2. After T001 reached `SUCCEEDED`, the next tick emitted `POOL_FROZEN` and set
   the pool to `FROZEN`; T002 remained `READY` and unclaimed.
3. A manual pool resume emitted `POOL_RESUMED`. The following tick claimed and
   completed T002 with `gpt-5.6-luna`, while the pool remained `RUNNING`.

The persisted event set contains `WEEKLY_WINDOW_CHANGED`, `POOL_DRAINING`,
`POOL_FROZEN`, and `POOL_RESUMED`.

### Structured provider coverage

Deterministic provider tests now cover primary-window exhaustion, weekly
remaining calculation, reset epoch conversion, `rateLimitReachedType`, global
spend-control blocking, absent reset timestamps, and targeted Fake-provider
exhaustion. `quota/manager.py` is 94% covered and `quota/provider.py` is 96%
covered.

## Real Luna smoke task

Live task T005 created a new Codex-visible conversation in the existing Codex
Harbor Project and used requested/effective model `gpt-5.6-luna` with reasoning
`low`. Its Root Thread is `01a054d0-d6d5-7a31-8bfd-cfc82ba3ee3c`.

The first Turn completed but did not satisfy the exact-file acceptance command,
so Harbor recorded `ACCEPTANCE_FAILED` and automatically injected a follow-up
Turn into the same Thread. The second Turn created the expected CRLF-terminated
file, both acceptance commands passed, and T005 ended `SUCCEEDED` with two
Attempts and one counted acceptance failure. This is a live confirmation of
same-Thread acceptance recovery, not a claim that a real quota reset occurred.

## Simulated fault-injection matrix (2026-08-31)

All cases below use temporary repositories/databases or in-process fakes. They
do not submit a real Codex Turn, change the live Harbor database, or consume
model quota.

| Boundary | Injected failure | Verified behavior |
|---|---|---|
| App Server transport | write failure, request timeout, error response, malformed JSON, stdout close, notification timeout | Errors propagate; pending requests and notification waiters are removed; malformed lines are ignored without stopping the reader |
| App Server requests | approval and unknown interactive requests | Non-interactive Harbor declines approval and returns JSON-RPC method-not-found for unsupported prompts instead of hanging |
| Runtime/Session | failed `thread/resume`, successful/failed `thread/fork`, malformed Thread/Turn IDs, wait failure, interrupt | Recovery first forks the existing session, then creates a new recovery Thread only if both resume and fork fail; active-Turn bookkeeping is always cleared |
| Recovery Manager | stale heartbeat/dead PID beside a live PID | Only the stale task returns to `READY`; `TASK_RECOVERY_QUEUED` and `WORKER_DIED` are persisted; the live Worker remains registered |
| Worker outcomes | auth, network, generic runtime failure, cancellation during Turn, repeated acceptance failure | Auth blocks, network enters delayed retry, exhausted generic/acceptance failures fail, cancellation remains cancelled, and Worker rows/claims are cleaned |
| Scheduler | crashed Worker future, interrupt transport error, quota-provider exception, expired retry, stop with active future | Each failure is isolated and recorded; scheduling survives; retry is released; stop waits for active work |
| Execution | real local command timeout, missing PID termination, simulated WSL success/timeout, unsupported backend | Timeout returns 124 and terminates the process tree; WSL invocation shape and timeout are deterministic; unsupported backend is rejected |
| Worktree | unregistered/nested repository, missing/conflicting directory, another repository, Git failure, unsafe cleanup | Every invalid path is rejected. Existing Harbor-owned directories are now Git-root and common-repository validated before reuse |
| API | App Server unavailable, missing/mismatched Project or conversation, absent/non-Git workspace, malformed `thread/start`, invalid controls | Responses use explicit 404/409/502/503 boundaries; a partially created task is rolled back if Thread creation is malformed |
| Daemon | normal server return and bind failure | Scheduler task is cancelled, `scheduler.stop()` runs, and the App Server context closes in both cases |
| CLI/config | malformed TOML/YAML, missing fields, invalid cleanup/config, control commands, quota display | Invalid inputs fail explicitly; normal control paths persist; CLI quota output now shows remaining allowance instead of used allowance |

The simulations found and fixed three production defects: App Server write
failures leaked `_pending` futures, notification timeouts leaked waiter entries,
and a pre-existing directory under the Harbor worktree root could be reused
without proving Git ownership. The CLI's primary quota display was also aligned
with the dashboard by showing remaining allowance.

## Remaining coverage gaps

The suite moved from 68% before quota work, through 70%, to 86%. Remaining risk
is now concentrated in live process/host behavior and low-frequency storage
combinations:

| Area | Coverage | Remaining qualification |
|---|---:|---|
| Codex App Server client | 63% | real subprocess startup/close escalation and additional live protocol-version response shapes |
| Daemon lifecycle | 79% | OS signal delivery and initialization failure before scheduler construction |
| Recovery Manager / Worker | 100% / 87% | destructive real-process kill during active edits and rare Project-metadata/inherited-workspace error combinations |
| CLI / Local API | 73% / 92% | subprocess-level `doctor`, `run`, `daemon`, and parser exit formatting; several low-risk endpoint variants |
| Execution / Scheduler | 93% / 94% | Linux Native host matrix, real WSL process tree, and long-running `run_forever` soak |
| Git worktree manager | 83% | real locked-file cleanup and existing-branch worktree-add behavior |
| Storage / repository / config | 89% / 93% / 89% | older partial-schema permutations, forced rollback faults, and high-contention multi-process SQLite claims |

`__main__.py` reports 0%, but it is only the four-line CLI entry point and is not
a material risk. Live `doctor`, daemon, Edge, and App Server smoke proofs exercise
some paths that coverage.py cannot attribute because they run in separate
processes.

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
the named proof files are untracked test outputs. The daemon was shut down
cleanly after recording the results.

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
