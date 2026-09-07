# Expected Outputs（黄金输出）

本目录存放用 `examples/raw/` 下样例输入跑出的**固定参考输出**，由 `tests/test_expected_outputs.py`
做回归锚点：CLI / 模块输出一旦与这里不一致，测试即失败。

> 注：当前样例均为**合成 / 脱敏样例**。项目无法获得脱敏的真实科研数据，
> 故 Phase 0 计划中的「3 个真实完整化合物样例」「真实 13C peak list」用合成样例替代。

| 黄金文件 | 来源输入 | 生成方式 |
|---|---|---|
| `nmr_report_1H.txt` | `raw/nmr_multiplet_table_clean_example.tsv` | `chemwf nmr format ... --frequency 400 --solvent CDCl3` |
| `hrms_report.txt` | SMILES `CCOC(=O)c1ccccc1` | `chemwf ms hrms --smiles ... --adduct "[M+Na]+" --found 173.0570` |
| `ir_report.txt` | `raw/ir_peaks_example.txt` | `chemwf ir format ...` |
| `uv_report.txt` | `raw/uv_peaks_example.txt` | `chemwf uv format ... --solvent MeOH` |
| `experiment_record_en.md` | `raw/experiment_record_example.yaml` | `chemwf records generate ... --language en` |
| `experiment_record_zh.md` | `raw/experiment_record_example.yaml` | `chemwf records generate ... --language zh` |

如果是有意改动输出格式，请同步用上述命令重新生成本目录文件，再提交。
