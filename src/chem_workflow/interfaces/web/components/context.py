"""Shared immutable Web application configuration."""

from chem_workflow.core.config import load_config

CONFIG = load_config()

__all__ = ["CONFIG"]
