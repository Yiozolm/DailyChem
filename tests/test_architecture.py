"""Import-boundary checks for the functional package refactor."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "chem_workflow"
DOMAIN_PACKAGES = ("core", "compounds", "spectroscopy", "records", "archive", "history")
FORBIDDEN_ROOT_IMPORTS = {"agents", "openai", "streamlit", "typer"}
DEPRECATED_LLM_SYMBOLS = ("LLMClientProtocol", "OpenAIResponsesClient", "parse_structured")


def test_canonical_domain_packages_do_not_import_delivery_or_agent_sdks() -> None:
    violations: list[str] = []
    for package_name in DOMAIN_PACKAGES:
        package_dir = PACKAGE_ROOT / package_name
        if not package_dir.exists():
            continue
        for path in sorted(package_dir.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                imported = _root_import(node)
                if imported in FORBIDDEN_ROOT_IMPORTS:
                    relative = path.relative_to(PACKAGE_ROOT).as_posix()
                    violations.append(f"{relative}:{node.lineno} imports {imported}")

    assert not violations, "Forbidden architecture imports:\n" + "\n".join(violations)


def test_deprecated_llm_call_layer_is_removed() -> None:
    violations: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for symbol in DEPRECATED_LLM_SYMBOLS:
            if symbol in text:
                relative = path.relative_to(PACKAGE_ROOT).as_posix()
                violations.append(f"{relative} contains deprecated {symbol}")
    assert not violations, "Deprecated LLM layer references:\n" + "\n".join(violations)


def test_openai_client_is_owned_by_agent_sdk_bootstrap() -> None:
    allowed = "ai/sdk/bootstrap.py"
    violations: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        relative = path.relative_to(PACKAGE_ROOT).as_posix()
        if relative == allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if _root_import(node) == "openai":
                violations.append(f"{relative}:{node.lineno} imports openai directly")
    assert not violations, "Direct OpenAI client imports:\n" + "\n".join(violations)


def _root_import(node: ast.AST) -> str | None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            root = alias.name.split(".", 1)[0]
            if root in FORBIDDEN_ROOT_IMPORTS:
                return root
    if isinstance(node, ast.ImportFrom) and node.module:
        return node.module.split(".", 1)[0]
    return None
