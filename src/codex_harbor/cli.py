from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

import yaml

from .application import ApplicationContainer
from .codex import (
    AppServerClient,
    AppServerError,
    ModelRegistry,
    resolve_codex_executable,
)
from .daemon import serve
from .domain import PoolStatus, TaskSpec
from .execution.local import platform_summary
from .git import WorktreeManager
from .quota import CodexQuotaProvider, QuotaManager
from .recovery import RecoveryManager
from .runtime import CodexAppServerRuntime
from .scheduler import Scheduler


def _json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _task_spec(data: dict[str, Any]) -> TaskSpec:
    repository = data.get("repository", {})
    if isinstance(repository, dict):
        repository = repository.get("path")
    execution = data.get("execution", {})
    agent = data.get("agent", {}) or {}
    acceptance = data.get("acceptance", {}) or {}
    return TaskSpec(
        task_id=data.get("id"),
        title=data["title"],
        repository=repository,
        prompt=data.get("prompt") or data["title"],
        description=data.get("description", ""),
        execution_backend=execution.get(
            "backend", data.get("execution_backend", "local")
        ),
        priority=int(data.get("priority", 100)),
        depends_on=list(data.get("depends_on", [])),
        exclusive_group=data.get("exclusive_group"),
        acceptance_commands=list(
            acceptance.get("commands", data.get("acceptance_commands", []))
        ),
        max_attempts=int(data.get("max_attempts", 5)),
        model=agent.get("model", data.get("model")),
        reasoning_effort=agent.get("reasoning_effort", data.get("reasoning_effort")),
        profile=data.get("profile"),
    )


def _add_task_parser(task_sub: argparse._SubParsersAction) -> None:
    add = task_sub.add_parser("add", help="create a task")
    add.add_argument("--id")
    add.add_argument("--repo", required=True)
    add.add_argument("--title", required=True)
    add.add_argument("--prompt")
    add.add_argument("--description", default="")
    add.add_argument(
        "--backend", default="local", choices=["local", "linux", "windows", "wsl"]
    )
    add.add_argument("--priority", type=int, default=100)
    add.add_argument("--depends-on", action="append", default=[])
    add.add_argument("--exclusive-group")
    add.add_argument("--accept", action="append", default=[])
    add.add_argument("--max-attempts", type=int, default=5)
    add.add_argument("--model")
    add.add_argument("--reasoning")
    add.add_argument("--profile")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harbor", description="Codex Harbor persistent task scheduler"
    )
    parser.add_argument("--config", help="path to config.toml")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    repo = sub.add_parser("repo")
    repo_sub = repo.add_subparsers(dest="repo_command", required=True)
    repo_sub.add_parser("add").add_argument("path")
    repo_sub.add_parser("list")
    task = sub.add_parser("task")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    _add_task_parser(task_sub)
    imported = task_sub.add_parser("import")
    imported.add_argument("path")
    task_sub.add_parser("list")
    show = task_sub.add_parser("show")
    show.add_argument("task_id")
    configure = task_sub.add_parser("config")
    configure.add_argument("task_id")
    configure.add_argument("--model")
    configure.add_argument("--reasoning")
    for action in ("retry", "cancel", "cleanup"):
        child = task_sub.add_parser(action)
        child.add_argument("task_id")
    sub.add_parser("ps")
    sub.add_parser("quota")
    for action in ("pause", "freeze", "resume"):
        sub.add_parser(action)
    sub.add_parser("run")
    sub.add_parser("daemon")
    for action in ("logs", "history"):
        child = sub.add_parser(action)
        child.add_argument("task_id")
    sub.add_parser("doctor")
    return parser


async def _runtime_parts(container: ApplicationContainer):
    codex_config = container.config.section("codex")
    client = AppServerClient(codex_config.get("executable") or None)
    await client.start()
    registry = await ModelRegistry.load(client)
    runtime = CodexAppServerRuntime(
        client,
        approval_policy=codex_config.get("approval_policy", "never"),
        sandbox=codex_config.get("sandbox", "workspace-write"),
    )
    return client, registry, runtime


async def _run_scheduler(container: ApplicationContainer) -> None:
    client, registry, runtime = await _runtime_parts(container)
    try:
        config = container.config.values
        scheduler = Scheduler(
            container.repository,
            runtime,
            registry,
            QuotaManager(container.repository, CodexQuotaProvider(client)),
            RecoveryManager(
                container.repository,
                stale_seconds=config["scheduler"]["stale_worker_seconds"],
            ),
            config,
            container.config.data_dir,
        )
        await scheduler.run_forever()
    finally:
        await client.close()


