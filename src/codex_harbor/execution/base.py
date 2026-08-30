from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ExecutionBackend(ABC):
    @abstractmethod
    async def run(
        self, command: str, cwd: str | Path, timeout: float
    ) -> tuple[int, str, str]:
        raise NotImplementedError

    @abstractmethod
    def process_alive(self, pid: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def normalize_path(self, path: str | Path) -> str:
        raise NotImplementedError

    @abstractmethod
    def terminate_tree(self, pid: int) -> None:
        raise NotImplementedError
