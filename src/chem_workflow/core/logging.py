"""Phase 12 lightweight logging setup for chemwf.

Logging is opt-in and quiet by default (WARNING). Set ``CHEMWF_LOG_LEVEL=INFO`` (or DEBUG) to see
the few informational messages emitted around file-writing operations.
"""

from __future__ import annotations

import logging
import os

_CONFIGURED = False


def configure_logging(level: str | int | None = None) -> None:
    """Configure root logging once, from ``level`` or ``CHEMWF_LOG_LEVEL`` (default WARNING)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    resolved = level if level is not None else os.environ.get("CHEMWF_LOG_LEVEL", "WARNING")
    logging.basicConfig(
        level=_coerce_level(resolved),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger; ensures logging is configured first."""
    configure_logging()
    return logging.getLogger(name)


def _coerce_level(value: str | int) -> int:
    if isinstance(value, int):
        return value
    return logging.getLevelNamesMapping().get(value.strip().upper(), logging.WARNING)
