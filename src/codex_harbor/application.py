from __future__ import annotations

from dataclasses import dataclass

from .config import HarborConfig, load_config
from .domain import utc_now
from .storage import Database, HarborRepository


@dataclass(slots=True)
class ApplicationContainer:
    config: HarborConfig
    database: Database
    repository: HarborRepository

    @classmethod
    def build(cls, config_path: str | None = None) -> ApplicationContainer:
        config = load_config(config_path)
        config.ensure_layout()
        database = Database(config.db_path)
        database.migrate(
            freeze_on_weekly_reset=bool(
                config.section("quota")["freeze_on_weekly_reset"]
            ),
            max_workers=int(config.section("scheduler")["max_workers"]),
            now=utc_now(),
        )
        return cls(config, database, HarborRepository(database))
