"""DailyChem Streamlit Web UI.

Run locally with:

```bash
uv run streamlit run app.py
```
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, cast

import streamlit as st

from chem_workflow.assignment import (
    AssignmentError,
    assign_1h_nmr,
    assignment_rows_for_review,
    render_assignment_draft,
)
from chem_workflow.config import load_config
from chem_workflow.database import (
    DatabaseError,
    all_compounds,
    connect,
    make_record,
    scan_archive,
    upsert_compound,
)
from chem_workflow.ir import IRInputError, format_ir, parse_ir_peaks
from chem_workflow.llm import (
    polish_record,
)
from chem_workflow.llm import (
    summarize_assignment as llm_summarize_assignment,
)
from chem_workflow.llm_models import (
    AssignmentSummaryDraft,
    ExperimentRecordDraft,
    LLMInputError,
    LLMServiceError,
    LLMWarning,
    OpenAISettings,
)
from chem_workflow.ms import (
    MSInputError,
    available_adducts,
    compute_hrms,
    format_hrms,
    hrms_from_manual,
)
from chem_workflow.nmr import NMRInputError, parse_mestrenova_multiplet_table
from chem_workflow.nmr_formatter import (
    NMRFormatError,
    NMRFormatOptions,
    format_nmr_spectrum,
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
from chem_workflow.search import SearchError, similarity_search, substructure_search
from chem_workflow.storage import RawFileGroup, StorageError, init_compound_archive
from chem_workflow.structure import (
    StructureInputError,
    draw_structure,
    load_structure,
    mol_info,
    parse_smiles,
)
from chem_workflow.ui_support import (
    UploadedFileLike,
    optional_text,
    parse_material_lines,
    split_nonempty_lines,
    write_uploaded_file,
    zip_directory_to_bytes,
)
from chem_workflow.uv import UVInputError, format_uv, parse_uv_peaks

Nucleus = Literal["1H", "13C", "19F", "31P"]
SUPPORTED_FORMAT_NUCLEI = ("1H", "13C")
CONFIG = load_config()


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


def _nmr_formatter_page() -> None:
    _page_header(
        "NMR Formatter",
        "把 MestReNova multiplet table 转成可直接放进实验记录或 SI 的 NMR 文本。",
    )

    left, right = st.columns([1, 1], gap="large")
    with left:
        nucleus = _nucleus_selectbox()
        default_frequency = (
            CONFIG.default_frequency_13c if nucleus == "13C" else CONFIG.default_frequency_1h
        )
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
        st.error("当前 publication-style formatter 只支持 1H / 13C；19F / 31P 留到后续扩展。")
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
        state_key = "nmr_1h_text" if nucleus == "1H" else "nmr_13c_text"
        st.session_state[state_key] = formatted
        st.success(f"{nucleus} NMR 已格式化。")
    except (NMRInputError, NMRFormatError, UnicodeDecodeError, ValueError) as error:
        st.error(str(error))


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


def _project_export_page() -> None:
    _page_header(
        "Project Export",
        "初始化标准化 compound 项目文件夹，并导出 summary Markdown 或 zip 归档。",
    )

    left, right = st.columns([0.95, 1.05], gap="large")
    with left:
        compound_id = st.text_input("Compound ID", value=_state_text("compound_id", "C001"))
        project_dir = st.text_input("Project directory", value="examples/project_demo")
        overwrite = st.checkbox("允许覆盖已有 metadata / summary", value=False)

        source_choice = st.radio(
            "结构来源",
            ("使用当前 SMILES", "手动输入 SMILES", "上传结构文件"),
            horizontal=True,
        )
        smiles = _state_text("compound_smiles")
        uploaded = None
        if source_choice == "手动输入 SMILES":
            smiles = st.text_area("SMILES", value=smiles or "CCOC(=O)c1ccccc1", height=90)
        elif source_choice == "上传结构文件":
            uploaded = st.file_uploader(
                "上传 MOL / SDF / CDX / CDXML / SMI",
                type=["mol", "sdf", "cdx", "cdxml", "smi", "smiles"],
                key="export_structure_upload",
            )

        include_record = st.checkbox(
            "复制当前生成的实验记录到 records/",
            value=bool(st.session_state.get("record_markdown")),
            disabled=not bool(st.session_state.get("record_markdown")),
        )

        if st.button("初始化并导出项目", type="primary", width="stretch"):
            _handle_project_export(
                compound_id=compound_id,
                project_dir=project_dir,
                overwrite=overwrite,
                source_choice=source_choice,
                smiles=smiles,
                uploaded=uploaded,
                include_record=include_record,
            )

    with right:
        _show_export_result()


def _assignment_page() -> None:
    _page_header(
        "NMR Assignment Draft",
        "用规则库和结构特征生成 1H NMR 候选归属；结果必须人工确认。",
    )

    left, right = st.columns([0.95, 1.05], gap="large")
    with left:
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
                "1H Frequency (MHz)",
                min_value=0.0,
                value=CONFIG.default_frequency_1h,
                step=1.0,
                key="assignment_frequency",
            )
        with col_solvent:
            solvent = st.text_input(
                "Solvent", value=CONFIG.default_solvent, key="assignment_solvent"
            )

        nmr_mode = st.radio("1H peak list 输入方式", ("上传文件", "粘贴文本"), horizontal=True)
        uploaded_nmr = None
        inline_nmr = ""
        if nmr_mode == "上传文件":
            uploaded_nmr = st.file_uploader(
                "上传 1H peak list（TSV / CSV / TXT）",
                type=["tsv", "csv", "txt"],
                key="assignment_nmr_upload",
            )
        else:
            inline_nmr = st.text_area(
                "粘贴 1H MestReNova multiplet table",
                value="Name\tShift\tH's\tClass\nA\t7.25\t5\tm\nB\t3.80\t3\ts\n",
                height=220,
                key="assignment_nmr_inline",
            )

        if st.button("生成 assignment 草稿", type="primary", width="stretch"):
            _handle_assignment_generate(
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
            spectrum = parse_mestrenova_multiplet_table(
                nmr_source,
                nucleus="1H",
                frequency_mhz=frequency,
                solvent=optional_text(solvent),
            )
            draft = assign_1h_nmr(mol, spectrum)
            markdown = render_assignment_draft(draft)
            st.session_state["assignment_markdown"] = markdown
            st.session_state["assignment_rows"] = assignment_rows_for_review(draft)
            st.session_state["compound_smiles"] = draft.compound_smiles
            st.success("assignment 草稿已生成；请人工确认后再使用。")
    except (AssignmentError, NMRInputError, StructureInputError, ValueError) as error:
        st.error(str(error))


def _show_assignment_result() -> None:
    markdown = st.session_state.get("assignment_markdown")
    rows = st.session_state.get("assignment_rows")
    if not isinstance(markdown, str) or not markdown:
        st.info("生成后这里会显示候选归属、风险提示和人工确认表。")
        return

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


def _history_search_page() -> None:
    _page_header(
        "History Search",
        "把做过的化合物沉淀到本地 SQLite 库，按子结构 / 相似度检索历史样例。",
    )

    db_path = st.text_input(
        "数据库路径",
        value=_state_text("history_db_path", CONFIG.db_path),
        key="history_db_path",
    )

    ingest_tab, search_tab = st.tabs(["入库", "检索"])
    with ingest_tab:
        _history_ingest_section(db_path)
    with search_tab:
        _history_search_section(db_path)


def _history_ingest_section(db_path: str) -> None:
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**从归档批量导入**")
        project_dir = st.text_input(
            "项目根目录", value=CONFIG.project_dir, key="history_project_dir"
        )
        if st.button("扫描归档并导入", width="stretch", key="history_import"):
            try:
                records = scan_archive(project_dir)
                with closing(connect(db_path)) as conn:
                    for record in records:
                        upsert_compound(conn, record)
                st.success(f"已导入 {len(records)} 个化合物。")
            except DatabaseError as error:
                st.error(str(error))

    with col_b:
        st.markdown("**添加当前化合物**")
        compound_id = st.text_input(
            "Compound ID", value=_state_text("compound_id", "C001"), key="history_add_id"
        )
        smiles = st.text_input(
            "SMILES", value=_state_text("compound_smiles"), key="history_add_smiles"
        )
        if st.button("加入历史库", type="primary", width="stretch", key="history_add"):
            if optional_text(smiles) is None:
                st.warning("请提供 SMILES。")
            else:
                _handle_history_add(db_path, compound_id=compound_id, smiles=smiles)


def _handle_history_add(db_path: str, *, compound_id: str, smiles: str) -> None:
    spectra = {
        "1H": _state_text("nmr_1h_text"),
        "13C": _state_text("nmr_13c_text"),
        "HRMS": _state_text("hrms_text"),
        "IR": _state_text("ir_text"),
        "UV": _state_text("uv_text"),
    }
    try:
        record = make_record(
            compound_id=compound_id,
            smiles=smiles,
            spectra={k: v for k, v in spectra.items() if v},
        )
        with closing(connect(db_path)) as conn:
            upsert_compound(conn, record)
        st.success(
            f"已写入 {record.compound_id}（{record.formula}, MW {record.molecular_weight}）。"
        )
    except DatabaseError as error:
        st.error(str(error))


def _history_search_section(db_path: str) -> None:
    query = st.text_input(
        "查询 SMILES / SMARTS",
        value=_state_text("compound_smiles", "c1ccccc1"),
        key="history_query",
    )
    mode = st.radio(
        "检索方式", ("子结构", "相似度"), horizontal=True, key="history_search_mode"
    )
    threshold = st.slider(
        "相似度阈值", min_value=0.0, max_value=1.0, value=0.7, step=0.05, key="history_threshold"
    )

    if st.button("检索", type="primary", width="stretch", key="history_search_run"):
        _handle_history_search(db_path, query=query, mode=mode, threshold=threshold)

    rows = st.session_state.get("history_search_rows")
    if isinstance(rows, list):
        if rows:
            st.dataframe(rows, width="stretch")
        else:
            st.info("没有匹配的历史化合物。")


def _handle_history_search(db_path: str, *, query: str, mode: str, threshold: float) -> None:
    try:
        with closing(connect(db_path)) as conn:
            records = all_compounds(conn)
        if mode == "子结构":
            hits = substructure_search(records, query)
        else:
            hits = similarity_search(records, query, threshold=threshold)
        st.session_state["history_search_rows"] = [
            {
                "compound_id": hit.compound.compound_id,
                "formula": hit.compound.formula or "",
                "MW": hit.compound.molecular_weight,
                "score": hit.score,
                "smiles": hit.compound.smiles,
            }
            for hit in hits
        ]
        st.success(f"找到 {len(hits)} 个匹配。")
    except (DatabaseError, SearchError) as error:
        st.error(str(error))


def _handle_project_export(
    *,
    compound_id: str,
    project_dir: str,
    overwrite: bool,
    source_choice: str,
    smiles: str,
    uploaded: object,
    include_record: bool,
) -> None:
    try:
        with TemporaryDirectory() as tmp:
            structure_path: Path | None = None
            smiles_input: str | None = None
            if source_choice == "上传结构文件":
                if uploaded is None:
                    st.warning("请先上传结构文件。")
                    return
                structure_path = write_uploaded_file(cast(UploadedFileLike, uploaded), tmp)
            else:
                smiles_input = optional_text(smiles)
                if smiles_input is None:
                    st.warning("请提供 SMILES，或切换到上传结构文件。")
                    return

            raw_groups = _record_raw_groups(
                tmp_dir=Path(tmp),
                compound_id=compound_id,
                include_record=include_record,
            )
            result = init_compound_archive(
                compound_id=compound_id,
                project_dir=Path(project_dir).expanduser(),
                smiles=smiles_input,
                structure_path=structure_path,
                raw_file_groups=raw_groups,
                overwrite=overwrite,
            )
            summary = result.summary_path.read_text(encoding="utf-8")
            zip_bytes = zip_directory_to_bytes(result.compound_dir)
            st.session_state["export_result"] = {
                "compound_dir": str(result.compound_dir),
                "summary": summary,
                "zip_name": f"{result.compound_dir.name}.zip",
                "zip_bytes": zip_bytes,
            }
            st.session_state["compound_id"] = compound_id.strip()
            st.success("项目文件夹已初始化。")
    except (StorageError, StructureInputError, FileNotFoundError, ValueError) as error:
        st.error(str(error))


def _record_raw_groups(
    *,
    tmp_dir: Path,
    compound_id: str,
    include_record: bool,
) -> tuple[RawFileGroup, ...]:
    record_markdown = st.session_state.get("record_markdown")
    if not include_record or not isinstance(record_markdown, str) or not record_markdown:
        return ()
    record_path = tmp_dir / f"{compound_id.strip() or 'compound'}_experiment_record.md"
    record_path.write_text(record_markdown + "\n", encoding="utf-8")
    return (RawFileGroup("record", Path("records"), (record_path,)),)


def _show_export_result() -> None:
    payload = st.session_state.get("export_result")
    if not isinstance(payload, dict):
        st.info("导出完成后，这里会显示 summary 和下载按钮。")
        return

    compound_dir = str(payload.get("compound_dir", ""))
    summary = str(payload.get("summary", ""))
    zip_name = str(payload.get("zip_name", "compound.zip"))
    zip_bytes = payload.get("zip_bytes")

    st.success(f"已生成：`{compound_dir}`")
    st.subheader("Summary")
    st.markdown(summary)
    st.download_button(
        "下载 summary.md",
        data=summary + "\n",
        file_name="summary.md",
        mime="text/markdown",
        width="stretch",
    )
    if isinstance(zip_bytes, bytes):
        st.download_button(
            "下载 compound zip",
            data=zip_bytes,
            file_name=zip_name,
            mime="application/zip",
            width="stretch",
        )


def _read_nmr_source(*, uploaded: object, inline_text: str) -> str:
    if uploaded is not None:
        return cast(UploadedFileLike, uploaded).getvalue().decode("utf-8-sig")
    if optional_text(inline_text) is None:
        raise ValueError("请上传 peak list 文件，或粘贴 MestReNova multiplet table。")
    return inline_text


def _show_nmr_preview(nucleus: Nucleus) -> None:
    if nucleus not in SUPPORTED_FORMAT_NUCLEI:
        st.info("19F / 31P 的输入入口已预留；publication-style formatter 会在后续扩展。")
        return
    state_key = "nmr_1h_text" if nucleus == "1H" else "nmr_13c_text"
    text = st.session_state.get(state_key)
    if isinstance(text, str) and text:
        st.subheader(f"{nucleus} NMR Preview")
        _downloadable_code(
            text,
            file_name=f"{_safe_state_file_stem('compound_id')}_{nucleus}_nmr.txt",
            mime="text/plain",
        )
    else:
        st.info("格式化后，这里会显示可复制的 NMR 文本。")


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


def _show_compound_metrics(info: dict[object, object]) -> None:
    st.subheader("Molecular information")
    col1, col2, col3 = st.columns(3)
    col1.metric("Formula", str(info.get("formula", "—")))
    col2.metric("MW", str(info.get("mol_weight", "—")))
    col3.metric("Heavy atoms", str(info.get("heavy_atoms", "—")))
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


if __name__ == "__main__":
    main()
