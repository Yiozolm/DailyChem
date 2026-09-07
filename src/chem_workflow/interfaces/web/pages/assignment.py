"""NMR assignment Streamlit page."""

from __future__ import annotations

from tempfile import TemporaryDirectory
from typing import cast

import streamlit as st

from chem_workflow.ai.schemas import AssignmentSummaryDraft, LLMInputError, LLMServiceError
from chem_workflow.ai.workflows import summarize_assignment as llm_summarize_assignment
from chem_workflow.compounds.structure import StructureInputError, load_structure, parse_smiles
from chem_workflow.interfaces.web.components.common import (
    Nucleus,
    _downloadable_code,
    _page_header,
    _safe_state_file_stem,
    _state_text,
)
from chem_workflow.interfaces.web.components.context import CONFIG
from chem_workflow.interfaces.web.components.llm import (
    _llm_settings_expander,
    _render_llm_draft,
)
from chem_workflow.interfaces.web.components.support import (
    UploadedFileLike,
    optional_text,
    write_uploaded_file,
)
from chem_workflow.interfaces.web.pages.nmr import _read_nmr_source
from chem_workflow.spectroscopy.assignment import (
    AssignmentError,
    assign_nmr,
    assignment_rows_for_review,
    render_assignment_draft,
)
from chem_workflow.spectroscopy.nmr.parsing import (
    NMRInputError,
    parse_mestrenova_multiplet_table,
    parse_shift_list,
)


def _assignment_page() -> None:
    _page_header(
        "NMR Assignment Draft",
        "用规则库和结构特征生成 1H / 13C 候选归属；结果必须人工确认。",
    )

    left, right = st.columns([0.95, 1.05], gap="large")
    with left:
        nucleus = cast(Nucleus, st.radio(
            "核种", ("1H", "13C"), horizontal=True, key="assignment_nucleus"
        ))
        structure_source = st.radio(
            "结构来源",
            ("使用当前 SMILES", "手动输入 SMILES", "上传结构文件"),
            horizontal=True,
            key="assignment_structure_source",
        )
        smiles = _state_text("compound_smiles", "COc1ccccc1")
        uploaded_structure = None
        if structure_source == "手动输入 SMILES":
            smiles = st.text_area("SMILES", value=smiles, height=80, key="assignment_smiles")
        elif structure_source == "上传结构文件":
            uploaded_structure = st.file_uploader(
                "上传 MOL / SDF / CDX / CDXML / SMI",
                type=["mol", "sdf", "cdx", "cdxml", "smi", "smiles"],
                key="assignment_structure_upload",
            )

        col_freq, col_solvent = st.columns(2)
        with col_freq:
            frequency = st.number_input(
                "Frequency (MHz)",
                min_value=0.0,
                value=(
                    CONFIG.default_frequency_13c
                    if nucleus == "13C"
                    else CONFIG.default_frequency_1h
                ),
                step=1.0,
                key="assignment_frequency",
            )
        with col_solvent:
            solvent = st.text_input(
                "Solvent", value=CONFIG.default_solvent, key="assignment_solvent"
            )

        if nucleus == "1H":
            nmr_hint = "粘贴 1H MestReNova multiplet table"
            nmr_default = "Name\tShift\tH's\tClass\nA\t7.25\t5\tm\nB\t3.80\t3\ts\n"
        else:
            nmr_hint = "粘贴 13C 化学位移列表（逗号/换行分隔）"
            nmr_default = "166.7, 132.8, 130.5, 129.6, 128.4, 60.9, 14.4"

        nmr_mode = st.radio("peak list 输入方式", ("上传文件", "粘贴文本"), horizontal=True)
        uploaded_nmr = None
        inline_nmr = ""
        if nmr_mode == "上传文件":
            uploaded_nmr = st.file_uploader(
                "上传 peak list（TSV / CSV / TXT）",
                type=["tsv", "csv", "txt"],
                key="assignment_nmr_upload",
            )
        else:
            inline_nmr = st.text_area(
                nmr_hint,
                value=nmr_default,
                height=220,
                key="assignment_nmr_inline",
            )

        if st.button("生成 assignment 草稿", type="primary", width="stretch"):
            _handle_assignment_generate(
                nucleus=nucleus,
                structure_source=structure_source,
                smiles=smiles,
                uploaded_structure=uploaded_structure,
                frequency=frequency,
                solvent=solvent,
                uploaded_nmr=uploaded_nmr,
                inline_nmr=inline_nmr,
            )

    with right:
        _show_assignment_result()

