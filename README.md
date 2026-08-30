# Codex Harbor（代码港）

Codex Harbor is a local-first, persistent scheduler above Codex App Server. It keeps task state in SQLite, code state in Git worktrees, and recovery context in durable envelopes so task identity does not depend on a terminal, worker, Codex process, or Desktop sidebar.

> Status: v0.1 MVP implementation. Windows Native is beta. The real quota provider follows the current local Codex App Server protocol and should be revalidated when Codex is upgraded.

## Implemented capabilities

- Durable task, dependency, attempt, thread, worker, pool, quota, and event records in SQLite/WAL.
- Transactional claim, priority/FIFO scheduling, dependency gates, exclusive groups, and parallel workers.
- Task states including `WAIT_QUOTA`, `RETRY_WAIT`, `BLOCKED`, and terminal states.
- Independent pool states with weekly-reset `DRAINING`, grandfathered tasks, `FROZEN`, and manual resume.
- One shared Codex App Server process with `initialize`, `thread/start`, `turn/start`, `thread/read`, `thread/resume`, `thread/fork`, `model/list`, and `account/rateLimits/read`.
- Per-task model/reasoning configuration, dynamic capability validation, pending next-turn changes, and attempt-effective audit fields. No silent fallback.
- Registered-repository boundary and per-task `harbor/<task-id>` Git worktrees. Worktrees are preserved by default.
- Acceptance commands with follow-up turns and bounded attempts.
- Recovery envelopes, worker heartbeats, stale-worker recovery, process-tree termination, Linux/WSL/Windows execution backends.
- CLI, loopback-only FastAPI, and a lightweight local dashboard decoupled from scheduler logic.
- Redaction of authorization, API key, cookie, and password material before captured command output is persisted.

## Install

Python 3.11+ and a logged-in Codex CLI are required.

```bash
uv sync --extra dev
uv run harbor init
uv run harbor doctor
```

Override the data directory for an isolated instance:

```powershell
$env:HARBOR_DATA_DIR = 'D:\harbor-data'
uv run harbor init
```

Defaults are shown in `config.example.toml`. The API binds to `127.0.0.1:8765`; `0.0.0.0` is never the default.

## First task

Harbor only works in explicitly registered Git repositories.

```bash
uv run harbor repo add /path/to/project
uv run harbor task add --repo /path/to/project --title "Add parser" --prompt "Implement the parser" --reasoning high --accept "pytest -q"
uv run harbor daemon
```

Open <http://127.0.0.1:8765> or inspect from the CLI:

```bash
uv run harbor ps
uv run harbor task show T001
uv run harbor history T001
```

Task import accepts the YAML shape in `docs/task-example.yaml`.

## Phase 0: real persistence proof

This is intentionally separate from fake-runtime tests. It starts one App Server process, creates a durable thread and completes a turn, closes that process, starts a second process, resumes and reads the same thread, and completes another turn.

```bash
uv run python tools/app_server_poc.py --workspace .
```

Evidence is written to `.codex-harbor-poc/state.json` (ignored by Git). It contains process IDs, the stable thread ID, both turn states, and the persisted turn count. The PoC uses read-only sandboxing and asks Codex not to modify files.

## CLI summary

```text
harbor init
harbor repo add|list
harbor task add|import|list|show|config|retry|cancel|cleanup
harbor ps | quota | pause | freeze | resume
harbor run | daemon
harbor logs TASK | history TASK | doctor
```

`task cleanup` removes only the exact Harbor-owned worktree after validating its registered Git root; the branch is preserved.

## Development and verification

```bash
uv run pytest
uv run pytest --cov=codex_harbor --cov-report=term-missing
uv run harbor --help
uv run harbor doctor
```

The automated suite uses fake runtimes and quotas for deterministic state-machine testing. The App Server PoC is the real integration gate. See `docs/IMPLEMENTATION.md` for phase coverage and explicit boundaries.

## Safety boundaries

- SQLite is the control-plane source of truth; Codex chat history is not.
- Task and pool state remain separate.
- Quota exhaustion is a wait state, not a failure attempt.
- Model capability failures block the task rather than silently changing model or effort.
- Secrets remain owned by Codex authentication and are not stored by Harbor.
- Harbor does not automatically merge task branches or delete worktrees.

## License

Apache-2.0.
