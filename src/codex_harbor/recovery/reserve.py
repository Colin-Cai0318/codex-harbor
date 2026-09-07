from __future__ import annotations

import asyncio

from ..codex import AppServerClient, ModelRegistry
from ..domain import EffectiveAgentConfig
from ..runtime import CodexAppServerRuntime

RESERVE_MODEL = "gpt-reserve"
RESERVE_EFFORT = "xhigh"


def reserve_available(snapshot: dict) -> bool:
    for bucket in (snapshot.get("rateLimitsByLimitId") or {}).values():
        if (
            bucket.get("limitName") != RESERVE_MODEL
            and bucket.get("limitId") != RESERVE_MODEL
        ):
            continue
        windows = [bucket[key] for key in ("primary", "secondary") if bucket.get(key)]
        return (
            bool(windows)
            and not bucket.get("spendControlReached")
            and not bucket.get("rateLimitReachedType")
            and all(float(window.get("usedPercent", 100)) < 100 for window in windows)
        )
    return False


async def prepare_reserve_checkpoint(
    control: AppServerClient, thread_id: str
) -> tuple[str, str]:
    """One bounded same-thread reserve turn; never runs the underlying task."""
    async with AppServerClient(
        control.executable, request_timeout=control.request_timeout
    ) as client:
        # Reserve is a separate hidden model/bucket, not the ordinary Luna model.
        models = []
        cursor = None
        while True:
            page = await client.request(
                "model/list", {"includeHidden": True, "cursor": cursor}
            )
            models.extend(page["data"])
            cursor = page.get("nextCursor")
            if not cursor:
                break
        ModelRegistry(models).resolve(
            task_model=RESERVE_MODEL,
            task_reasoning=RESERVE_EFFORT,
            global_model=RESERVE_MODEL,
        )
        if not reserve_available(await client.rate_limits()):
            raise RuntimeError(
                "Luna Reserve allowance is unavailable; no reserve turn was sent"
            )
        runtime = CodexAppServerRuntime(client)
        inspected = await client.thread_read(thread_id, include_turns=False)
        thread = inspected["thread"]
        if thread["id"] != thread_id:
            raise RuntimeError("original thread identity did not match")
        result = await asyncio.wait_for(
            runtime.resume_task(
                thread_id,
                thread["cwd"],
                "本轮只为 Harbor 补建当前任务的额度恢复记录。请根据本对话输出简短续接摘要："
                "原任务目标、已经完成的工作、剩余步骤和必须遵守的约束。"
                "不要调用任何工具，不要修改文件，不要执行原任务，不要创建或切换对话。"
                "Harbor 会将摘要写入恢复 task，并在主额度恢复后以原主模型继续本对话。",
                EffectiveAgentConfig(
                    RESERVE_MODEL, RESERVE_EFFORT, RESERVE_MODEL, RESERVE_EFFORT
                ),
            ),
            timeout=90,
        )
        if result.status != "completed":
            raise RuntimeError(
                result.error or f"reserve checkpoint ended: {result.status}"
            )
        page = await client.request(
            "thread/turns/list",
            {
                "threadId": thread_id,
                "limit": 1,
                "sortDirection": "desc",
                "itemsView": "full",
            },
        )
        turn = (page.get("data") or [{}])[0]
        if turn.get("id") != result.turn_id:
            raise RuntimeError("reserve checkpoint turn identity did not match")
        text = "\n".join(
            item.get("text", "")
            for item in turn.get("items", [])
            if item.get("type") == "agentMessage"
        )
        if not text.strip():
            raise RuntimeError("reserve checkpoint contained no summary")
        return text[:6000], result.turn_id
