<div align="center">

# ⚓ Codex Harbor

### Durable task orchestration for Codex

Turn Codex sessions into persistent, schedulable coding tasks—with durable state,
isolated Git worktrees, quota-aware execution, and recovery across processes.

[![CI](https://github.com/Colin-Cai0318/codex-harbor/actions/workflows/ci.yml/badge.svg)](https://github.com/Colin-Cai0318/codex-harbor/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-v0.1%20MVP-orange)](#project-status)
[![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20WSL-555)](#requirements)

**English** · [简体中文](README.zh-CN.md)

</div>

---

Codex Harbor is a local-first control plane built on top of Codex App Server.
SQLite preserves control-plane state, Git worktrees isolate code changes, and
recovery envelopes keep task identity independent of a terminal, worker,
Codex process, or Desktop sidebar.

> [!IMPORTANT]
> Codex Harbor is an MVP. Windows Native is currently beta, and live quota
> behavior should be revalidated after upgrading the Codex CLI.

## Table of contents

- [Why Codex Harbor?](#why-codex-harbor)
- [Architecture](#architecture)
- [Task, session, and turn model](#task-session-and-turn-model)
- [Features](#features)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Register a local repository](#register-a-local-repository)
- [Configuration](#configuration)
- [Task files](#task-files)
- [CLI reference](#cli-reference)
- [Codex plugin](#codex-plugin)
- [Persistence and recovery](#persistence-and-recovery)
- [Development and verification](#development-and-verification)
- [Safety boundaries](#safety-boundaries)
- [Project status](#project-status)

## Why Codex Harbor?

A normal interactive Codex session is tied to a running client. Harbor gives
long-running and multi-repository work a durable lifecycle:

| Need | Harbor behavior |
|---|---|
| Survive restarts | Persists tasks, attempts, Codex threads, workers, quota, and events in SQLite/WAL |
| Run safely in parallel | Claims tasks transactionally and gives each task its own Git worktree |
| Respect ordering | Supports dependencies, priority + FIFO ordering, and exclusive groups |
| Handle quota pauses | Uses separate task and pool state machines with wait, drain, freeze, and resume states |
| Keep agent choices explicit | Validates model/reasoning capabilities dynamically; never silently falls back |
| Prove completion | Runs acceptance commands and can feed failures back into bounded follow-up turns |

## Architecture

```mermaid
flowchart LR
    U[Developer / Codex] --> CLI[CLI]
    U --> UI[Local Dashboard]
    U --> PL[Codex Plugin]
    UI --> API[Loopback API<br/>127.0.0.1:8765]
    PL --> API
    CLI --> D[Harbor Daemon]
    API --> D
    D --> S[Scheduler + Pool Controller]
    S --> W[Worker Pool]
    W --> AS[Codex App Server]
    W --> WT[Per-task Git Worktrees]
    D --> DB[(SQLite / WAL)]
    W --> DB
```

The daemon owns one shared App Server process. Workers retain task-scoped model
and reasoning configuration, so agent state never leaks between tasks.

## Task, session, and turn model

Harbor does not replace Codex sessions. It schedules work into durable Codex
threads created through App Server, so the transcript remains in Codex's own
thread store and can be recognized in the Codex app as `[T001] Task title`.
Harbor's dashboard adds lifecycle and quota control; it is not a second chat
history implementation.

| Harbor/Codex object | Meaning | Lifetime |
|---|---|---|
| Task | Business objective, repository, prompt, acceptance, dependencies, and scheduling state | Until explicitly deleted |
| Root Thread | The task's primary Codex session and conversation history | Reused across Worker and App Server restarts |
| Recovery Thread | A fork/new thread used only if the prior thread cannot be resumed | Linked to the same Task |
| Turn | One prompt execution inside a Thread | Recorded with its Thread and execution number |
| Counted failure | A runtime or acceptance failure that consumes the configured retry budget | Separate from the Turn count |

The normal mapping is one Task to one Root Thread, with multiple Turns over
time. The first Turn receives the full task envelope. Acceptance feedback and
quota-reset recovery prompts are injected as later Turns in that same Thread.
Quota exhaustion is recorded as `WAIT_QUOTA`; its Turn remains visible, but it
does not increment the counted-failure budget.

```mermaid
flowchart LR
    T[Harbor Task] --> R[Codex Root Thread]
    R --> A[Turn 1: full task prompt]
    A --> Q[WAIT_QUOTA]
    Q -->|5-hour window available| B[thread/resume]
    B --> C[Turn 2: recovery prompt]
    C --> V[Acceptance]
```

If the daemon or App Server stops while waiting, SQLite retains the Task ↔
Thread mapping. After restart, the scheduler waits for the persisted reset time
and live quota availability, then calls `thread/resume` before starting the next
Turn. It does not create a detached replacement session merely because quota
was exhausted.

## Features

### Persistent scheduling

- Durable repositories, tasks, dependencies, attempts, threads, workers, quota,
  pool state, and event records.
- Transactional task admission with priority/FIFO ordering.
- Dependency gates, exclusive groups, parallel workers, bounded retry, and
  acceptance-command follow-up.
- Independent task states such as `WAIT_QUOTA`, `RETRY_WAIT`, and `BLOCKED`, plus
  pool states such as `DRAINING` and `FROZEN`.
- A runtime-adjustable, persisted maximum parallel-task limit (1–64).

### Native Codex integration

- Implements App Server initialization and durable thread/turn operations.
- Starts, reads, resumes, and forks Codex threads without relying on internal
  rollout JSONL files.
- Loads the live model registry and validates reasoning-effort support.
- Reads structured account rate limits through the current App Server protocol.

### Isolation, recovery, and observability

- Creates `harbor/<task-id>` branches in Harbor-owned Git worktrees.
- Supports local Linux, Windows Native, and WSL execution backends.
- Persists recovery envelopes and detects stale worker heartbeats.
- Captures task history and command output after redacting authorization,
  API-key, cookie, and password material.
- Provides a loopback-only FastAPI service and a card-based lifecycle dashboard
  with light/dark themes and a persistent English/Simplified Chinese language
  selector. Quota cards emphasize the remaining allowance.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- Git
- An installed and authenticated Codex CLI

Harbor currently targets Windows Native, Linux Native, and WSL2. Windows Native
is beta; see [Project status](#project-status) for qualification boundaries.

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/Colin-Cai0318/codex-harbor.git
cd codex-harbor
uv sync --extra dev
```

### 2. Initialize and verify the runtime

```bash
uv run harbor init
uv run harbor doctor
```

### 3. Register a repository and create a task

Harbor registers an existing local Git checkout, not a GitHub URL. For example:

```powershell
uv run harbor repo add "F:\BossHunter"

uv run harbor task add `
  --repo "F:\BossHunter" `
  --title "Improve BossHunter documentation" `
  --prompt "Document installation, startup, and verification without changing application code" `
  --backend windows `
  --reasoning high `
  --accept "git diff --check"
```

See [Register a local repository](#register-a-local-repository) for the full
path/remote distinction, validation commands, expected output, and troubleshooting.

### 4. Start Harbor

```bash
uv run harbor daemon
```

Open <http://127.0.0.1:8765> for the dashboard, or inspect the same state from
another terminal:

```bash
uv run harbor ps
uv run harbor task show T001
uv run harbor history T001
```

## Register a local repository

### Local path versus GitHub URL

Harbor currently accepts a local path only. A GitHub URL is managed by Git for
clone, pull, and push operations; it is not passed to `harbor repo add`.

| Value | BossHunter example | Used directly by Harbor |
|---|---|---|
| Local Git checkout | `F:\BossHunter` | Yes, for registration and task creation |
| GitHub repository | [`Colin-Cai0318/BossHunter`](https://github.com/Colin-Cai0318/BossHunter) | No, it remains a Git remote |
| Harbor database | `%LOCALAPPDATA%\CodexHarbor\harbor.db` by default | Yes, it stores registrations and task state |

`repo add` does not clone a repository. If the local checkout does not exist,
clone it first:

```powershell
git clone https://github.com/Colin-Cai0318/BossHunter "F:\BossHunter"
```

### 1. Validate the local checkout

```powershell
Test-Path -LiteralPath "F:\BossHunter"
git -C "F:\BossHunter" rev-parse --show-toplevel
git -C "F:\BossHunter" rev-parse --verify HEAD
git -C "F:\BossHunter" remote -v
```

The first command should print `True`, the second should identify
`F:/BossHunter`, and the third should resolve a commit. The remote can be named
`origin`, `fork`, or anything else; Harbor does not depend on the remote name.

> [!WARNING]
> A Harbor task worktree starts from the repository's committed `HEAD`.
> Uncommitted and untracked files in the source checkout are not copied into the
> task worktree automatically.

### 2. Register it from the Codex Harbor checkout

```powershell
cd "E:\Tools\Codex_Harbor"
uv run harbor repo add "F:\BossHunter"
```

Successful output resembles:

```json
{
  "path": "F:\\BossHunter",
  "name": "BossHunter",
  "added_at": "2026-08-30T09:00:00+00:00"
}
```

Repeating the command is safe: it updates the registration for the same path;
it does not copy or modify the source checkout. The daemon does not need to be
running for registration.

### 3. Verify registration

```powershell
uv run harbor repo list
```

The output should contain `F:\\BossHunter`. If the dashboard is already open,
refresh it. The Create Task repository selector will then show
`BossHunter — F:\BossHunter`.

### 4. Create and run an example task

```powershell
uv run harbor task add `
  --repo "F:\BossHunter" `
  --title "Improve BossHunter documentation" `
  --prompt "Document installation, startup, and verification without changing application code. Summarize the result." `
  --backend windows `
  --reasoning high `
  --accept "git diff --check"

uv run harbor daemon
```

Open <http://127.0.0.1:8765>, or inspect the task from another terminal:

```powershell
uv run harbor task list
uv run harbor ps
```

### Troubleshooting

| Symptom | Cause and resolution |
|---|---|
| `repository does not exist` | The local path is wrong; verify the drive and directory, and quote paths containing spaces |
| `repository is not registered` | The task uses another path or another Harbor data directory; rerun `repo add` and inspect `repo list` |
| `repo list` is still empty | The CLI and daemon may use different `HARBOR_DATA_DIR` or `--config` values; both must use the same configuration |
| A GitHub URL cannot be registered | This is expected; clone it and register the resulting local directory |
| Local uncommitted changes are missing | Worktrees start from committed `HEAD`; commit the changes that the task must see |
| The dashboard selector has no new repository | Refresh the page; repository options load when the page starts |

## Configuration

The generated configuration follows [`config.example.toml`](config.example.toml).
Important defaults are deliberately conservative:

| Setting | Default | Purpose |
|---|---:|---|
| `harbor.bind` | `127.0.0.1` | Keeps the dashboard and API on loopback |
| `harbor.port` | `8765` | Local dashboard/API port |
| `scheduler.max_workers` | `3` | Maximum concurrent workers |
| `quota.provider` | `codex` | Reads structured Codex account rate limits |
| `quota.freeze_on_weekly_reset` | `true` | Drains grandfathered work before freezing at a weekly reset |
| `codex.approval_policy` | `never` | Prevents unattended workers from hanging on approval prompts |
| `codex.sandbox` | `workspace-write` | Restricts agent writes to its task workspace |

`scheduler.max_workers` seeds a new database. After initialization, the value
can be changed live from the dashboard and is retained in Harbor's database.

Use an isolated data directory when testing another Harbor instance:

```powershell
$env:HARBOR_DATA_DIR = 'D:\harbor-data'
uv run harbor init
```

## Task files

Tasks can be created individually or imported from YAML:

```bash
uv run harbor task import docs/task-example.yaml
```

```yaml
id: T001
title: Add watchdog parser
repository:
  path: /absolute/path/to/repository
execution:
  backend: local
agent:
  model: null
  reasoning_effort: high
priority: 50
depends_on: []
exclusive_group: watchdog-parser
prompt: Implement the parser and preserve existing behavior.
acceptance:
  commands:
    - pytest tests/watchdog -q
max_attempts: 5
```

Lower priority numbers run first; tasks with equal priority use FIFO order.
`max_attempts` is the counted-failure retry limit; quota-wait Turns do not
consume it.

## CLI reference

| Command | Purpose |
|---|---|
| `harbor init` | Create the data directory, database, and default configuration |
| `harbor repo add\|list` | Register or list eligible Git repositories |
| `harbor task add\|import\|list\|show` | Create and inspect tasks |
| `harbor task config` | Change the task model or reasoning effort |
| `harbor task retry\|cancel\|cleanup` | Control task lifecycle and owned worktrees |
| `harbor ps` | Show pool, workers, and active tasks |
| `harbor quota` | Show the latest persisted quota windows |
| `harbor pause\|freeze\|resume` | Control pool admission |
| `harbor run` | Run the scheduler until the current work is settled |
| `harbor daemon` | Run the scheduler and local dashboard continuously |
| `harbor logs TASK` | Read persisted task output |
| `harbor history TASK` | Read the task event timeline |
| `harbor doctor` | Validate Python, Git, SQLite, Codex, models, quota, and execution backends |

Run `uv run harbor <command> --help` for complete arguments.

## Codex plugin

The repository includes a validated development plugin at
[`integrations/plugins/codex-harbor`](integrations/plugins/codex-harbor). Its
`harbor-tasks` skill lets Codex inspect and manage the pool through Harbor's
loopback API while preserving the same scheduler and safety boundaries as the
CLI and dashboard.

The API contract and a dependency-free helper are included under the plugin's
[`references`](integrations/plugins/codex-harbor/skills/harbor-tasks/references/api.md)
and [`scripts`](integrations/plugins/codex-harbor/skills/harbor-tasks/scripts/harbor_api.py)
directories.

## Persistence and recovery

Harbor treats SQLite as the control-plane source of truth and a Codex thread as
durable execution context. The Phase 0 proof starts an App Server process,
completes a turn, stops the process, starts a different process, resumes the
same thread, reads its persisted history, and completes another turn:

```bash
uv run python tools/app_server_poc.py --workspace .
```

Machine-local proof data is written to `.codex-harbor-poc/state.json` and is
ignored by Git.

## Development and verification

```bash
uv run pytest -q
uv run pytest --cov=codex_harbor --cov-report=term-missing
uv run python -m compileall -q src tools tests
uv run harbor doctor
```

The CI matrix covers Ubuntu and Windows with Python 3.11 and 3.13. Deterministic
tests use fake runtimes and quota providers; the App Server proof is the live
integration gate.

- [Implementation map](docs/IMPLEMENTATION.md)
- [Validation record](docs/VALIDATION.md)
- [Example task](docs/task-example.yaml)

## Safety boundaries

> [!WARNING]
> Harbor deliberately does not auto-merge task branches or delete successful
> worktrees. Cleanup is always explicit.

- SQLite—not chat history—is the control-plane source of truth.
- Task state and pool state remain separate.
- Quota exhaustion is a wait state and recorded Turn, not a counted failure.
- Unsupported model capabilities block a task instead of changing its model.
- Codex authentication remains owned by Codex; Harbor does not store its secrets.
- `task cleanup` validates the registered Git root and removes only the exact
  Harbor-owned worktree; it preserves the branch.
- The API binds to loopback by default and never defaults to `0.0.0.0`.

## Project status

Codex Harbor v0.1 is a working MVP. Automated tests, a real two-process App
Server recovery proof, a real isolated worktree task, and the loopback API have
been validated on Windows Native.

The following remain release-qualification work and are not claimed as fully
validated: a real 5-hour/weekly quota exhaustion cycle, destructive process-kill
and host-reboot testing, Linux/WSL host soak testing, and Windows service
packaging. See the [validation record](docs/VALIDATION.md) for exact evidence.

## License

Licensed under the [Apache License 2.0](LICENSE).
