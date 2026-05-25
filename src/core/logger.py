import logging
import sys
from pathlib import Path

_LOG_FORMAT = "%(asctime)s [%(levelname)-7s] %(message)s"
_LOG_DATE = "%H:%M:%S"


def setup_logger(name: str = None, level: int = logging.INFO, log_file: Path = None) -> logging.Logger:
    logger = logging.getLogger(name or __name__)

    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    fmt = logging.Formatter(_LOG_FORMAT, _LOG_DATE)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    sh.setLevel(level)
    logger.addHandler(sh)

    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        fh.setLevel(level)
        logger.addHandler(fh)

    return logger
