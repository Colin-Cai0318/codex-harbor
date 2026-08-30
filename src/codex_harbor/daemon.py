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
    codex = values["codex"]
    async with AppServerClient(codex.get("executable") or None) as client:
        registry = await ModelRegistry.load(client)
        runtime = CodexAppServerRuntime(
            client,
            approval_policy=codex.get("approval_policy", "never"),
            sandbox=codex.get("sandbox", "workspace-write"),
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
            max_workers=int(values["scheduler"]["max_workers"]),
            profiles=values.get("profiles", {}),
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
        try:
            await server.serve()
        finally:
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
