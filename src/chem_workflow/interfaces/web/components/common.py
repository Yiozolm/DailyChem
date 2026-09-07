"""Shared Streamlit rendering, state, and theme helpers."""

from __future__ import annotations

from typing import Literal, cast

import streamlit as st

from chem_workflow.interfaces.web.components.support import optional_text

Nucleus = Literal["1H", "13C", "19F", "31P"]

def _downloadable_code(text: str, *, file_name: str, mime: str) -> None:
    st.caption("代码块右上角的 copy 图标可一键复制。")
    st.code(text, language="text")
    st.download_button(
        "下载文本",
        data=text + "\n",
        file_name=file_name,
        mime=mime,
        width="stretch",
    )

def _show_compound_metrics(info: dict[object, object]) -> None:
    st.subheader("Molecular information")
    st.metric("Formula", str(info.get("formula", "—")))
    mw_col, atoms_col = st.columns(2)
    mw_col.metric("MW", str(info.get("mol_weight", "—")))
    atoms_col.metric("Heavy atoms", str(info.get("heavy_atoms", "—")))
    st.text_input("Canonical SMILES", value=str(info.get("smiles", "")), disabled=True)

def _render_svg(svg: str, *, height: int) -> None:
    st.html(
        f"""
        <div class="structure-shell">
          {svg}
        </div>
        <style>
          .structure-shell {{
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: {height - 30}px;
            border: 1px solid #d8d1c5;
            border-radius: 18px;
            background:
              radial-gradient(circle at 20% 10%, rgba(58, 105, 99, 0.10), transparent 28%),
              linear-gradient(135deg, #fffdf8 0%, #f7f0e6 100%);
          }}
          svg {{
            max-width: 100%;
            max-height: {height - 58}px;
          }}
        </style>
        """
    )

def _page_header(title: str, subtitle: str) -> None:
    st.markdown('<div class="eyebrow">Phase 7 · Local Web UI</div>', unsafe_allow_html=True)
    st.title(title)
    st.caption(subtitle)
    st.divider()

def _nucleus_selectbox() -> Nucleus:
    value = st.selectbox("Nucleus", ("1H", "13C", "19F", "31P"))
    return cast(Nucleus, value)

def _state_text(key: str, default: str = "") -> str:
    value = st.session_state.get(key, default)
    if value is None:
        return default
    return str(value)

def _safe_state_file_stem(key: str) -> str:
    raw = _state_text(key, "compound").strip() or "compound"
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in raw)

def _optional_float(value: str, *, label: str) -> float | None:
    text = optional_text(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError as error:
        raise ValueError(f"{label} 必须是数字，得到 {value!r}。") from error

def _apply_theme() -> None:
    st.markdown(
        """
        <style>
          :root {
            --dailychem-ink: #28312e;
            --dailychem-muted: #68746f;
            --dailychem-paper: #fffaf0;
            --dailychem-green: #2f6f64;
          }
          .stApp {
            background:
              radial-gradient(circle at top left, rgba(47, 111, 100, 0.10), transparent 30%),
              linear-gradient(180deg, #fffaf0 0%, #f8f3ea 48%, #f5efe4 100%);
            color: var(--dailychem-ink);
          }
          .block-container {
            padding-top: 4.5rem;
            max-width: 1180px;
          }
          .eyebrow {
            color: var(--dailychem-green);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
          }
          div[data-testid="stMetric"] {
            border: 1px solid #ded6c8;
            border-radius: 16px;
            padding: 0.85rem 1rem;
            background: rgba(255, 255, 255, 0.58);
          }
          section[data-testid="stSidebar"] {
            background: #26332f;
          }
          section[data-testid="stSidebar"] * {
            color: #f8f3ea;
          }
          .stButton > button, .stDownloadButton > button {
            border-radius: 999px;
            border: 1px solid rgba(47, 111, 100, 0.35);
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

__all__ = [
    "Nucleus",
    "_apply_theme",
    "_downloadable_code",
    "_nucleus_selectbox",
    "_optional_float",
    "_page_header",
    "_render_svg",
    "_safe_state_file_stem",
    "_show_compound_metrics",
    "_state_text",
]
