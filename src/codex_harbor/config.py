from __future__ import annotations

import copy
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from platformdirs import user_data_path

DEFAULTS: dict[str, Any] = {
    "harbor": {"data_dir": "", "bind": "127.0.0.1", "port": 8765},
    "scheduler": {
        "max_workers": 3,
        "poll_interval_seconds": 2.0,
        "heartbeat_interval_seconds": 10.0,
        "stale_worker_seconds": 45.0,
    },
    "quota": {"freeze_on_weekly_reset": True, "provider": "codex"},
    "codex": {
        "executable": "",
        "default_model": "",
        "default_reasoning_effort": "medium",
        "approval_policy": "never",
        "sandbox": "workspace-write",
    },
    "profiles": {
        "simple": {"reasoning_effort": "low"},
        "normal": {"reasoning_effort": "medium"},
        "deep_debug": {"reasoning_effort": "high"},
        "critical_rca": {"reasoning_effort": "xhigh"},
    },
}


def _merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value


@dataclass(slots=True)
class HarborConfig:
    values: dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULTS))
    source: Path | None = None

    @property
    def data_dir(self) -> Path:
        env_value = os.environ.get("HARBOR_DATA_DIR")
        configured = env_value or self.values["harbor"].get("data_dir")
        return (
            Path(configured).expanduser().resolve()
            if configured
            else user_data_path("CodexHarbor", appauthor=False)
        )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "harbor.db"

    def section(self, name: str) -> dict[str, Any]:
        return self.values[name]

    def ensure_layout(self) -> None:
        for path in (
            self.data_dir,
            self.data_dir / "tasks",
            self.data_dir / "worktrees",
            self.data_dir / "logs",
        ):
            path.mkdir(parents=True, exist_ok=True)


def load_config(path: str | Path | None = None) -> HarborConfig:
    values = copy.deepcopy(DEFAULTS)
    selected = Path(path).expanduser().resolve() if path else None
    if selected is None:
        env_path = os.environ.get("HARBOR_CONFIG")
        if env_path:
            selected = Path(env_path).expanduser().resolve()
        else:
            candidate = user_data_path("CodexHarbor", appauthor=False) / "config.toml"
            selected = candidate if candidate.exists() else None
    if selected and selected.exists():
        with selected.open("rb") as handle:
            _merge(values, tomllib.load(handle))
    return HarborConfig(values=values, source=selected)
