# Codex Harbor v0.1 implementation map

This document maps the product specification to implemented code and verification. It distinguishes deterministic automated coverage from live Codex/account behavior.

## Phase coverage

| Phase | Implementation | Verification |
|---|---|---|
| 0 App Server PoC | `tools/app_server_poc.py`, async stdio client | Real two-process start/turn/resume/read/turn proof; output JSON is retained locally |
| 1 Persistent core | config, SQLite migration, state machines, event store, CLI | storage/state/API tests |
| 2 Codex runtime | v2 handshake and thread/turn/model methods | mocked protocol tests plus Phase 0 |
| 3 Single worker | transactional claim, heartbeat, attempts, logs/events | worker integration tests |
| 4 Recovery | envelope, stale worker, resume/fork/recovery-thread flow | recovery unit/integration tests |
| 5 Fake quota | injectable `FakeQuotaProvider` | quota transition tests |
| 6 Real quota | `account/rateLimits/read` structured provider | live `doctor`/daemon, schema-grounded parsing |
| 7 Weekly freeze | window identity comparison, draining generation, grandfathered set | pool controller tests |
| 8 Model/reasoning | live registry, profiles, overrides, pending next-turn values, attempt audit | registry and worker tests |
| 9 Dependency/worktree | dependency gate, priority/FIFO, exclusive groups, per-task Git worktree | real temporary Git repositories |
| 10 Acceptance | command runner, timeout, output capture, follow-up turn | acceptance and worker tests |
| 11 Linux/WSL2 | isolated execution backends | selection/unit coverage; full host matrix remains release validation |
| 12 Windows Native | executable resolution, paths, process tree, file-lock-safe SQLite | current Windows test run; remains beta |
| 13 Local API | loopback FastAPI endpoints | HTTP integration tests |
| 14 Dashboard | lightweight HTML dashboard consuming only Local API | HTTP render/API tests |
| 15 Skill/plugin | Development plugin and `harbor-tasks` skill under `integrations/plugins/codex-harbor` | plugin/skill validation plus loopback API helper smoke test |

## Important implementation choices

The current Codex CLI-generated protocol schema is treated as the integration contract. The client sends newline-delimited messages without assuming an internal rollout JSONL format. It completes `initialize` then `initialized`, and uses durable, non-ephemeral threads.

The daemon owns one App Server process and shares it across workers. Each task owns its model/reasoning configuration; a worker never carries global mutable agent state between tasks.

Worktree cleanup is explicit. Success preserves both worktree and branch. Automatic merge is intentionally out of scope.

## Release boundaries

- Real 5-hour and weekly exhaustion cannot be manufactured safely. Automated tests use the fake provider; live reset behavior must be observed across actual account windows before calling a build production-stable.
- Host reboot autostart requires platform service installation by the operator. Startup recovery is implemented, but this repository does not silently register a Windows service or systemd unit.
- Linux Native and WSL2 need CI or host-matrix validation. A Windows run cannot substantiate those host-specific guarantees.
- The local dashboard is deliberately lightweight instead of React/Vite; the required UI → API → daemon → scheduler separation is preserved.
- Interactive approvals are denied by the non-interactive worker and surface as blocked/failed task evidence instead of hanging indefinitely.
