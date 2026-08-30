# Harbor Local API reference

Base URL: `http://127.0.0.1:8765`

| Purpose | Method and path |
|---|---|
| Repositories | `GET /api/repositories`, `POST /api/repositories` |
| Tasks | `GET /api/tasks`, `GET /api/tasks/{id}`, `POST /api/tasks` |
| Agent config | `PATCH /api/tasks/{id}/agent` |
| Lifecycle | `POST /api/tasks/{id}/retry`, `POST /api/tasks/{id}/cancel` |
| Pool | `GET /api/pool`, `PATCH /api/pool`, `POST /api/pool/pause`, `/freeze`, `/resume` |
| Runtime | `GET /api/quota`, `GET /api/models`, `GET /api/profiles`, `GET /api/workers` |
| History | `GET /api/events?task_id=T001&limit=200` |

Task creation body:

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
  "profile": null
}
```

`priority` sorts ascending, then FIFO: 10 critical, 50 high, 100 normal, 200 low. `reasoning_effort` is one of `default`, `minimal`, `low`, `medium`, `high`, or `xhigh`, subject to the selected model's live capability record.

Patch only fields the user intends to change. Explicit JSON `null` restores inheritance. While a turn is running, the API records the value as pending for the next turn.
