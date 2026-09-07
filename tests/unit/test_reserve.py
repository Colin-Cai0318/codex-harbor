import pytest

from codex_harbor.recovery.reserve import reserve_available


@pytest.mark.parametrize(
    "used,blocked,expected", [(95, False, True), (100, False, False), (0, True, False)]
)
def test_reserve_uses_named_bucket_not_normal_luna_or_main_quota(
    used, blocked, expected
):
    snapshot = {
        "rateLimitsByLimitId": {
            "codex": {"primary": {"usedPercent": 100}},
            "base_model_inference": {
                "limitName": "gpt-reserve",
                "primary": {"usedPercent": used},
                "spendControlReached": blocked,
            },
        }
    }
    assert reserve_available(snapshot) is expected
    assert not reserve_available(
        {"rateLimitsByLimitId": {"codex": {"primary": {"usedPercent": 0}}}}
    )


@pytest.mark.asyncio
async def test_checkpoint_sends_actual_reserve_xhigh_to_same_thread_and_closes(
    monkeypatch,
):
    from codex_harbor.recovery.reserve import prepare_reserve_checkpoint

    calls = []

    class Client:
        executable = "codex"
        request_timeout = 30

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            calls.append("closed")

        async def request(self, method, params):
            if method == "model/list":
                assert params["includeHidden"] is True
                return {
                    "data": [
                        {
                            "model": "gpt-reserve",
                            "supportedReasoningEfforts": [{"reasoningEffort": "xhigh"}],
                        }
                    ]
                }
            assert method == "thread/turns/list"
            assert params["threadId"] == "original"
            return {
                "data": [
                    {
                        "id": "reserve-turn",
                        "items": [{"type": "agentMessage", "text": "remaining work"}],
                    }
                ]
            }

        async def rate_limits(self):
            return {
                "rateLimitsByLimitId": {
                    "reserve": {
                        "limitName": "gpt-reserve",
                        "primary": {"usedPercent": 10},
                    }
                }
            }

        async def thread_read(self, thread_id, **kwargs):
            return {"thread": {"id": thread_id, "cwd": "/workspace"}}

        async def thread_resume(self, thread_id, **kwargs):
            calls.append(("resume", thread_id, kwargs["model"]))
            return {"thread": {"id": thread_id}}

        async def turn_start(self, thread_id, prompt, **kwargs):
            calls.append(("turn", thread_id, kwargs["model"], kwargs["effort"]))
            return {"turn": {"id": "reserve-turn"}}

        async def wait_turn(self, *args):
            return {"id": "reserve-turn", "status": "completed"}

    client = Client()
    monkeypatch.setattr(
        "codex_harbor.recovery.reserve.AppServerClient", lambda *a, **k: client
    )
    assert await prepare_reserve_checkpoint(client, "original") == (
        "remaining work",
        "reserve-turn",
    )
    assert calls == [
        ("resume", "original", "gpt-reserve"),
        ("turn", "original", "gpt-reserve", "xhigh"),
        "closed",
    ]
