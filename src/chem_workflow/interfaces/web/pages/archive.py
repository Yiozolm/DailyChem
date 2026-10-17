"""Project export Streamlit page."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import streamlit as st

from chem_workflow.archive import RawFileGroup, StorageError, init_compound_archive
from chem_workflow.compounds.structure import StructureInputError
from chem_workflow.interfaces.web.components.common import _page_header, _state_text
from chem_workflow.interfaces.web.components.support import (
    UploadedFileLike,
    optional_text,
    write_uploaded_file,
    zip_directory_to_bytes,
)


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
        include_ocr = st.checkbox(
            "保留 OCR 原图、原始响应和结构化草稿",
            value=bool(st.session_state.get("ocr_draft")),
            disabled=not bool(st.session_state.get("ocr_draft")),
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
                include_ocr=include_ocr,
            )

    with right:
        _show_export_result()

def _handle_project_export(
    *,
    compound_id: str,
    project_dir: str,
    overwrite: bool,
    source_choice: str,
    smiles: str,
    uploaded: object,
    include_record: bool,
    include_ocr: bool,
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
                include_ocr=include_ocr,
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
    include_ocr: bool,
) -> tuple[RawFileGroup, ...]:
    groups: list[RawFileGroup] = []
    if include_record:
        record_markdown = st.session_state.get("record_markdown")
        if isinstance(record_markdown, str) and record_markdown:
            record_path = tmp_dir / f"{compound_id.strip() or 'compound'}_experiment_record.md"
            record_path.write_text(record_markdown + "\n", encoding="utf-8")
            groups.append(RawFileGroup("record", Path("records"), (record_path,)))
        record_yaml = st.session_state.get("record_yaml")
        if isinstance(record_yaml, str) and record_yaml:
            yaml_path = tmp_dir / f"{compound_id.strip() or 'compound'}_experiment_record.yaml"
            yaml_path.write_text(record_yaml, encoding="utf-8")
            groups.append(RawFileGroup("record-yaml", Path("records"), (yaml_path,)))
    if include_ocr:
        image_paths: list[Path] = []
        image_items = st.session_state.get("ocr_images")
        if isinstance(image_items, list):
            for index, item in enumerate(image_items, start=1):
                if not isinstance(item, dict) or not isinstance(item.get("data"), bytes):
                    continue
                name = Path(str(item.get("name") or f"page_{index}.jpg")).name
                image_path = tmp_dir / f"ocr_{index:02d}_{name}"
                image_path.write_bytes(item["data"])
                image_paths.append(image_path)
        if image_paths:
            groups.append(RawFileGroup("ocr-images", Path("ocr/images"), tuple(image_paths)))

        raw_response = st.session_state.get("ocr_raw_response")
        if isinstance(raw_response, dict):
            raw_path = tmp_dir / "raw_ocr.json"
            raw_path.write_text(
                json.dumps(raw_response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            groups.append(RawFileGroup("ocr-raw", Path("ocr"), (raw_path,)))
        draft = st.session_state.get("ocr_draft")
        if isinstance(draft, dict):
            draft_path = tmp_dir / "structured_draft.json"
            draft_path.write_text(
                json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            groups.append(RawFileGroup("ocr-draft", Path("ocr"), (draft_path,)))
    return tuple(groups)

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

render = _project_export_page

__all__ = ["render"]