async def _doctor(container: ApplicationContainer) -> int:
    checks: list[tuple[str, str, bool]] = []
    checks.append(("Python", sys.version.split()[0], sys.version_info >= (3, 11)))
    checks.append(("SQLite", sqlite3.sqlite_version, True))
    git = shutil.which("git")
    checks.append(("Git", git or "not found", bool(git)))
    try:
        codex = resolve_codex_executable(
            container.config.section("codex").get("executable") or None
        )
        checks.append(("Codex executable", codex, True))
    except FileNotFoundError as error:
        checks.append(("Codex executable", str(error), False))
        codex = None
    checks.append(("Execution backend", platform_summary(), True))
    checks.append(
        ("Database", str(container.config.db_path), container.config.db_path.exists())
    )
    checks.append(
        (
            "Data directory",
            str(container.config.data_dir),
            container.config.data_dir.is_dir(),
        )
    )
    if codex:
        try:
            async with AppServerClient(codex, request_timeout=15) as client:
                health = await client.health_check()
                models = await client.model_list()
                checks.append(
                    ("Codex App Server", "initialized", bool(health.get("ok")))
                )
                checks.append(("Codex authentication", "account/read succeeded", True))
                checks.append(("Model Registry", f"{len(models)} models", bool(models)))
        except (AppServerError, OSError, TimeoutError) as error:
            checks.append(("Codex App Server", str(error), False))
    print("Codex Harbor Doctor\n")
    for name, detail, okay in checks:
        print(f"{name:<24} {'OK' if okay else 'FAIL':<5} {detail}")
    return 0 if all(item[2] for item in checks) else 1


def _print_ps(container: ApplicationContainer) -> None:
    pool = container.repository.get_pool()
    workers = container.repository.list_workers()
    quotas = {item["quota_type"]: item for item in container.repository.list_quotas()}
    print("CODEX HARBOR\n")
    print(
        f"Pool: {pool['state']}    Workers: {len(workers)} / {container.config.section('scheduler')['max_workers']}"
    )
    for name in ("PRIMARY_5H", "WEEKLY"):
        quota = quotas.get(name, {})
        used = (
            "unknown"
            if quota.get("used_percent") is None
            else f"{quota['used_percent']:.0f}% used"
        )
        print(f"{name:<10} {used:<14} reset {quota.get('reset_at') or 'unknown'}")
    print("\nID       STATUS        AGENT                    TITLE")
    for task in container.repository.list_tasks():
        agent = f"{task.get('model') or 'default'}/{task.get('reasoning_effort') or 'default'}"
        print(f"{task['id']:<8} {task['status']:<13} {agent:<24} {task['title']}")


def dispatch(args: argparse.Namespace) -> int:
    container = ApplicationContainer.build(args.config)
    repository = container.repository
    if args.command == "init":
        print(f"Initialized Codex Harbor at {container.config.data_dir}")
        return 0
    if args.command == "repo":
        _json(
            repository.add_repository(args.path)
            if args.repo_command == "add"
            else repository.list_repositories()
        )
        return 0
    if args.command == "task":
        if args.task_command == "add":
            _json(
                repository.create_task(
                    TaskSpec(
                        task_id=args.id,
                        title=args.title,
                        repository=args.repo,
                        prompt=args.prompt or args.title,
                        description=args.description,
                        execution_backend=args.backend,
                        priority=args.priority,
                        depends_on=args.depends_on,
                        exclusive_group=args.exclusive_group,
                        acceptance_commands=args.accept,
                        max_attempts=args.max_attempts,
                        model=args.model,
                        reasoning_effort=args.reasoning,
                        profile=args.profile,
                    )
                )
            )
        elif args.task_command == "import":
            data = yaml.safe_load(Path(args.path).read_text(encoding="utf-8"))
            items = (
                data.get("tasks", [])
                if isinstance(data, dict) and "tasks" in data
                else data
            )
            if isinstance(items, dict):
                items = [items]
            _json([repository.create_task(_task_spec(item)) for item in items])
        elif args.task_command == "list":
            _json(repository.list_tasks())
        elif args.task_command == "show":
            _json(repository.get_task(args.task_id))
        elif args.task_command == "config":
            updates = {}
            if args.model is not None:
                updates["model"] = args.model
            if args.reasoning is not None:
                updates["reasoning"] = args.reasoning
            if not updates:
                raise ValueError("provide --model and/or --reasoning")
            _json(repository.update_agent_config(args.task_id, **updates))
        elif args.task_command == "retry":
            _json(repository.retry_task(args.task_id))
        elif args.task_command == "cancel":
            _json(repository.cancel_task(args.task_id))
        elif args.task_command == "cleanup":
            task = repository.get_task(args.task_id)
            if not task.get("worktree_path"):
                raise ValueError("task has no worktree")
            asyncio.run(
                WorktreeManager(
                    repository, container.config.data_dir / "worktrees"
                ).cleanup(task["id"], task["repository"], task["worktree_path"])
            )
            print(
                f"Removed worktree for {task['id']}; branch harbor/{task['id']} was preserved"
            )
        return 0
    if args.command == "ps":
        _print_ps(container)
        return 0
    if args.command == "quota":
        _json(repository.list_quotas())
        return 0
    if args.command in {"pause", "freeze", "resume"}:
        state = {
            "pause": PoolStatus.PAUSED,
            "freeze": PoolStatus.FROZEN,
            "resume": PoolStatus.RUNNING,
        }[args.command]
        repository.set_pool(state)
        _json(repository.get_pool())
        return 0
    if args.command == "run":
        try:
            asyncio.run(_run_scheduler(container))
        except KeyboardInterrupt:
            pass
        return 0
    if args.command == "daemon":
        asyncio.run(serve(args.config))
        return 0
    if args.command in {"logs", "history"}:
        _json(repository.list_events(args.task_id, 1000))
        return 0
    if args.command == "doctor":
        return asyncio.run(_doctor(container))
    return 2


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        raise SystemExit(dispatch(args))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except (KeyError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
