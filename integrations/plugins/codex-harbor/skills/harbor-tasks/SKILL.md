---
name: harbor-tasks
description: Manage persistent Codex Harbor coding tasks through its loopback Local API. Use when the user asks to inspect Harbor, split work into Harbor tasks, create dependencies, change task model or reasoning, inspect quota, or pause, freeze, resume, retry, or cancel Harbor work. Do not use for ordinary Codex tasks that are not meant to enter Harbor.
---

# Harbor Tasks

Treat Harbor's SQLite-backed API as the task source of truth; do not infer state from the Codex sidebar. Default to `http://127.0.0.1:8765` and never redirect Harbor requests to a non-loopback address without the user's explicit configuration and authorization.

Use `scripts/harbor_api.py` for deterministic requests. Start read-only work by fetching `/api/pool`, `/api/tasks`, and only the task details needed. If Harbor is unreachable, report that the daemon must be started; do not silently start background services unless the user asked to run Harbor.

When creating tasks:

- Inspect enough repository context to produce concrete objectives and acceptance commands.
- Confirm the repository appears in `/api/repositories`; registering a repository is a separate mutation.
- Preserve the user's requested task boundaries. Add dependencies only where completion is genuinely required.
- Put model and reasoning configuration on each task. Use `null` for inheritance; never invent a model name or silently downgrade reasoning.
- Include acceptance commands that test observable outcomes. Do not mark a Task successful yourself; Harbor's Acceptance Runner owns that decision.
- Default `workspace_mode` to `project` so Harbor uses the current Codex Project/conversation workspace. Use `isolated` only when the user explicitly wants a separate Harbor worktree.
- When the user splits one objective into ordered Tasks, prefer `POST /api/task-groups`. Use `session_mode: shared` when later Tasks should inherit the preceding Codex conversation, or `isolated` when each Task needs its own Session.
- Include the current Codex Project ID and originating Thread ID when they are available. If only the Project root is known, Harbor discovers the matching Project; never guess a Thread ID.
- `origin_thread_id` alone records provenance, not a request to resume it. To continue a specific conversation, use `conversation_mode: existing` and `thread_id`. A Project ID is optional for this path. For automatic quota recovery of the current task, use the bundled `harbor-auto-resume` skill and `/api/recovery-watches`; do not submit an ordinary new task.
- Shared-session groups must be sequential. A terminal upstream failure blocks later Tasks; `WAIT_QUOTA` is resumable and does not permanently block the chain.

Project workspaces are user-owned existing checkouts. Tasks targeting the same
workspace are serialized automatically, and cleanup must never be requested for
them. Only Harbor-owned isolated worktrees are eligible for cleanup.

User requests such as “create,” “cancel,” “retry,” “pause,” “freeze,” or “resume” authorize that exact Harbor mutation. For ambiguous bulk mutations, show the affected task IDs and ask for the missing scope before writing. Reads do not require confirmation.

Pool state and Task state are independent. Explain that a frozen pool does not rewrite each Task status, quota wait is not failure, and weekly reset freeze is a graceful drain.

Read [references/api.md](references/api.md) only when constructing a request or interpreting a response beyond basic task listing.
