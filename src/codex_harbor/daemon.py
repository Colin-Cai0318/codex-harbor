from __future__ import annotations

import argparse
import asyncio

import uvicorn

from .api import create_app
from .application import ApplicationContainer
from .codex import AppServerClient, ModelRegistry
from .quota import CodexQuotaProvider, QuotaManager
from .recovery import RecoveryManager
from .runtime import CodexAppServerRuntime
from .scheduler import Scheduler


async def serve(config_path: str | None = None) -> None:
    container = ApplicationContainer.build(config_path)
    values = container.config.values
    if values["harbor"]["bind"] not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError(
            "Harbor is single-user and must bind to 127.0.0.1, localhost, or ::1"
        )
    codex = values["codex"]
    async with AppServerClient(codex.get("executable") or None) as client:
        # Hidden models include the native reserve model.  They must remain
        # resolvable for already-armed recovery watches, while the API filters
        # them from the user-facing model picker.
        registry = await ModelRegistry.load(client, include_hidden=True)
        runtime = CodexAppServerRuntime(
            client,
            approval_policy=codex.get("approval_policy", "never"),
            sandbox=codex.get("sandbox", "workspace-write"),
            isolated_workers=True,
        )
        scheduler = Scheduler(
            container.repository,
            runtime,
            registry,
            QuotaManager(container.repository, CodexQuotaProvider(client)),
            RecoveryManager(
                container.repository,
                stale_seconds=values["scheduler"]["stale_worker_seconds"],
            ),
            values,
            container.config.data_dir,
        )
        app = create_app(
            container.repository,
            model_registry=registry,
            profiles=values.get("profiles", {}),
            app_server_client=client,
            codex_settings=values.get("codex", {}),
        )
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host=values["harbor"]["bind"],
                port=int(values["harbor"]["port"]),
                log_level="info",
            )
        )
        scheduler_task = asyncio.create_task(scheduler.run_forever())
        server_task = asyncio.create_task(server.serve())
        try:
            await asyncio.wait(
                {scheduler_task, server_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if scheduler_task.done() and not server_task.done():
                server.should_exit = True
            await server_task
            if scheduler_task.done():
                scheduler_task.result()
                if not scheduler.stopping:
                    raise RuntimeError("Harbor scheduler stopped unexpectedly")
        finally:
            server.should_exit = True
            if not server_task.done():
                server_task.cancel()
            await asyncio.gather(server_task, return_exceptions=True)
            scheduler.stopping = True
            scheduler_task.cancel()
            await asyncio.gather(scheduler_task, return_exceptions=True)
            await scheduler.stop()


def main() -> None:
    parser = argparse.ArgumentParser(prog="codex-harbord")
    parser.add_argument("--config")
    args = parser.parse_args()
    try:
        asyncio.run(serve(args.config))
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
