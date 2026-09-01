"""Local history and literature search Streamlit page."""

from __future__ import annotations

from contextlib import closing

import streamlit as st

from chem_workflow.history import (
    DatabaseError,
    all_compounds,
    all_literature,
    connect,
    make_literature_record,
    make_record,
    scan_archive,
    upsert_compound,
    upsert_literature,
)
from chem_workflow.history.search import SearchError, similarity_search, substructure_search
from chem_workflow.interfaces.web.components.common import _page_header, _state_text
from chem_workflow.interfaces.web.components.context import CONFIG
from chem_workflow.interfaces.web.components.support import optional_text


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

    ingest_tab, search_tab, lit_tab = st.tabs(["入库", "检索", "文献"])
    with ingest_tab:
        _history_ingest_section(db_path)
    with search_tab:
        _history_search_section(db_path)
    with lit_tab:
        _history_literature_section(db_path)

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

def _history_literature_section(db_path: str) -> None:
    st.markdown("**添加文献参考**")
    col_a, col_b = st.columns(2)
    with col_a:
        doi = st.text_input("DOI", value="", key="lit_doi", placeholder="10.1021/...")
        lit_smiles = st.text_input("SMILES", value=_state_text("compound_smiles"), key="lit_smiles")
        title = st.text_input("Title", value="", key="lit_title")
    with col_b:
        lit_h1 = st.text_area("1H NMR", value="", height=80, key="lit_h1")
        lit_c13 = st.text_area("13C NMR", value="", height=80, key="lit_c13")
    if st.button("加入文献库", type="primary", width="stretch", key="lit_add"):
        if optional_text(doi) is None or optional_text(lit_smiles) is None:
            st.warning("请至少填写 DOI 和 SMILES。")
        else:
            _handle_literature_add(
                db_path, doi=doi, smiles=lit_smiles, title=title, h1=lit_h1, c13=lit_c13
            )

    st.divider()
    st.markdown("**按相似度对照文献**")
    query = st.text_input(
        "查询 SMILES", value=_state_text("compound_smiles"), key="lit_compare_smiles"
    )
    threshold = st.slider(
        "相似度阈值", min_value=0.0, max_value=1.0, value=0.4, step=0.05, key="lit_threshold"
    )
    if st.button("对照文献", width="stretch", key="lit_compare"):
        _handle_literature_compare(db_path, query=query, threshold=threshold)

    rows = st.session_state.get("lit_compare_rows")
    if isinstance(rows, list):
        if rows:
            st.dataframe(rows, width="stretch")
        else:
            st.info("没有相似的文献。")

def _handle_literature_add(
    db_path: str, *, doi: str, smiles: str, title: str, h1: str, c13: str
) -> None:
    try:
        record = make_literature_record(
            doi=doi,
            smiles=smiles,
            title=optional_text(title),
            nmr_1h=optional_text(h1),
            nmr_13c=optional_text(c13),
        )
        with closing(connect(db_path)) as conn:
            upsert_literature(conn, record)
        st.success(f"已写入文献 {record.doi}。")
    except DatabaseError as error:
        st.error(str(error))

def _handle_literature_compare(db_path: str, *, query: str, threshold: float) -> None:
    if optional_text(query) is None:
        st.warning("请提供查询 SMILES。")
        return
    try:
        with closing(connect(db_path)) as conn:
            records = all_literature(conn)
        hits = similarity_search(records, query, threshold=threshold)
        st.session_state["lit_compare_rows"] = [
            {
                "doi": hit.record.doi,
                "title": hit.record.title or "",
                "score": hit.score,
                "1H": hit.record.nmr_1h or "",
                "13C": hit.record.nmr_13c or "",
                "smiles": hit.record.smiles,
            }
            for hit in hits
        ]
        st.success(f"找到 {len(hits)} 篇相似文献。")
    except (DatabaseError, SearchError) as error:
        st.error(str(error))

render = _history_search_page

__all__ = ["render"]

