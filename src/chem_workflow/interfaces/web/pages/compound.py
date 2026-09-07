"""Compound setup Streamlit page."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import streamlit as st

from chem_workflow.compounds.structure import (
    StructureInputError,
    draw_structure,
    load_structure,
    mol_info,
    parse_smiles,
)
from chem_workflow.interfaces.web.components.common import (
    _page_header,
    _render_svg,
    _show_compound_metrics,
    _state_text,
)
from chem_workflow.interfaces.web.components.support import UploadedFileLike, write_uploaded_file


def _compound_setup_page() -> None:
    _page_header(
        "Compound Setup",
        "从 SMILES 或结构文件生成 canonical SMILES、分子式、分子量和带 atom index 的结构图。",
    )

    left, right = st.columns([0.95, 1.05], gap="large")
    with left:
        compound_id = st.text_input(
            "Compound ID",
            value=_state_text("compound_id", "C001"),
            help="例如 C001 / B-17；用于后续实验记录和项目归档。",
        )
        input_mode = st.radio("结构输入方式", ("SMILES", "上传结构文件"), horizontal=True)
        smiles = ""
        uploaded = None
        if input_mode == "SMILES":
            smiles = st.text_area(
                "SMILES",
                value=_state_text("compound_smiles", "CCOC(=O)c1ccccc1"),
                height=90,
                help="输入单个目标化合物的 SMILES。",
            )
        else:
            uploaded = st.file_uploader(
                "上传 MOL / SDF / CDX / CDXML / SMI",
                type=["mol", "sdf", "cdx", "cdxml", "smi", "smiles"],
            )
        show_atom_index = st.checkbox("显示 atom index", value=True)

        if st.button("解析结构", type="primary", width="stretch"):
            _handle_structure_parse(
                compound_id=compound_id,
                input_mode=input_mode,
                smiles=smiles,
                uploaded=uploaded,
                show_atom_index=show_atom_index,
            )

    with right:
        info = st.session_state.get("compound_info")
        svg = st.session_state.get("compound_svg")
        if isinstance(info, dict):
            _show_compound_metrics(info)
        else:
            st.info("解析结构后，这里会显示分子信息。")
        if isinstance(svg, str) and svg:
            _render_svg(svg, height=430)

def _handle_structure_parse(
    *,
    compound_id: str,
    input_mode: str,
    smiles: str,
    uploaded: object,
    show_atom_index: bool,
) -> None:
    try:
        with TemporaryDirectory() as tmp:
            if input_mode == "SMILES":
                mol = parse_smiles(smiles)
            else:
                if uploaded is None:
                    st.warning("请先上传一个结构文件。")
                    return
                path = write_uploaded_file(cast(UploadedFileLike, uploaded), tmp)
                mol = load_structure(path)

            info = mol_info(mol)
            svg_path = Path(tmp) / "structure.svg"
            draw_structure(mol, svg_path, show_atom_index=show_atom_index)
            st.session_state["compound_id"] = compound_id.strip() or "C001"
            st.session_state["compound_info"] = info
            st.session_state["compound_smiles"] = str(info["smiles"])
            st.session_state["compound_svg"] = svg_path.read_text(encoding="utf-8")
            st.success("结构解析完成。")
    except (StructureInputError, ValueError) as error:
        st.error(str(error))

render = _compound_setup_page

__all__ = ["render"]

