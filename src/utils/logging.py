"""Single import point for structured logging.

Uses `rich` for colourful terminal output and falls back to stdlib if
`rich` isn't installed (so the data pipeline still runs in minimal envs).
"""

from __future__ import annotations

import logging
import os
import sys


def get_logger(name: str = "ocean_across") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logger.setLevel(level)

    try:
        from rich.logging import RichHandler

        handler: logging.Handler = RichHandler(
            rich_tracebacks=True, show_path=False, markup=True
        )
        fmt = "%(message)s"
    except ImportError:  # pragma: no cover
        handler = logging.StreamHandler(sys.stderr)
        fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"

    handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
