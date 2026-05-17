"""Phase 7 Streamlit app smoke tests."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_streamlit_app_renders_compound_setup() -> None:
    app = AppTest.from_file("app.py")

    app.run(timeout=5)

    assert not app.exception
    assert "Compound Setup" in [title.value for title in app.title]
    assert "解析结构" in [button.label for button in app.button]


def test_streamlit_app_parses_default_smiles() -> None:
    app = AppTest.from_file("app.py")
    app.run(timeout=5)

    app.button[0].click().run(timeout=5)

    assert not app.exception
    assert "结构解析完成。" in [message.value for message in app.success]
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Formula"] == "C9H10O2"
    assert metrics["MW"] == "150.177"
    assert metrics["Heavy atoms"] == "11"
