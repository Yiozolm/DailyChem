"""Access immutable resources shipped inside the ``chem_workflow`` package."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

_RESOURCE_PACKAGE = "chem_workflow.resources"


class ResourceError(ValueError):
    """Raised when a required packaged resource cannot be resolved or read."""


def resource_path(*parts: str) -> Path:
    """Return the installed filesystem path for one packaged resource.

    Wheels are installed as ordinary files by the supported ``uv`` workflow. Resource lookup is
    centralized here so feature modules never depend on their own directory depth.
    """
    _validate_parts(parts)
    resource = files(_RESOURCE_PACKAGE).joinpath(*parts)
    if not resource.is_file():
        relative = "/".join(parts)
        raise ResourceError(f"找不到内置资源：{relative}")
    return Path(str(resource))


def read_resource_text(*parts: str) -> str:
    """Read one UTF-8 text resource from the installed package."""
    _validate_parts(parts)
    resource = files(_RESOURCE_PACKAGE).joinpath(*parts)
    if not resource.is_file():
        relative = "/".join(parts)
        raise ResourceError(f"找不到内置资源：{relative}")
    try:
        return resource.read_text(encoding="utf-8")
    except OSError as e:
        relative = "/".join(parts)
        raise ResourceError(f"无法读取内置资源：{relative}") from e


def _validate_parts(parts: tuple[str, ...]) -> None:
    if not parts:
        raise ResourceError("资源路径不能为空")
    for part in parts:
        if not part or part in {".", ".."} or "/" in part or "\\" in part:
            raise ResourceError(f"非法资源路径片段：{part!r}")
