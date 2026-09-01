"""Shared Streamlit components for Agent SDK settings and draft output."""

from __future__ import annotations

from typing import Literal, cast

import streamlit as st

from chem_workflow.ai.schemas import LLMInputError, LLMWarning, OpenAISettings
from chem_workflow.interfaces.web.components.common import _downloadable_code


def _llm_settings_expander(key_prefix: str) -> OpenAISettings | None:
    """Render an optional LLM settings expander and build OpenAISettings.

    API key is never collected here; it is read from environment / `.env` by `from_env`.
    Returns None when the settings are invalid (already surfaced via st.error).
    """
    with st.expander("LLM 设置（可选）"):
        st.caption("API key 只从环境变量或项目 `.env` 读取，不在此页面收集。")
        model = st.text_input(
            "Model（留空用默认）",
            value="",
            key=f"{key_prefix}_llm_model",
            placeholder="gpt-5.4-mini",
        )
        base_url = st.text_input(
            "Base URL（OpenAI-compatible，可选）",
            value="",
            key=f"{key_prefix}_llm_base_url",
            placeholder="https://api.openai.com/v1",
        )
        api_mode = st.selectbox(
            "API mode",
            ("responses", "chat-completions"),
            key=f"{key_prefix}_llm_api_mode",
        )
    try:
        return OpenAISettings.from_env(
            model=model or None,
            base_url=base_url or None,
            api_mode=cast("Literal['responses', 'chat-completions']", api_mode),
        )
    except LLMInputError as error:
        st.error(str(error))
        return None

def _render_llm_draft(
    *,
    title: str,
    markdown_text: str,
    warnings: list[LLMWarning],
    file_name: str,
    checkbox_key: str,
) -> None:
    """Render an LLM draft with a draft badge, warnings, copy block, and review checkbox."""
    st.subheader(title)
    st.caption("⚠️ DRAFT —— 不可直接作为最终结论 / supporting information，请人工复核后再使用。")

    severity_icon = {"info": "ℹ️", "warning": "⚠️", "risk": "🛑"}
    if warnings:
        st.markdown("**Warnings**")
        for warning in warnings:
            icon = severity_icon.get(warning.severity, "⚠️")
            st.markdown(f"- {icon} `{warning.code}` — {warning.message}")
    else:
        st.caption("（无 warnings）")

    st.markdown(markdown_text)
    _downloadable_code(markdown_text, file_name=file_name, mime="text/markdown")
    st.checkbox("✅ I reviewed this draft", key=checkbox_key)

__all__ = ["_llm_settings_expander", "_render_llm_draft"]

