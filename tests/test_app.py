"""Phase 7 Streamlit app smoke tests."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def test_streamlit_app_renders_compound_setup() -> None:
    app = AppTest.from_file(APP_PATH)

    app.run(timeout=5)

    assert not app.exception
    assert "Compound Setup" in [title.value for title in app.title]
    assert "解析结构" in [button.label for button in app.button]


def test_streamlit_app_parses_default_smiles() -> None:
    app = AppTest.from_file(APP_PATH)
    app.run(timeout=5)

    app.button[0].click().run(timeout=5)

    assert not app.exception
    assert "结构解析完成。" in [message.value for message in app.success]
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Formula"] == "C9H10O2"
    assert metrics["MW"] == "150.177"
    assert metrics["Heavy atoms"] == "11"


def _select_workflow(app, page: str):  # noqa: ANN001
    """Select a page on the sidebar 'Workflow' radio regardless of its positional index."""
    workflow = next(r for r in app.radio if r.label == "Workflow")
    return workflow.set_value(page)


def _radio_by_label(app, label: str):  # noqa: ANN001
    return next(r for r in app.radio if r.label == label)


def test_streamlit_app_generates_assignment_draft() -> None:
    app = AppTest.from_file(APP_PATH)
    app.run(timeout=5)

    _select_workflow(app, "6 · NMR Assignment").run(timeout=10)
    _radio_by_label(app, "peak list 输入方式").set_value("粘贴文本").run(timeout=10)
    app.button[0].click().run(timeout=15)

    assert not app.exception
    assert "assignment 草稿已生成；请人工确认后再使用。" in [
        message.value for message in app.success
    ]
    assert "Editable review table" in [subheader.value for subheader in app.subheader]


def test_streamlit_app_assignment_13c() -> None:
    app = AppTest.from_file(APP_PATH)
    app.run(timeout=5)

    _select_workflow(app, "6 · NMR Assignment").run(timeout=10)
    app.radio(key="assignment_nucleus").set_value("13C").run(timeout=10)
    _radio_by_label(app, "peak list 输入方式").set_value("粘贴文本").run(timeout=10)
    app.button[0].click().run(timeout=15)

    assert not app.exception
    assert any("assignment 草稿已生成" in m.value for m in app.success)


def test_streamlit_app_generates_hrms_text() -> None:
    app = AppTest.from_file(APP_PATH)
    app.run(timeout=5)

    _select_workflow(app, "3 · MS / IR / UV").run(timeout=10)
    # Default HRMS section: from-structure mode, ethyl benzoate, [M+H]+ default adduct.
    app.button[0].click().run(timeout=10)

    assert not app.exception
    assert "HRMS 文本已生成。" in [message.value for message in app.success]
    codes = " ".join(code.value for code in app.code)
    assert "HRMS (ESI)" in codes


def test_streamlit_app_history_search(tmp_path) -> None:  # noqa: ANN001
    db_path = str(tmp_path / "history.sqlite")
    app = AppTest.from_file(APP_PATH)
    app.run(timeout=5)

    _select_workflow(app, "7 · History Search").run(timeout=10)
    # Point the page at a temp DB and add a compound.
    app.text_input(key="history_db_path").set_value(db_path).run(timeout=10)
    app.text_input(key="history_add_smiles").set_value("CCOC(=O)c1ccccc1").run(timeout=10)
    add_button = next(b for b in app.button if b.label == "加入历史库")
    add_button.click().run(timeout=10)

    assert not app.exception
    assert any("已写入" in message.value for message in app.success)


def test_streamlit_app_literature_tab(tmp_path) -> None:  # noqa: ANN001
    db_path = str(tmp_path / "history.sqlite")
    app = AppTest.from_file(APP_PATH)
    app.run(timeout=5)

    _select_workflow(app, "7 · History Search").run(timeout=10)
    app.text_input(key="history_db_path").set_value(db_path).run(timeout=10)
    app.text_input(key="lit_doi").set_value("10.1/x").run(timeout=10)
    app.text_input(key="lit_smiles").set_value("CCOC(=O)c1ccccc1").run(timeout=10)
    add_button = next(b for b in app.button if b.label == "加入文献库")
    add_button.click().run(timeout=10)

    assert not app.exception
    assert any("已写入文献" in m.value for m in app.success)
