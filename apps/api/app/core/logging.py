import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import settings


def _make_handler(path: Path) -> RotatingFileHandler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    return handler


def setup_logging() -> None:
    logs_dir = Path(settings.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if getattr(root, "_tech_hype_configured", False):
        return

    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    console = logging.StreamHandler()
    console.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    root.addHandler(console)
    root.addHandler(_make_handler(logs_dir / "app.log"))

    collector = logging.getLogger("collector")
    collector.setLevel(root.level)
    collector.addHandler(_make_handler(logs_dir / "collector.log"))
    collector.propagate = True

    root._tech_hype_configured = True  # type: ignore[attr-defined]


def get_collector_logger() -> logging.Logger:
    return logging.getLogger("collector")
