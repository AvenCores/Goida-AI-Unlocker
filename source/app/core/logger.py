import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

logger = logging.getLogger("goida_unlocker")
logger.addHandler(logging.NullHandler())


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Настраивает логирование один раз из main()."""
    if getattr(setup_logging, "_done", False):
        return logger
    setup_logging._done = True  # type: ignore[attr-defined]
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    try:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    except Exception:
        pass
    try:
        log_dir = Path.home() / ".goida-ai-unlocker" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            str(log_dir / "app.log"), maxBytes=512 * 1024,
            backupCount=3, encoding="utf-8",
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass
    logger.propagate = False
    return logger
