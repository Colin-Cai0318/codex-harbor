"""PyInstaller entry point (absolute import supports a frozen executable)."""

import os
import traceback
from pathlib import Path

if __name__ == "__main__":
    try:
        from codex_harbor.desktop import main

        main()
    except BaseException as error:  # noqa: BLE001 - record failures before the GUI/logging exists
        if isinstance(error, SystemExit) and error.code in {None, 0}:
            raise
        destination = (
            Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
            / "CodexHarbor"
            / "logs"
        )
        destination.mkdir(parents=True, exist_ok=True)
        with (destination / "desktop-startup.log").open(
            "a", encoding="utf-8"
        ) as handle:
            traceback.print_exc(file=handle)
        raise
