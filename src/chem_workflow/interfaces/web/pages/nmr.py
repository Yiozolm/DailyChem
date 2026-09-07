"""NMR formatter Streamlit page."""

from __future__ import annotations

from typing import cast

import streamlit as st

from chem_workflow.interfaces.web.components.common import (
    Nucleus,
    _downloadable_code,
    _nucleus_selectbox,
    _page_header,
    _safe_state_file_stem,
    _state_text,
)
from chem_workflow.interfaces.web.components.context import CONFIG
from chem_workflow.interfaces.web.components.support import UploadedFileLike, optional_text
from chem_workflow.spectroscopy.nmr.formatting import (
    NMRFormatError,
    NMRFormatOptions,
    format_nmr_spectrum,
)
from chem_workflow.spectroscopy.nmr.parsing import (
    NMRInputError,
    parse_mestrenova_multiplet_table,
)

SUPPORTED_FORMAT_NUCLEI = ("1H", "13C", "19F", "31P")

def _nmr_formatter_page() -> None:
    _page_header(
        "NMR Formatter",
        "把 MestReNova multiplet table 转成可直接放进实验记录或 SI 的 NMR 文本。",
    )

    left, right = st.columns([1, 1], gap="large")
    with left:
        nucleus = _nucleus_selectbox()
        default_frequency = {
            "13C": CONFIG.default_frequency_13c,
            "19F": 376.0,
            "31P": 162.0,
        }.get(nucleus, CONFIG.default_frequency_1h)
        frequency = st.number_input(
            "Frequency (MHz)",
            min_value=0.0,
            value=default_frequency,
            step=1.0,
        )
        solvent = st.text_input("Solvent", value=CONFIG.default_solvent)
        sample_id = st.text_input("Sample ID", value=_state_text("compound_id", "C001"))
        include_assignment = st.checkbox("保留 assignment", value=False)
        sort_descending = st.checkbox("按 δ 从高到低排序", value=True)

        input_mode = st.radio("Peak list 输入方式", ("上传文件", "粘贴文本"), horizontal=True)
        uploaded = None
        inline_text = ""
        if input_mode == "上传文件":
            uploaded = st.file_uploader("上传 TSV / CSV / TXT", type=["tsv", "csv", "txt"])
        else:
            inline_text = st.text_area(
                "粘贴 MestReNova multiplet table",
                height=260,
                placeholder="Name\tShift\tRange\tH's\tIntegral\tClass\tJ's\nA (s)\t7.26\t...",
            )

        if st.button("格式化 NMR", type="primary", width="stretch"):
            _handle_nmr_format(
                nucleus=nucleus,
                frequency=frequency,
                solvent=solvent,
                sample_id=sample_id,
                include_assignment=include_assignment,
                sort_descending=sort_descending,
                uploaded=uploaded,
                inline_text=inline_text,
            )

    with right:
        _show_nmr_preview(nucleus)

def _handle_nmr_format(
    *,
    nucleus: Nucleus,
    frequency: float,
    solvent: str,
    sample_id: str,
    include_assignment: bool,
    sort_descending: bool,
    uploaded: object,
    inline_text: str,
) -> None:
    if nucleus not in SUPPORTED_FORMAT_NUCLEI:
        st.error(f"暂不支持 {nucleus} 的 publication-style 格式化。")
        return
    try:
        source = _read_nmr_source(uploaded=uploaded, inline_text=inline_text)
        spectrum = parse_mestrenova_multiplet_table(
            source,
            nucleus=nucleus,
            frequency_mhz=frequency,
            solvent=optional_text(solvent),
            sample_id=optional_text(sample_id),
        )
        formatted = format_nmr_spectrum(
            spectrum,
            NMRFormatOptions(
                include_assignment=include_assignment,
                sort_descending=sort_descending,
            ),
        )
        st.session_state[_nmr_state_key(nucleus)] = formatted
        st.success(f"{nucleus} NMR 已格式化。")
    except (NMRInputError, NMRFormatError, UnicodeDecodeError, ValueError) as error:
        st.error(str(error))

def _read_nmr_source(*, uploaded: object, inline_text: str) -> str:
    if uploaded is not None:
        return cast(UploadedFileLike, uploaded).getvalue().decode("utf-8-sig")
    if optional_text(inline_text) is None:
        raise ValueError("请上传 peak list 文件，或粘贴 MestReNova multiplet table。")
    return inline_text

def _nmr_state_key(nucleus: Nucleus) -> str:
    return f"nmr_{nucleus.lower()}_text"

def _show_nmr_preview(nucleus: Nucleus) -> None:
    text = st.session_state.get(_nmr_state_key(nucleus))
    if isinstance(text, str) and text:
        st.subheader(f"{nucleus} NMR Preview")
        _downloadable_code(
            text,
            file_name=f"{_safe_state_file_stem('compound_id')}_{nucleus}_nmr.txt",
            mime="text/plain",
        )
    else:
        st.info("格式化后，这里会显示可复制的 NMR 文本。")

render = _nmr_formatter_page

__all__ = ["_read_nmr_source", "render"]

