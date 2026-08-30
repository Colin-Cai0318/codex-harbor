# Harbor Local API reference

Base URL: `http://127.0.0.1:8765`

| Purpose | Method and path |
|---|---|
| Repositories | `GET /api/repositories`, `POST /api/repositories` |
| Tasks | `GET /api/tasks`, `GET /api/tasks/{id}`, `POST /api/tasks` |
| Task groups | `GET /api/task-groups`, `GET /api/task-groups/{id}`, `POST /api/task-groups` |
| Agent config | `PATCH /api/tasks/{id}/agent` |
| Lifecycle | `POST /api/tasks/{id}/retry`, `POST /api/tasks/{id}/cancel` |
| Pool | `GET /api/pool`, `PATCH /api/pool`, `POST /api/pool/pause`, `/freeze`, `/resume` |
| Runtime | `GET /api/quota`, `GET /api/models`, `GET /api/profiles`, `GET /api/workers`, `GET /api/codex/projects`, `GET /api/codex/projects/{id}/threads` |
| History | `GET /api/events?task_id=T001&limit=200` |

Project-driven task creation body (preferred):

```json
{
  "codex_project_id": "01a05029-18b6-7b32-bcce-6367259f1f3d",
  "conversation_mode": "existing",
  "thread_id": "01a05029-2856-77b1-b099-6262d7ca67cd",
  "message": "Continue this conversation and implement the requested change.",
  "priority": 100,
  "depends_on": [],
  "acceptance_commands": [],
  "max_attempts": 5,
  "model": null,
  "reasoning_effort": null,
  "execution_backend": "local"
}
```

For `"conversation_mode": "new"`, omit `thread_id` and supply:

```json
{
  "primary_workspace": "E:\\Tools\\Codex_Harbor",
  "workspace_roots": [
    "E:\\Tools\\Codex_Harbor",
    "F:\\shared-context"
  ]
}
```

The primary workspace must be inside a Git checkout. Harbor auto-registers its
Git top-level, starts a durable Thread assigned to the selected Project, and
sends `message` verbatim on the first Turn. Existing conversations keep their
Thread ID, name, history, and cwd.

Legacy task creation body:

```json
{
  "title": "Implement parser",
  "repository": "/absolute/registered/repository",
  "prompt": "Concrete objective and constraints",
  "description": "Optional context",
  "execution_backend": "local",
  "priority": 100,
  "depends_on": [],
  "exclusive_group": null,
  "acceptance_commands": ["pytest -q"],
  "max_attempts": 5,
  "model": null,
  "reasoning_effort": "high",
  "profile": null,
  "codex_project_id": null,
  "origin_thread_id": null,
  "session_parent_task_id": null,
  "reuse_parent_worktree": false,
  "workspace_mode": "project"
}
```

`workspace_mode` is `project` (existing Codex/registered workspace), `isolated`
(new Harbor-owned worktree), or `inherit` (reuse a session parent's workspace).
For a manually chained task, `session_parent_task_id` automatically becomes a
dependency and causes the task to reuse that parent's Codex Thread.

Ordered shared-session group body:

```json
{
  "title": "Feature implementation",
  "repository": "E:\\Tools\\Codex_Harbor",
  "session_mode": "shared",
  "workspace_mode": "project",
  "sequential": true,
  "codex_project_id": null,
  "origin_thread_id": null,
  "tasks": [
    {
      "title": "Database",
      "prompt": "Implement the schema changes",
      "priority": 10,
      "acceptance_commands": ["uv run pytest -q"]
    },
    {
      "title": "Scheduler",
      "prompt": "Continue with the scheduler changes",
      "priority": 20,
      "acceptance_commands": ["uv run pytest -q"]
    }
  ]
}
```

The server adds sequential dependencies atomically. In `shared` mode each later
Task links the predecessor's durable Codex Thread and injects its new prompt only
after the predecessor succeeds. Terminal upstream failure blocks dependants;
quota wait keeps the chain pending and resumes the same Thread after reset.

`priority` sorts ascending, then FIFO: 10 critical, 50 high, 100 normal, 200 low. `reasoning_effort` is one of `default`, `minimal`, `low`, `medium`, `high`, or `xhigh`, subject to the selected model's live capability record.

Patch only fields the user intends to change. Explicit JSON `null` restores inheritance. While a turn is running, the API records the value as pending for the next turn.
