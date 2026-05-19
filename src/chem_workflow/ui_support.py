"""Small helpers shared by the Streamlit UI.

The UI deliberately stays thin: this module only contains parsing / filesystem helpers that are
easy to unit test, while chemistry-specific work remains in `structure`, `nmr`, `records`, and
`storage`.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Protocol
from zipfile import ZIP_DEFLATED, ZipFile

from chem_workflow.records import Material


class UploadedFileLike(Protocol):
    """Minimal protocol implemented by Streamlit uploaded files."""

    name: str

    def getvalue(self) -> bytes:
        """Return the uploaded file payload."""


def optional_text(value: str | None) -> str | None:
    """Normalize blank UI fields to `None`."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def split_nonempty_lines(text: str | None) -> list[str]:
    """Return stripped non-empty lines from a free-text field."""
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_material_lines(text: str | None) -> list[Material]:
    """Parse material lines from the UI.

    Recommended format is one material per line:

    ```text
    benzoic acid | 1.0 mmol
    ethanol | 5 mL
    ```

    A comma is also accepted as a lightweight fallback: `benzoic acid, 1.0 mmol`.
    Lines without a delimiter are treated as names with an unknown amount.
    """
    materials: list[Material] = []
    for line in split_nonempty_lines(text):
        name, amount = _split_material_line(line)
        if name:
            materials.append(Material(name=name, amount=amount))
    return materials


def write_uploaded_file(uploaded: UploadedFileLike, target_dir: str | Path) -> Path:
    """Write an uploaded file into `target_dir` and return the written path."""
    safe_name = _safe_upload_name(uploaded.name)
    directory = Path(target_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / safe_name
    path.write_bytes(uploaded.getvalue())
    return path


def zip_directory_to_bytes(directory: str | Path) -> bytes:
    """Create a zip archive for `directory` and return it as bytes."""
    root = Path(directory)
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"目录不存在或不是文件夹：{root}")

    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                relative = PurePosixPath(root.name) / PurePosixPath(
                    path.relative_to(root).as_posix()
                )
                archive.write(path, relative.as_posix())
    return buffer.getvalue()


def _split_material_line(line: str) -> tuple[str, str | None]:
    if "|" in line:
        name, amount = line.split("|", 1)
    elif "," in line:
        name, amount = line.split(",", 1)
    else:
        return line.strip(), None
    return line_part(name), optional_text(amount)


def line_part(value: str) -> str:
    """Normalize one delimited material field."""
    return value.strip()


def _safe_upload_name(name: str) -> str:
    safe_name = Path(name).name.strip()
    if not safe_name or safe_name in {".", ".."}:
        raise ValueError("上传文件名无效")
    return safe_name
