# Codex Harbor v0.1 implementation map

This document maps the product specification to implemented code and verification. It distinguishes deterministic automated coverage from live Codex/account behavior.

## Phase coverage

| Phase | Implementation | Verification |
|---|---|---|
| 0 App Server PoC | `tools/app_server_poc.py`, async stdio client | Real two-process start/turn/resume/read/turn proof; output JSON is retained locally |
| 1 Persistent core | config, SQLite migrations, state machines, event store, CLI; v3 separates execution turns from counted failures and repairs historical `usageLimitExceeded` failures; v4 adds task groups, Codex Projects, shared Thread links, and workspace ownership; v5 persists Project-conversation mode, cwd, runtime roots, and direct-message behavior | storage/state/API and migration tests |
| 2 Codex runtime | v2 handshake and thread/turn/model methods | mocked protocol tests plus Phase 0 |
| 3 Single worker | transactional claim, heartbeat, attempts, logs/events, runtime-adjustable persisted parallelism | worker and persistence integration tests |
| 4 Recovery | envelope, stale worker, resume/fork/recovery-thread flow; every newly claimed Worker resumes its durable Thread before starting a Turn | recovery and quota-resume integration tests |
| 5 Fake quota | injectable `FakeQuotaProvider` | full Scheduler simulation of five-hour wait/release on a Luna task |
| 6 Real quota | `account/rateLimits/read` structured provider | deterministic structured-response tests plus live `doctor`/daemon parsing |
| 7 Weekly freeze | window identity comparison, draining generation, grandfathered set | full Scheduler simulation of weekly drain, automatic freeze, manual resume, and queued Luna execution |
| 8 Model/reasoning | live registry, profiles, overrides, pending next-turn values, attempt audit | registry and worker tests |
| 9 Dependency/workspace | dependency gate, terminal failure propagation, priority/FIFO, automatic same-workspace serialization, existing Project workspaces, and opt-in per-task Git worktrees | real temporary Git repositories and shared-workspace integration tests |
| 10 Acceptance | command runner, timeout, output capture, follow-up turn | acceptance and worker tests |
| 11 Linux/WSL2 | isolated execution backends | selection/unit coverage; full host matrix remains release validation |
| 12 Windows Native | executable resolution, paths, process tree, file-lock-safe SQLite | current Windows test run; remains beta |
| 13 Local API | loopback FastAPI endpoints | HTTP integration tests |
| 14 Dashboard | card-based lifecycle board with light/dark themes, persistent English/Simplified Chinese selection, remaining-first quota cards, and Project-driven existing/new conversation creation consuming only Local API | HTTP/API tests, emitted-JavaScript parser test, Edge visual QA |
| 15 Skill/plugin | Development plugin and `harbor-tasks` skill under `integrations/plugins/codex-harbor` | plugin/skill validation plus loopback API helper smoke test |
| 16 Project/task groups | Codex Project discovery, project-filtered conversation listing, immediate durable conversation creation with runtime workspace roots, direct first-message injection, atomic sequential groups, isolated/shared Session policy, many-to-many Task↔Thread links, and continuation prompt injection | generated-schema checks, live Project/list metadata proof, API/storage/Worker integration tests |

## Important implementation choices

The current Codex CLI-generated protocol schema is treated as the integration contract. The client sends newline-delimited messages without assuming an internal rollout JSONL format. It completes `initialize` then `initialized`, and uses durable, non-ephemeral threads.

The daemon owns one App Server process and shares it across workers. Each task owns its model/reasoning configuration; a worker never carries global mutable agent state between tasks.

### Task, Thread, Turn, and failure accounting

`tasks.current_attempt` is the monotonic execution sequence retained for schema compatibility. Each execution record may carry a Codex `thread_id` and `turn_id`. `tasks.failure_count` is the independent bounded-retry budget. A quota-limited Turn is stored with result `WAIT_QUOTA` and a rate-limit error type, but does not increment `failure_count`.

The default relationship is Task 1:1 Root Thread and Thread 1:N Turns. A shared-session task group deliberately makes Task:N ↔ Thread:1: after each predecessor succeeds, the successor links the same durable Thread and injects a continuation prompt containing the new objective. A Task may have additional Recovery/Fork Threads only when the active Thread cannot be resumed. Root and recovery threads are durable/non-ephemeral Codex threads, named `[task-id] title` or `[group-id] title`, assigned to the matching Codex Project, and retained in Codex's thread store. SQLite remains authoritative for scheduling; Codex remains authoritative for the conversation transcript.

The dashboard's primary creation contract is Project-driven. It either links an
existing Project Thread (preserving its name and cwd) or calls durable
`thread/start` immediately with `projectId` and `runtimeWorkspaceRoots`. The
selected primary cwd is resolved to its Git top-level for scheduling safety, but
Codex continues to run at the exact conversation cwd. The first Worker Turn sends
the user's single task message without an injected Harbor wrapper.

On a rate-limit error, the worker persists the Turn evidence and sets `resume_at` from the matching quota window reset (with a short anti-hot-loop fallback). The scheduler releases the task only after both `resume_at` has passed and all required quota windows are available. A fresh Worker always calls `thread/resume` before its first new Turn, including when `current_attempt` is greater than one.

The default `project` workspace is the existing originating conversation cwd when it belongs to the registered repository's Git common directory; otherwise it is the registered repository root. Tasks sharing it receive an automatic exclusive group. Harbor records that it does not own this workspace, so cleanup refuses it. `isolated` mode remains available for a Harbor-owned task worktree; success preserves both worktree and branch. Existing legacy worktree tasks are not relocated, which protects their uncommitted state. Automatic merge is intentionally out of scope.

For dependencies, `WAIT_QUOTA` remains a nonterminal pause and resumes the same Thread after the reset gate opens. A terminal upstream `FAILED`, `BLOCKED`, or `CANCELLED` state changes dependants to `BLOCKED` with `UPSTREAM_FAILED`. Retrying that upstream returns dependants to `WAIT_DEP`, and its eventual success releases them in dependency order.

## Release boundaries

- A real 5-hour exhaustion error has been captured and used as a regression fixture. The post-reset continuation path is deterministic-test validated, but the next naturally occurring live reset still needs observation before calling the build production-stable.
- Host reboot autostart requires platform service installation by the operator. Startup recovery is implemented, but this repository does not silently register a Windows service or systemd unit.
- Linux Native and WSL2 need CI or host-matrix validation. A Windows run cannot substantiate those host-specific guarantees.
- The local dashboard is deliberately lightweight instead of React/Vite; the required UI → API → daemon → scheduler separation is preserved.
- Interactive approvals are denied by the non-interactive worker and surface as blocked/failed task evidence instead of hanging indefinitely.
