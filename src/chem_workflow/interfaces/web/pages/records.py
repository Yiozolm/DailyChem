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
from chem_workflow.compounds.structure import StructureInputError, mol_info, parse_smiles
from chem_workflow.core.config import ConfigError, load_config
from chem_workflow.interfaces.web.components.common import (
    _downloadable_code,
    _page_header,
    _safe_state_file_stem,
)
from chem_workflow.interfaces.web.components.llm import (
    _llm_settings_expander,
    _render_llm_draft,
)
from chem_workflow.interfaces.web.components.support import (
    UploadedFileLike,
    optional_text,
    parse_material_lines,
    split_nonempty_lines,
)
from chem_workflow.ocr import (
    OCRImage,
    OCRRecordDraft,
    OCRRuntimeError,
    OCRRuntimeManager,
    OCRService,
    OCRServiceError,
    check_yield,
    infer_mime_type,
)
from chem_workflow.records import (
    Characterization,
    Language,
    ReactionInfo,
    ReactionRecord,
    RecordInputError,
    YieldInfo,
    render_experiment_record,
    render_record_yaml,
)


def _experiment_record_page() -> None:
    _page_header(
        "Experiment Record Generator",
        "可手动填写，或先拍照识别实验记录，再逐字段校对并生成 Markdown / YAML。",
    )

    _render_ocr_section()

    with st.form("record_form"):
        compound_id = _text_input("Compound ID", "compound_id", "C001")
        product_name = _text_input("Product name", "product_name", "ethyl benzoate")
        smiles = _text_input("SMILES", "compound_smiles", "")

        col_a, col_b = st.columns(2)
        with col_a:
            starting_materials = _text_area(
                "Starting materials（每行：name | amount）",
                "starting_materials",
                "benzoic acid | 1.0 mmol\nethanol | 5 mL",
                height=110,
            )
            procedure = _text_area(
                "Procedure details",
                "procedure",
                "",
                height=120,
                help="保留反应设置、滴加、TLC 或颜色观察等原始步骤；OCR 结果会填入这里。",
            )
            solvent = _text_input("Solvent", "solvent", "ethanol")
            temperature = _text_input("Temperature", "temperature", "room temperature")
            workup = _text_area(
                "Workup", "workup", "quenched with water and extracted with EtOAc"
            )
        with col_b:
            reagents = _text_area(
                "Reagents（每行：name | amount）",
                "reagents",
                "conc. H2SO4 | catalytic",
                height=110,
            )
            reaction_time = _text_input("Time", "reaction_time", "12 h")
            purification = _text_input("Purification", "purification", "column chromatography")
            appearance = _text_input("Appearance", "appearance", "colorless oil")

        col_y1, col_y2, col_lang = st.columns([1, 1, 1])
        with col_y1:
            yield_mass = _text_input("Yield mass", "yield_mass", "95 mg")
        with col_y2:
            yield_percent = _text_input("Yield percent", "yield_percent", "63%")
        with col_lang:
            _ensure_state("record_language", "en")
            language = cast(Language, st.selectbox("Language", ("en", "zh"), key="record_language"))

        st.subheader("Characterization")
        h1_nmr = _text_area("1H NMR", "nmr_1h_text", "", height=100)
        c13_nmr = _text_area("13C NMR", "nmr_13c_text", "", height=100)
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            hrms = _text_input("HRMS", "hrms_text", "")
            ms = _text_input("MS", "ms_text", "")
        with col_c2:
            ir = _text_input("IR", "ir_text", "")
            uv = _text_input("UV-vis", "uv_text", "")
        other_characterization = _text_area(
            "Other characterization（每行一条）", "other_characterization", ""
        )

        submitted = st.form_submit_button("生成 Markdown", type="primary")

    if submitted:
        _handle_record_generate(
            compound_id=compound_id,
            product_name=product_name,
            smiles=smiles,
            starting_materials=starting_materials,
            reagents=reagents,
            procedure=procedure,
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
        yaml_text = st.session_state.get("record_yaml")
        if isinstance(yaml_text, str) and yaml_text:
            st.download_button(
                "下载实验记录 YAML",
                data=yaml_text,
                file_name=f"{_safe_state_file_stem('compound_id')}_experiment_record.yaml",
                mime="application/yaml",
                width="stretch",
            )
        _render_record_polish_section(markdown, language)


def _ensure_state(key: str, default: str) -> None:
    if key not in st.session_state:
        st.session_state[key] = default


def _text_input(label: str, key: str, default: str) -> str:
    _ensure_state(key, default)
    return st.text_input(label, key=key)


def _text_area(label: str, key: str, default: str, **kwargs: object) -> str:
    _ensure_state(key, default)
    return st.text_area(label, key=key, **kwargs)


def _render_ocr_section() -> None:
    with st.expander("📷 从照片生成实验记录（本地 GLM-OCR）", expanded=True):
        st.caption(
            "照片只发送到本机 WSL2 内的 GLM-OCR。识别结果是草稿，必须逐字段核对后再生成记录。"
        )
        camera = st.camera_input("拍摄实验记录", key="ocr_camera")
        uploads = st.file_uploader(
            "或上传一张/多张实验记录照片",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="ocr_uploads",
        )
        if st.button("识别照片", key="ocr_run", type="primary", width="stretch"):
            _handle_ocr_request(camera, uploads)

        draft_payload = st.session_state.get("ocr_draft")
        if isinstance(draft_payload, dict):
            draft = OCRRecordDraft.model_validate(draft_payload)
            _render_ocr_review(draft)


def _handle_ocr_request(camera: object, uploads: object) -> None:
    images: list[OCRImage] = []
    if camera is not None:
        camera_file = cast(UploadedFileLike, camera)
        images.append(
            OCRImage(
                name=getattr(camera_file, "name", "camera.jpg"),
                data=camera_file.getvalue(),
                mime_type=infer_mime_type(getattr(camera_file, "name", "camera.jpg")),
            )
        )
    if isinstance(uploads, list):
        for upload in uploads:
            file = cast(UploadedFileLike, upload)
            name = getattr(file, "name", "upload.jpg")
            images.append(
                OCRImage(name=name, data=file.getvalue(), mime_type=infer_mime_type(name))
            )
    if not images:
        st.warning("请先拍照或上传至少一张图片。")
        return
    try:
        config = load_config().ocr
        manager = OCRRuntimeManager(config)
        with st.spinner("正在启动本地 OCR 服务并识别照片…"):
            manager.start()
            service = OCRService(manager.client())
            draft, raw_response, raw_content = service.recognize(images)
        st.session_state["ocr_draft"] = draft.model_dump(mode="json")
        st.session_state["ocr_raw_response"] = raw_response
        st.session_state["ocr_raw_content"] = raw_content
        st.session_state["ocr_images"] = [
            {
                "name": image.name,
                "mime_type": image.mime_type,
                "data": image.data,
            }
            for image in images
        ]
        st.success(f"已识别 {len(images)} 张照片；请逐字段核对。")
    except (ConfigError, OCRRuntimeError, OCRServiceError, ValueError) as error:
        st.error(str(error))


def _render_ocr_review(draft: OCRRecordDraft) -> None:
    st.subheader("OCR 草稿复核")
    if draft.warnings:
        for warning in draft.warnings:
            st.warning(warning)
    rows: list[dict[str, str]] = []
    for name, field in draft.scalar_fields().items():
        reviewed = st.checkbox(
            f"已核对：{name}",
            value=field.status == "reviewed",
            key=f"ocr_review_{name}",
        )
        rows.append(
            {
                "field": name,
                "value": field.display_value(),
                "source_text": field.source_text or "",
                "status": "reviewed" if reviewed else "needs_review",
            }
        )
    if draft.material_table:
        st.markdown("**试剂表（按照片原文解析）**")
        st.dataframe(
            [row.model_dump(exclude={"source_text"}) for row in draft.material_table],
            hide_index=True,
            width="stretch",
        )
    _render_ocr_yield_check(draft)
    if draft.starting_materials:
        st.markdown("**Starting materials**")
        for item in draft.starting_materials:
            st.write(f"{item.as_form_line()}  ·  {item.source_text or '未提供原文片段'}")
    if draft.reagents:
        st.markdown("**Reagents**")
        for item in draft.reagents:
            st.write(f"{item.as_form_line()}  ·  {item.source_text or '未提供原文片段'}")
    st.dataframe(rows, hide_index=True, width="stretch")
    if draft.raw_text:
        with st.expander("查看原始 OCR 文本"):
            st.text(draft.raw_text)
    if draft.unmapped_text:
        st.info("未映射内容：" + "；".join(draft.unmapped_text))
    if st.button("填入实验记录表单", key="ocr_apply", width="stretch"):
        reviewed_draft = _draft_with_review_states(draft)
        st.session_state["ocr_draft"] = reviewed_draft.model_dump(mode="json")
        _apply_ocr_draft(reviewed_draft)
        st.rerun()


def _render_ocr_yield_check(draft: OCRRecordDraft) -> None:
    """Re-check the yield with the product SMILES once the user has entered it."""
    smiles = str(st.session_state.get("compound_smiles") or "").strip()
    if not smiles or not draft.material_table or not draft.yield_mass.value:
        return
    try:
        product_mw = float(cast(float, mol_info(parse_smiles(smiles))["mol_weight"]))
    except StructureInputError:
        return
    messages = check_yield(
        draft.material_table,
        draft.yield_mass.value,
        draft.yield_percent.value,
        product_mw=product_mw,
    )
    if not messages:
        st.success(f"产率与产物分子量 {product_mw:.2f} g/mol 一致。")
    for message in messages:
        st.warning(message)


def _draft_with_review_states(draft: OCRRecordDraft) -> OCRRecordDraft:
    payload = draft.model_dump(mode="json")
    for name in draft.scalar_fields():
        field_payload = payload.get(name)
        if isinstance(field_payload, dict):
            field_payload["status"] = (
                "reviewed" if st.session_state.get(f"ocr_review_{name}", False) else "needs_review"
            )
    return OCRRecordDraft.model_validate(payload)


def _apply_ocr_draft(draft: OCRRecordDraft) -> None:
    for key, value in draft.form_values().items():
        if value:
            st.session_state[key] = value
    st.session_state["ocr_applied"] = True

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
    procedure: str = "",
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
                procedure=optional_text(procedure),
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
        st.session_state["record_yaml"] = render_record_yaml(record)
        st.session_state["record_payload"] = record.model_dump(mode="json", by_alias=True)
        st.success("实验记录 Markdown 已生成。")
    except (RecordInputError, ValueError) as error:
        st.error(str(error))

render = _experiment_record_page

__all__ = ["render"]

