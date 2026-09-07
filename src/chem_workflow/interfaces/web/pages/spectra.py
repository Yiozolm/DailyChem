"""HRMS, IR, and UV-vis Streamlit page."""

from __future__ import annotations

import streamlit as st

from chem_workflow.interfaces.web.components.common import (
    _downloadable_code,
    _optional_float,
    _page_header,
    _safe_state_file_stem,
    _state_text,
)
from chem_workflow.interfaces.web.components.context import CONFIG
from chem_workflow.interfaces.web.components.support import optional_text
from chem_workflow.spectroscopy.hrms import (
    MSInputError,
    available_adducts,
    compute_hrms,
    format_hrms,
    hrms_from_manual,
)
from chem_workflow.spectroscopy.ir import IRInputError, format_ir, parse_ir_peaks
from chem_workflow.spectroscopy.uv import UVInputError, format_uv, parse_uv_peaks


def _spectra_page() -> None:
    _page_header(
        "MS / IR / UV",
        "生成 HRMS m/z、IR 和 UV-vis 标准表征文本；结果可自动带入实验记录。",
    )

    hrms_tab, ir_tab, uv_tab = st.tabs(["HRMS", "IR", "UV-vis"])
    with hrms_tab:
        _hrms_section()
    with ir_tab:
        _ir_section()
    with uv_tab:
        _uv_section()

def _hrms_section() -> None:
    mode = st.radio(
        "Calculated m/z 来源",
        ("从结构自动计算", "手动输入 calc m/z"),
        horizontal=True,
        key="hrms_mode",
    )
    col_a, col_b = st.columns(2)
    with col_a:
        adducts = available_adducts()
        adduct_index = (
            adducts.index(CONFIG.default_adduct) if CONFIG.default_adduct in adducts else 0
        )
        adduct = st.selectbox("Adduct", adducts, index=adduct_index, key="hrms_adduct")
        ionization = st.text_input(
            "Ionization", value=CONFIG.default_ionization, key="hrms_ionization"
        )
    with col_b:
        found = st.text_input("Found m/z（可选）", value="", key="hrms_found")

    smiles = ""
    ion_formula = ""
    calc = ""
    if mode == "从结构自动计算":
        smiles = st.text_input(
            "SMILES",
            value=_state_text("compound_smiles", "CCOC(=O)c1ccccc1"),
            key="hrms_smiles",
        )
    else:
        ion_formula = st.text_input("Ion formula", value="C9H10O2Na", key="hrms_ion_formula")
        calc = st.text_input("Calculated m/z", value="173.0573", key="hrms_calc")

    if st.button("生成 HRMS", type="primary", width="stretch", key="hrms_generate"):
        _handle_hrms_generate(
            mode=mode,
            smiles=smiles,
            ion_formula=ion_formula,
            calc=calc,
            adduct=adduct,
            ionization=ionization,
            found=found,
        )

    text = st.session_state.get("hrms_text")
    if isinstance(text, str) and text:
        st.divider()
        _downloadable_code(
            text,
            file_name=f"{_safe_state_file_stem('compound_id')}_hrms.txt",
            mime="text/plain",
        )

def _handle_hrms_generate(
    *,
    mode: str,
    smiles: str,
    ion_formula: str,
    calc: str,
    adduct: str,
    ionization: str,
    found: str,
) -> None:
    try:
        found_mz = _optional_float(found, label="Found m/z")
        if mode == "手动输入 calc m/z":
            calc_mz = _optional_float(calc, label="Calculated m/z")
            if calc_mz is None or not optional_text(ion_formula):
                st.warning("手动模式需要同时填写 Ion formula 和 Calculated m/z。")
                return
            result = hrms_from_manual(
                ion_formula=ion_formula,
                calculated_mz=calc_mz,
                adduct=adduct,
                ionization=ionization,
                found_mz=found_mz,
            )
        else:
            if optional_text(smiles) is None:
                st.warning("请提供 SMILES。")
                return
            result = compute_hrms(
                smiles=smiles,
                adduct=adduct,
                ionization=ionization,
                found_mz=found_mz,
            )
        st.session_state["hrms_text"] = format_hrms(result)
        st.success("HRMS 文本已生成。")
    except (MSInputError, ValueError) as error:
        st.error(str(error))

def _ir_section() -> None:
    technique = st.text_input("Technique", value="neat", key="ir_technique")
    include_intensity = st.checkbox("保留强度标签", value=False, key="ir_include_intensity")
    peaks = st.text_area(
        "IR 波数列表（逗号/空白/换行分隔，可带强度，如 1715 s）",
        value="3050, 2920, 1715, 1600, 1450",
        height=120,
        key="ir_peaks",
    )

    if st.button("生成 IR", type="primary", width="stretch", key="ir_generate"):
        try:
            spectrum = parse_ir_peaks(peaks, technique=technique)
            st.session_state["ir_text"] = format_ir(
                spectrum, include_intensity=include_intensity
            )
            st.success("IR 文本已生成。")
        except IRInputError as error:
            st.error(str(error))

    text = st.session_state.get("ir_text")
    if isinstance(text, str) and text:
        st.divider()
        _downloadable_code(
            text,
            file_name=f"{_safe_state_file_stem('compound_id')}_ir.txt",
            mime="text/plain",
        )

def _uv_section() -> None:
    solvent = st.text_input("Solvent", value="MeOH", key="uv_solvent")
    peaks = st.text_area(
        "UV-vis λmax 列表（逗号/换行分隔，可带 ε，如 254 (12000)）",
        value="254 (12000), 320 (4500)",
        height=120,
        key="uv_peaks",
    )

    if st.button("生成 UV-vis", type="primary", width="stretch", key="uv_generate"):
        try:
            spectrum = parse_uv_peaks(peaks, solvent=solvent)
            st.session_state["uv_text"] = format_uv(spectrum)
            st.success("UV-vis 文本已生成。")
        except UVInputError as error:
            st.error(str(error))

    text = st.session_state.get("uv_text")
    if isinstance(text, str) and text:
        st.divider()
        _downloadable_code(
            text,
            file_name=f"{_safe_state_file_stem('compound_id')}_uv.txt",
            mime="text/plain",
        )

render = _spectra_page

__all__ = ["render"]

