import logging
from functools import lru_cache
from pathlib import Path

from gugabobo.config import get_settings


@lru_cache
def get_logger() -> logging.Logger:
    settings = get_settings()
    log_path = Path(settings.log_dir) / "gugabobo.log"
    logger = logging.getLogger("gugabobo")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    return logger


def read_log_lines(limit: int = 100) -> list[str]:
    settings = get_settings()
    log_path = Path(settings.log_dir) / "gugabobo.log"
    if not log_path.exists():
        return []
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-limit:]