def _handle_assignment_generate(
    *,
    nucleus: Nucleus,
    structure_source: str,
    smiles: str,
    uploaded_structure: object,
    frequency: float,
    solvent: str,
    uploaded_nmr: object,
    inline_nmr: str,
) -> None:
    try:
        with TemporaryDirectory() as tmp:
            if structure_source == "上传结构文件":
                if uploaded_structure is None:
                    st.warning("请先上传结构文件。")
                    return
                structure_path = write_uploaded_file(
                    cast(UploadedFileLike, uploaded_structure), tmp
                )
                mol = load_structure(structure_path)
            else:
                smiles_input = optional_text(smiles)
                if smiles_input is None:
                    st.warning("请提供 SMILES，或切换到上传结构文件。")
                    return
                mol = parse_smiles(smiles_input)

            nmr_source = _read_nmr_source(uploaded=uploaded_nmr, inline_text=inline_nmr)
            if nucleus == "1H":
                spectrum = parse_mestrenova_multiplet_table(
                    nmr_source,
                    nucleus="1H",
                    frequency_mhz=frequency,
                    solvent=optional_text(solvent),
                )
            else:
                spectrum = parse_shift_list(
                    nmr_source,
                    nucleus=nucleus,
                    frequency_mhz=frequency,
                    solvent=optional_text(solvent),
                )
            draft = assign_nmr(mol, spectrum)
            markdown = render_assignment_draft(draft)
            st.session_state["assignment_markdown"] = markdown
            st.session_state["assignment_rows"] = assignment_rows_for_review(draft)
            st.session_state["assignment_warnings"] = [
                {"severity": w.severity, "code": w.code, "message": w.message}
                for w in draft.warnings
            ]
            st.session_state["compound_smiles"] = draft.compound_smiles
            st.success("assignment 草稿已生成；请人工确认后再使用。")
    except (AssignmentError, NMRInputError, StructureInputError, ValueError) as error:
        st.error(str(error))

def _render_assignment_warnings() -> None:
    warnings = st.session_state.get("assignment_warnings")
    if not isinstance(warnings, list):
        return
    for warning in warnings:
        code = warning.get("code", "")
        message = warning.get("message", "")
        if code == "signal_count_match":
            st.success(f"✅ {message}")
        elif code == "signal_count_mismatch":
            st.warning(f"⚠️ {message}")

def _show_assignment_result() -> None:
    markdown = st.session_state.get("assignment_markdown")
    rows = st.session_state.get("assignment_rows")
    if not isinstance(markdown, str) or not markdown:
        st.info("生成后这里会显示候选归属、风险提示和人工确认表。")
        return

    _render_assignment_warnings()

    st.subheader("Editable review table")
    if isinstance(rows, list):
        edited = st.data_editor(
            rows,
            width="stretch",
            num_rows="fixed",
            column_config={
                "status": st.column_config.SelectboxColumn(
                    "status",
                    options=["candidate", "needs_review", "confirmed"],
                    required=True,
                )
            },
            disabled=["peak", "integration", "multiplicity", "candidates"],
        )
        st.caption("可在 selected_assignment / manual_note 中人工修改；确认后再标记 confirmed。")
        st.session_state["assignment_rows"] = edited

    st.subheader("Markdown draft")
    _downloadable_code(
        markdown,
        file_name=f"{_safe_state_file_stem('compound_id')}_assignment_draft.md",
        mime="text/markdown",
    )
    _render_assignment_summary_section(markdown)

def _render_assignment_summary_section(markdown: str) -> None:
    st.divider()
    st.subheader("LLM 辅助（draft）")
    st.caption("把候选归属整理成可读的复核摘要；输出为 draft，assignment 仍为候选。")
    settings = _llm_settings_expander("assignment")
    if st.button("📝 Summarize for review", key="assignment_llm_summary", width="stretch"):
        if settings is None:
            return
        try:
            result = llm_summarize_assignment(markdown, settings=settings)
            st.session_state["assignment_llm_draft"] = result.output
        except (LLMInputError, LLMServiceError) as error:
            st.error(str(error))
            return

    draft = st.session_state.get("assignment_llm_draft")
    if isinstance(draft, AssignmentSummaryDraft):
        _render_llm_draft(
            title="Assignment review summary",
            markdown_text=draft.summary_markdown,
            warnings=draft.warnings,
            file_name=f"{_safe_state_file_stem('compound_id')}_assignment_summary.md",
            checkbox_key="assignment_llm_reviewed",
        )

render = _assignment_page

__all__ = ["render"]

