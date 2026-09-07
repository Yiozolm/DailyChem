"""DailyChem Streamlit Web UI router."""

from __future__ import annotations

import streamlit as st

from chem_workflow.interfaces.web.components.common import _apply_theme
from chem_workflow.interfaces.web.pages.archive import render as _project_export_page
from chem_workflow.interfaces.web.pages.assignment import render as _assignment_page
from chem_workflow.interfaces.web.pages.compound import render as _compound_setup_page
from chem_workflow.interfaces.web.pages.history import render as _history_search_page
from chem_workflow.interfaces.web.pages.nmr import render as _nmr_formatter_page
from chem_workflow.interfaces.web.pages.records import render as _experiment_record_page
from chem_workflow.interfaces.web.pages.spectra import render as _spectra_page


def main() -> None:
    """Render the Streamlit app."""
    st.set_page_config(
        page_title="DailyChem Workflow",
        page_icon="🧪",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _apply_theme()
    _render_sidebar()

    page = st.sidebar.radio(
        "Workflow",
        (
            "1 · Compound Setup",
            "2 · NMR Formatter",
            "3 · MS / IR / UV",
            "4 · Experiment Record",
            "5 · Project Export",
            "6 · NMR Assignment",
            "7 · History Search",
        ),
    )

    if page.startswith("1"):
        _compound_setup_page()
    elif page.startswith("2"):
        _nmr_formatter_page()
    elif page.startswith("3"):
        _spectra_page()
    elif page.startswith("4"):
        _experiment_record_page()
    elif page.startswith("5"):
        _project_export_page()
    elif page.startswith("6"):
        _assignment_page()
    else:
        _history_search_page()

def _render_sidebar() -> None:
    st.sidebar.title("DailyChem")
    st.sidebar.caption("结构 → NMR → 实验记录 → 项目归档")
    st.sidebar.divider()
    st.sidebar.markdown(
        """
        **MVP 范围**

        - 结构：SMILES / MOL / SDF / CDX / CDXML
        - NMR：MestReNova multiplet table
        - MS / IR / UV：HRMS m/z、IR / UV-vis 文本
        - 记录：Markdown 初稿
        - 导出：标准 compound 文件夹 + zip
        - Assignment：候选归属 + 人工确认
        - 历史检索：子结构 / 相似度（本地 SQLite）
        """
    )

if __name__ == "__main__":
    main()

