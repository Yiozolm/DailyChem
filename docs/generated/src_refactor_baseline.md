# `src` 重构基线（2026-08-31）

本文件记录 `codex/src-functional-refactor` 开始实施前的行为和公共入口，供渐进迁移比对。

## Git 与质量基线

- 基线：`dev@908f1bb`
- pytest：`226 passed, 1 skipped`
- Ruff：通过
- Python 包顶层模块：21 个（含 `__init__.py`）
- 顶层 Python 代码：约 6,048 行
- 根目录 Streamlit `app.py`：约 1,470 行

## CLI 根命令

```text
chemwf
  version
  backup
  init-compound
  structure
  nmr
  records
  llm
  ms
  ir
  uv
  db
  lit
  config
```

重构期间以上命令名、分组、主要参数和退出码保持兼容。

## 关键 Python 公共入口

```text
chem_workflow.structure
  StructureInputError, parse_smiles, load_structure, mol_info, draw_structure

chem_workflow.nmr
  NMRInputError, NMRPeak, NMRSpectrum, normalize_multiplicity,
  parse_j_values, parse_shift_range, parse_mestrenova_multiplet_table, parse_shift_list

chem_workflow.nmr_formatter
  NMRFormatError, NMRFormatOptions, format_nmr_spectrum

chem_workflow.assignment
  AssignmentError, AssignmentRule, DetectedFeature, AssignmentCandidate,
  PeakAssignment, AssignmentWarning, AssignmentDraft, load_assignment_rules,
  detect_proton_features, detect_carbon_features, assign_1h_nmr, assign_nmr,
  render_assignment_draft, assignment_rows_for_review

chem_workflow.records
  RecordInputError, Material, ReactionInfo, YieldInfo, Characterization,
  ReactionRecord, load_reaction_record, render_experiment_record, write_experiment_record

chem_workflow.storage
  StorageError, RawFileGroup, CompoundArchiveResult, CompoundMetadata,
  init_compound_archive, backup_compound_archive

chem_workflow.database
  DatabaseError, CompoundRecord, LiteratureRecord, connect, upsert_compound,
  get_compound, find_by_smiles, all_compounds, delete_compound, make_record,
  make_literature_record, upsert_literature, all_literature,
  get_literature_by_doi, delete_literature, record_from_metadata, scan_archive

chem_workflow.search
  HasSmiles, SearchError, SearchHit, substructure_search, similarity_search

chem_workflow.llm / chem_workflow.llm_models
  当前 workflow、schema、settings，以及计划弃用的 OpenAIResponsesClient、
  LLMClientProtocol 和手工 API orchestration
```

兼容入口用于迁移窗口；项目内部代码应逐阶段切换到新的 canonical 功能包。
