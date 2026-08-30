# Codex Harbor v0.1 implementation map

This document maps the product specification to implemented code and verification. It distinguishes deterministic automated coverage from live Codex/account behavior.

## Phase coverage

| Phase | Implementation | Verification |
|---|---|---|
| 0 App Server PoC | `tools/app_server_poc.py`, async stdio client | Real two-process start/turn/resume/read/turn proof; output JSON is retained locally |
| 1 Persistent core | config, SQLite migrations, state machines, event store, CLI; v3 separates execution turns from counted failures and repairs historical `usageLimitExceeded` failures | storage/state/API and migration tests |
| 2 Codex runtime | v2 handshake and thread/turn/model methods | mocked protocol tests plus Phase 0 |
| 3 Single worker | transactional claim, heartbeat, attempts, logs/events, runtime-adjustable persisted parallelism | worker and persistence integration tests |
| 4 Recovery | envelope, stale worker, resume/fork/recovery-thread flow; every newly claimed Worker resumes its durable Thread before starting a Turn | recovery and quota-resume integration tests |
| 5 Fake quota | injectable `FakeQuotaProvider` | quota transition tests |
| 6 Real quota | `account/rateLimits/read` structured provider | live `doctor`/daemon, schema-grounded parsing |
| 7 Weekly freeze | window identity comparison, draining generation, grandfathered set | pool controller tests |
| 8 Model/reasoning | live registry, profiles, overrides, pending next-turn values, attempt audit | registry and worker tests |
| 9 Dependency/worktree | dependency gate, priority/FIFO, exclusive groups, per-task Git worktree | real temporary Git repositories |
| 10 Acceptance | command runner, timeout, output capture, follow-up turn | acceptance and worker tests |
| 11 Linux/WSL2 | isolated execution backends | selection/unit coverage; full host matrix remains release validation |
| 12 Windows Native | executable resolution, paths, process tree, file-lock-safe SQLite | current Windows test run; remains beta |
| 13 Local API | loopback FastAPI endpoints | HTTP integration tests |
| 14 Dashboard | card-based lifecycle board with light/dark themes, persistent English/Simplified Chinese selection, and remaining-first quota cards consuming only Local API | HTTP/API tests, emitted-JavaScript parser test, Edge visual QA |
| 15 Skill/plugin | Development plugin and `harbor-tasks` skill under `integrations/plugins/codex-harbor` | plugin/skill validation plus loopback API helper smoke test |

## Important implementation choices

The current Codex CLI-generated protocol schema is treated as the integration contract. The client sends newline-delimited messages without assuming an internal rollout JSONL format. It completes `initialize` then `initialized`, and uses durable, non-ephemeral threads.

The daemon owns one App Server process and shares it across workers. Each task owns its model/reasoning configuration; a worker never carries global mutable agent state between tasks.

### Task, Thread, Turn, and failure accounting

`tasks.current_attempt` is the monotonic execution sequence retained for schema compatibility. Each execution record may carry a Codex `thread_id` and `turn_id`. `tasks.failure_count` is the independent bounded-retry budget. A quota-limited Turn is stored with result `WAIT_QUOTA` and a rate-limit error type, but does not increment `failure_count`.

The normal relationship is Task 1:1 Root Thread and Thread 1:N Turns. A Task may have additional Recovery/Fork Threads only when the active Thread cannot be resumed. Root and recovery threads are durable/non-ephemeral Codex threads, named `[task-id] title`, and remain in Codex's thread store. SQLite remains authoritative for scheduling; Codex remains authoritative for the conversation transcript.

On a rate-limit error, the worker persists the Turn evidence and sets `resume_at` from the matching quota window reset (with a short anti-hot-loop fallback). The scheduler releases the task only after both `resume_at` has passed and all required quota windows are available. A fresh Worker always calls `thread/resume` before its first new Turn, including when `current_attempt` is greater than one.

Worktree cleanup is explicit. Success preserves both worktree and branch. Automatic merge is intentionally out of scope.

## Release boundaries

- A real 5-hour exhaustion error has been captured and used as a regression fixture. The post-reset continuation path is deterministic-test validated, but the next naturally occurring live reset still needs observation before calling the build production-stable.
- Host reboot autostart requires platform service installation by the operator. Startup recovery is implemented, but this repository does not silently register a Windows service or systemd unit.
- Linux Native and WSL2 need CI or host-matrix validation. A Windows run cannot substantiate those host-specific guarantees.
- The local dashboard is deliberately lightweight instead of React/Vite; the required UI → API → daemon → scheduler separation is preserved.
- Interactive approvals are denied by the non-interactive worker and surface as blocked/failed task evidence instead of hanging indefinitely.
