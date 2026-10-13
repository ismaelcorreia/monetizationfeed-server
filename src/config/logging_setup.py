"""
Logging — structured, consistent, single entry point.
"""
from __future__ import annotations

import logging
import sys
from typing import Optional


def configure_logging(level: str = "INFO", name: Optional[str] = None) -> logging.Logger:
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)

    root = logging.getLogger(name or "news_engine")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not root.handlers:
        root.addHandler(handler)

    return root


def get_logger(module: str) -> logging.Logger:
    return logging.getLogger(f"news_engine.{module}")
