"""Opt-in: three real Luna turns, worker ownership release and simulated quota reset."""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import uuid
from pathlib import Path

from codex_harbor.acceptance import AcceptanceRunner
from codex_harbor.codex import AppServerClient, ModelRegistry
from codex_harbor.config import DEFAULTS
from codex_harbor.domain import EffectiveAgentConfig, QuotaWindow, TaskSpec, utc_now
from codex_harbor.execution import select_backend
from codex_harbor.git import WorktreeManager
from codex_harbor.quota import FakeQuotaProvider, QuotaManager
from codex_harbor.recovery.auto_resume import AutoResumeManager
from codex_harbor.runtime import CodexAppServerRuntime
from codex_harbor.storage import Database, HarborRepository
from codex_harbor.worker import Worker


async def run(workspace, output):
    output.mkdir(parents=True, exist_ok=False)
    evidence = {"started_at": utc_now(), "checks": []}

    def record(name, **details):
        evidence["checks"].append({"name": name, **details})
        (output / "evidence.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
        print(json.dumps(evidence["checks"][-1]), flush=True)

    db = Database(output / "harbor.db")
    db.migrate(now=utc_now())
    repository = HarborRepository(db)
    repository.add_repository(workspace)
    config = copy.deepcopy(DEFAULTS)
    model = "gpt-5.6-luna"
    config["codex"].update(default_model=model, default_reasoning_effort="low")
    token = "CONTINUITY_" + uuid.uuid4().hex
    async with AppServerClient() as control:
        registry = await ModelRegistry.load(control)
        registry.resolve(task_model=model, task_reasoning="xhigh", global_model=model)
        runtime = CodexAppServerRuntime(control, isolated_workers=True)

        async def work(task):
            claimed = repository.claim_next("e2e-worker")
            assert claimed and claimed["id"] == task["id"]
            await Worker(
                repository,
                runtime,
                registry,
                WorktreeManager(repository, output / "worktrees"),
                AcceptanceRunner(select_backend("local")),
                config,
                output,
                "e2e-worker",
            ).run(claimed)
            result = repository.get_task(task["id"])
            record(
                "worker",
                status=result["status"],
                thread_id=result["root_thread_id"],
                effort=result["latest_attempt"]["effective_reasoning_effort"],
            )
            assert result["status"] == "SUCCEEDED", result["latest_attempt"]
            return result

        first = repository.create_task(
            TaskSpec(
                title="Harbor ownership continuity test",
                repository=str(workspace),
                prompt=f"Remember this exact token for later: {token}. Reply only STORED. Do not call tools or modify files.",
                model=model,
                reasoning_effort="low",
                conversation_mode="new",
                direct_prompt=True,
            )
        )
        first = await work(first)
        thread_id = first["root_thread_id"]
        # A separate process must resume immediately after worker completion.
        async with AppServerClient() as reserve:
            reserve_runtime = CodexAppServerRuntime(reserve)
            result = await reserve_runtime.resume_task(
                thread_id,
                str(workspace),
                "Return only the exact CONTINUITY token I gave you earlier. Do not call tools or modify files.",
                EffectiveAgentConfig(model, "xhigh", model, "xhigh"),
            )
            assert result.status == "completed", result.error
            inspected = await reserve.thread_read(thread_id)
            assert token in json.dumps(inspected["thread"]["turns"][-1]["items"])
            record(
                "reserve_same_thread",
                thread_id=result.thread_id,
                effort="xhigh",
                context_retained=True,
            )

        # Use real persisted history but inject quota failure in the read adapter;
        # no production records or account limits are modified.
        thread = inspected["thread"]
        thread["turns"][-1].update(
            status="failed", error={"codexErrorInfo": "usageLimitExceeded"}
        )

        class Reader:
            async def thread_read(self, selected, **kwargs):
                assert selected == thread_id
                return {"thread": thread}

        manager = AutoResumeManager(repository, Reader())
        spec = TaskSpec(
            title="Resume exact original test",
            repository=str(workspace),
            prompt="Return only the exact CONTINUITY token I gave you earlier. Do not call tools or modify files.",
            model=model,
            reasoning_effort="low",
            conversation_mode="existing",
            origin_thread_id=thread_id,
            preserve_thread_name=True,
            direct_prompt=True,
        )
        watch = manager.arm(spec, thread, 95)
        await manager.tick(
            [QuotaWindow("PRIMARY_5H", available=False, used_percent=100)]
        )
        waiter = repository.get_task(manager.list()[0]["task_id"])
        assert (
            waiter["status"] == "WAIT_QUOTA" and waiter["root_thread_id"] == thread_id
        )
        quota = QuotaManager(repository, FakeQuotaProvider())
        await quota.refresh()
        assert quota.release_quota_waiters() == 1
        resumed = await work(waiter)
        assert resumed["root_thread_id"] == thread_id
        async with AppServerClient() as desktop:
            reopened = await desktop.thread_resume(thread_id)
            assert reopened["thread"]["id"] == thread_id
            final = await desktop.thread_read(thread_id)
            assert token in json.dumps(final["thread"]["turns"][-1]["items"])
            record(
                "same_thread_after_reset",
                watch_id=watch["id"],
                thread_id=thread_id,
                original_config_restored=True,
                context_retained=True,
                writer_released=True,
            )
        assert (await control.request("thread/loaded/list", {}))["data"] == []
        record("control_connection_does_not_own_threads", passed=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--workspace", type=Path, default=Path(".harbor/e2e-project"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".harbor") / f"same-thread-{uuid.uuid4().hex[:8]}",
    )
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required; this uses three real model turns")
    asyncio.run(run(args.workspace.resolve(), args.output.resolve()))
