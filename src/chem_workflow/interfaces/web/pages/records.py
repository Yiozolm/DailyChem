"""Experiment-record Streamlit page."""

from __future__ import annotations

from typing import cast

import streamlit as st

from chem_workflow.ai.schemas import (
    ExperimentRecordDraft,
    LLMInputError,
    LLMServiceError,
)
from chem_workflow.ai.workflows import polish_record
from chem_workflow.interfaces.web.components.common import (
    _downloadable_code,
    _page_header,
    _safe_state_file_stem,
    _state_text,
)
from chem_workflow.interfaces.web.components.llm import (
    _llm_settings_expander,
    _render_llm_draft,
)
from chem_workflow.interfaces.web.components.support import (
    optional_text,
    parse_material_lines,
    split_nonempty_lines,
)
from chem_workflow.records import (
    Characterization,
    Language,
    ReactionInfo,
    ReactionRecord,
    RecordInputError,
    YieldInfo,
    render_experiment_record,
)


def _experiment_record_page() -> None:
    _page_header(
        "Experiment Record Generator",
        "填写反应条件、后处理、纯化和表征数据，生成 Markdown 实验记录初稿。",
    )

    with st.form("record_form"):
        compound_id = st.text_input("Compound ID", value=_state_text("compound_id", "C001"))
        product_name = st.text_input("Product name", value="ethyl benzoate")
        smiles = st.text_input("SMILES", value=_state_text("compound_smiles"))

        col_a, col_b = st.columns(2)
        with col_a:
            starting_materials = st.text_area(
                "Starting materials（每行：name | amount）",
                value="benzoic acid | 1.0 mmol\nethanol | 5 mL",
                height=110,
            )
            solvent = st.text_input("Solvent", value="ethanol")
            temperature = st.text_input("Temperature", value="room temperature")
            workup = st.text_area("Workup", value="quenched with water and extracted with EtOAc")
        with col_b:
            reagents = st.text_area(
                "Reagents（每行：name | amount）",
                value="conc. H2SO4 | catalytic",
                height=110,
            )
            reaction_time = st.text_input("Time", value="12 h")
            purification = st.text_input("Purification", value="column chromatography")
            appearance = st.text_input("Appearance", value="colorless oil")

        col_y1, col_y2, col_lang = st.columns([1, 1, 1])
        with col_y1:
            yield_mass = st.text_input("Yield mass", value="95 mg")
        with col_y2:
            yield_percent = st.text_input("Yield percent", value="63%")
        with col_lang:
            language = cast(Language, st.selectbox("Language", ("en", "zh")))

        st.subheader("Characterization")
        h1_nmr = st.text_area(
            "1H NMR",
            value=_state_text("nmr_1h_text"),
            height=100,
        )
        c13_nmr = st.text_area(
            "13C NMR",
            value=_state_text("nmr_13c_text"),
            height=100,
        )
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            hrms = st.text_input("HRMS", value=_state_text("hrms_text"))
            ms = st.text_input("MS", value="")
        with col_c2:
            ir = st.text_input("IR", value=_state_text("ir_text"))
            uv = st.text_input("UV-vis", value=_state_text("uv_text"))
        other_characterization = st.text_area("Other characterization（每行一条）", value="")

        submitted = st.form_submit_button("生成 Markdown", type="primary")

    if submitted:
        _handle_record_generate(
            compound_id=compound_id,
            product_name=product_name,
            smiles=smiles,
            starting_materials=starting_materials,
            reagents=reagents,
            solvent=solvent,
            temperature=temperature,
            reaction_time=reaction_time,
            workup=workup,
            purification=purification,
            appearance=appearance,
            yield_mass=yield_mass,
            yield_percent=yield_percent,
            h1_nmr=h1_nmr,
            c13_nmr=c13_nmr,
            hrms=hrms,
            ms=ms,
            ir=ir,
            uv=uv,
            other_characterization=other_characterization,
            language=language,
        )

    markdown = st.session_state.get("record_markdown")
    if isinstance(markdown, str) and markdown:
        st.divider()
        st.subheader("Markdown Preview")
        st.markdown(markdown)
        _downloadable_code(
            markdown,
            file_name=f"{_safe_state_file_stem('compound_id')}_experiment_record.md",
            mime="text/markdown",
        )
        _render_record_polish_section(markdown, language)

def _render_record_polish_section(markdown: str, language: Language) -> None:
    st.divider()
    st.subheader("LLM 辅助（draft）")
    st.caption("把上方 Markdown 润色成 supporting-information 风格；输出为 draft，需人工确认。")
    settings = _llm_settings_expander("record")
    if st.button("✨ LLM 润色草稿", key="record_llm_polish", width="stretch"):
        if settings is None:
            return
        try:
            result = polish_record(markdown, settings=settings, language=language)
            st.session_state["record_llm_draft"] = result.output
        except (LLMInputError, LLMServiceError) as error:
            st.error(str(error))
            return

    draft = st.session_state.get("record_llm_draft")
    if isinstance(draft, ExperimentRecordDraft):
        _render_llm_draft(
            title=draft.title or "Polished record draft",
            markdown_text=draft.markdown,
            warnings=draft.warnings,
            file_name=f"{_safe_state_file_stem('compound_id')}_record_llm_draft.md",
            checkbox_key="record_llm_reviewed",
        )

def _handle_record_generate(
    *,
    compound_id: str,
    product_name: str,
    smiles: str,
    starting_materials: str,
    reagents: str,
    solvent: str,
    temperature: str,
    reaction_time: str,
    workup: str,
    purification: str,
    appearance: str,
    yield_mass: str,
    yield_percent: str,
    h1_nmr: str,
    c13_nmr: str,
    hrms: str,
    ms: str,
    ir: str,
    uv: str,
    other_characterization: str,
    language: Language,
) -> None:
    try:
        record = ReactionRecord(
            compound_id=compound_id.strip(),
            product_name=optional_text(product_name),
            smiles=optional_text(smiles),
            reaction=ReactionInfo(
                starting_materials=parse_material_lines(starting_materials),
                reagents=parse_material_lines(reagents),
                solvent=optional_text(solvent),
                temperature=optional_text(temperature),
                time=optional_text(reaction_time),
            ),
            workup=optional_text(workup),
            purification=optional_text(purification),
            appearance=optional_text(appearance),
            yield_=YieldInfo(
                mass=optional_text(yield_mass),
                percent=optional_text(yield_percent),
            ),
            characterization=Characterization(
                h1_nmr=optional_text(h1_nmr),
                c13_nmr=optional_text(c13_nmr),
                hrms=optional_text(hrms),
                ms=optional_text(ms),
                ir=optional_text(ir),
                uv=optional_text(uv),
                other=split_nonempty_lines(other_characterization),
            ),
        )
        markdown = render_experiment_record(record, language=language)
        st.session_state["compound_id"] = record.compound_id
        if record.smiles:
            st.session_state["compound_smiles"] = record.smiles
        st.session_state["record_markdown"] = markdown
        st.success("实验记录 Markdown 已生成。")
    except (RecordInputError, ValueError) as error:
        st.error(str(error))

render = _experiment_record_page

__all__ = ["render"]

