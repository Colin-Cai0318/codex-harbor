"""Opt-in live Luna test: uv run python tools/luna_e2e.py --execute.

Uses an existing checkout, an isolated Harbor DB, durable Codex conversations,
and a maximum of eight model turns. Evidence stays under ignored .harbor/.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
import uuid
from pathlib import Path

import httpx

from codex_harbor.api import create_app
from codex_harbor.codex import AppServerClient, AppServerError, ModelRegistry
from codex_harbor.config import DEFAULTS
from codex_harbor.domain import EffectiveAgentConfig, TaskStatus, utc_now
from codex_harbor.quota import CodexQuotaProvider, QuotaManager
from codex_harbor.recovery import RecoveryManager
from codex_harbor.runtime import CodexAppServerRuntime
from codex_harbor.scheduler import Scheduler
from codex_harbor.storage import Database, HarborRepository

MODEL = "gpt-5.6-luna"


async def main(workspace: Path, output: Path, execute: bool, coding_only: bool = False):
    output.mkdir(parents=True, exist_ok=False)
    evidence = {"started_at": utc_now(), "model": MODEL, "effort": "low", "checks": []}

    def record(name, **details):
        evidence["checks"].append({"name": name, **details})
        (output / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps({"name": name, **details}), flush=True)

    database = Database(output / "harbor.db")
    database.migrate(now=utc_now())
    repository = HarborRepository(database)
    config = copy.deepcopy(DEFAULTS)
    config["codex"].update(default_model=MODEL, default_reasoning_effort="low")
    token = "HARBOR_" + uuid.uuid4().hex[:12]
    thread_id = None
    first_id = None
    project_id = None
    try:
        for phase in (1, 2):
            async with AppServerClient() as client:
                registry = await ModelRegistry.load(client)
                registry.resolve(task_model=MODEL, task_reasoning="low", global_model=MODEL)
                project = await client.find_project_for_path(Path.cwd())
                if not project:
                    raise RuntimeError("Existing Codex Project for current checkout is required")
                project_id = project["id"]
                for retry in range(3):
                    try:
                        limits = (await client.rate_limits()).get("rateLimits", {})
                        break
                    except (AppServerError, TimeoutError):
                        if retry == 2:
                            raise
                        record("quota-preflight-retry", retry=retry + 1)
                        await asyncio.sleep(2)
                record(f"preflight-{phase}", model_available=True,
                       process_id=client.process.pid,
                       quota={key: limits.get(key) for key in ("primary", "secondary")})
                if not execute:
                    return
                runtime = CodexAppServerRuntime(client, isolated_workers=True)
                scheduler = Scheduler(repository, runtime, registry,
                                      QuotaManager(repository, CodexQuotaProvider(client)),
                                      RecoveryManager(repository), config, output)
                app = create_app(repository, model_registry=registry, app_server_client=client)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
                    async def create(message, *, existing=None, depends=None, acceptance=None, max_attempts=1, project_id=project_id):
                        response = await api.post("/api/tasks", json={
                            "message": message, "codex_project_id": project_id,
                            "conversation_mode": "existing" if existing else "new",
                            "thread_id": existing, "workspace_roots": [str(workspace)],
                            "primary_workspace": str(workspace), "model": MODEL,
                            "reasoning_effort": "low", "max_attempts": max_attempts,
                            "depends_on": depends or [], "acceptance_commands": acceptance or [],
                        })
                        response.raise_for_status()
                        return response.json()

                    async def run_to_settled(task_id, scheduler=scheduler):
                        deadline = asyncio.get_running_loop().time() + 180
                        while asyncio.get_running_loop().time() < deadline:
                            await scheduler.tick()
                            task = repository.get_task(task_id)
                            if task["status"] in {"SUCCEEDED", "FAILED", "BLOCKED", "WAIT_QUOTA"}:
                                record("task", id=task_id, status=task["status"],
                                       thread=task["root_thread_id"], attempt=task["latest_attempt"])
                                return task
                            await asyncio.sleep(0.5)
                        raise TimeoutError(f"task {task_id} did not settle")

                    try:
                        if coding_only:
                            filename = f"luna_{uuid.uuid4().hex[:8]}.py"
                            check = f'"{sys.executable}" -c "import runpy; f=runpy.run_path({filename!r})[\'add\']; assert f(2,3)==5; assert f(-2,2)==0; assert f(0,0)==0"'
                            task = await create(
                                f"Implement one tiny Python module named {filename} in the current workspace. It must define add(a, b) returning a+b. Use tools to create this file. Do not modify other files. No dependencies. Finish after checking it.",
                                acceptance=[check], max_attempts=2,
                            )
                            result = await run_to_settled(task["id"])
                            assert result["status"] == TaskStatus.SUCCEEDED
                            assert (workspace / filename).is_file()
                            evidence["passed"] = True
                            record("real-code-and-acceptance", passed=True, file=filename)
                            return
                        if phase == 1:
                            task = await create(f"This is a small Harbor test. Remember token {token} in this conversation. Reply with exactly that token. Do not use tools or change files.")
                            first_id = task["id"]
                            result = await run_to_settled(first_id)
                            assert result["status"] == TaskStatus.SUCCEEDED
                            thread_id = result["root_thread_id"]
                            assert thread_id, "worker must persist its conversation identity"
                        else:
                            task = await create("Reply with the exact token I asked you to remember earlier. Do not use tools or change files.", existing=thread_id, depends=[first_id])
                            result = await run_to_settled(task["id"])
                            assert result["status"] == TaskStatus.SUCCEEDED
                            assert result["root_thread_id"] == thread_id
                            history = await client.thread_read(thread_id)
                            turns = history["thread"]["turns"]
                            last_items = turns[-1].get("items", [])
                            assert any(token in item.get("text", "") for item in last_items if item.get("type") == "agentMessage"), last_items
                            record("cross-process-context", passed=True, turn_count=len(turns))

                            # The acceptance gate fails once, without asking the model to fix code.
                            gate = output / "acceptance-gate"
                            command = f'"{sys.executable}" -c "from pathlib import Path; import sys; sys.exit(0 if Path({str(gate)!r}).exists() else 1)"'
                            failing = await create("Reply exactly GATE_TEST. Do not use tools or change files.", existing=thread_id, acceptance=[command])
                            follower = await create("Reply exactly FOLLOWER_OK. Do not use tools or change files.", existing=thread_id, depends=[failing["id"]])
                            result = await run_to_settled(failing["id"])
                            assert result["status"] == TaskStatus.FAILED
                            await scheduler.tick()
                            assert repository.get_task(follower["id"])["status"] == TaskStatus.BLOCKED
                            gate.touch()
                            response = await api.post(f'/api/tasks/{failing["id"]}/retry')
                            response.raise_for_status()
                            assert (await run_to_settled(failing["id"]))["status"] == TaskStatus.SUCCEEDED
                            assert (await run_to_settled(follower["id"]))["status"] == TaskStatus.SUCCEEDED
                            record("dependency-failure-and-retry", passed=True)

                            # Concurrent read-only turns test the actual notification transport.
                            cfg = EffectiveAgentConfig(MODEL, "low", MODEL, "low")
                            results = await asyncio.wait_for(asyncio.gather(*[
                                runtime.start_task(str(workspace), f"Reply exactly PARALLEL_{index}. No tools or file changes.", cfg)
                                for index in range(2)
                            ]), 180)
                            assert all(result.status == "completed" for result in results)
                            record("parallel-turns", passed=True, threads=[r.thread_id for r in results])
                    finally:
                        for future in scheduler.running.values():
                            if not future.done():
                                future.cancel()
                        await scheduler.stop()
        evidence["passed"] = True
        record("complete", passed=True)
    except BaseException as error:
        evidence["passed"] = False
        record("error", error=str(error))
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--coding-only", action="store_true")
    parser.add_argument("--workspace", type=Path, default=Path(".harbor/e2e-project"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.workspace.resolve(), args.output.resolve(), args.execute, args.coding_only))
