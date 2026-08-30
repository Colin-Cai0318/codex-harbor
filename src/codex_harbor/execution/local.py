from __future__ import annotations

import asyncio
import os
import platform
from pathlib import Path

import psutil

from .base import ExecutionBackend


class LocalBackend(ExecutionBackend):
    async def run(
        self, command: str, cwd: str | Path, timeout: float
    ) -> tuple[int, str, str]:
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
        except TimeoutError:
            self.terminate_tree(process.pid)
            await process.wait()
            return 124, "", f"command timed out after {timeout:g}s"
        return (
            process.returncode or 0,
            stdout.decode(errors="replace"),
            stderr.decode(errors="replace"),
        )

    def process_alive(self, pid: int) -> bool:
        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()

    def normalize_path(self, path: str | Path) -> str:
        return str(Path(path).expanduser().resolve())

    def terminate_tree(self, pid: int) -> None:
        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return
        children = parent.children(recursive=True)
        for process in children:
            process.terminate()
        parent.terminate()
        _, alive = psutil.wait_procs([*children, parent], timeout=5)
        for process in alive:
            process.kill()


class LinuxBackend(LocalBackend):
    pass


class WindowsBackend(LocalBackend):
    pass


class WSLBackend(LocalBackend):
    async def run(
        self, command: str, cwd: str | Path, timeout: float
    ) -> tuple[int, str, str]:
        process = await asyncio.create_subprocess_exec(
            "wsl.exe",
            "--cd",
            str(cwd),
            "sh",
            "-lc",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
        except TimeoutError:
            self.terminate_tree(process.pid)
            await process.wait()
            return 124, "", f"command timed out after {timeout:g}s"
        return (
            process.returncode or 0,
            stdout.decode(errors="replace"),
            stderr.decode(errors="replace"),
        )


def select_backend(name: str = "local") -> ExecutionBackend:
    normalized = name.lower()
    if normalized == "wsl":
        return WSLBackend()
    if normalized in {"windows", "local"} and os.name == "nt":
        return WindowsBackend()
    if normalized in {"linux", "local"}:
        return LinuxBackend()
    raise ValueError(f"unsupported execution backend: {name}")


def platform_summary() -> str:
    if os.name == "nt" and "microsoft" in platform.release().lower():
        return "WSL2"
    return "Windows Native" if os.name == "nt" else "Linux Native"
