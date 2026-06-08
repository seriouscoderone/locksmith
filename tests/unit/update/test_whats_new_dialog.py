"""Tests for WhatsNewDialog.

The interesting logic is the markdown renderer (``render_markdown``)
which is tested in isolation — no QApplication needed for it. Dialog
construction is smoke-tested under the offscreen Qt platform plugin
to catch import / init failures.
"""
from __future__ import annotations

import os
import sys

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from locksmith.ui.dialogs.whats_new import WhatsNewDialog, render_markdown


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


# ---- render_markdown unit tests (no Qt needed) -----------------------


def test_render_markdown_empty_returns_empty():
    assert render_markdown("") == ""
    assert render_markdown(None) == ""  # type: ignore[arg-type]


def test_render_markdown_paragraph_becomes_p_tag():
    out = render_markdown("Hello world")
    assert "<p>" in out
    assert "Hello world" in out
    assert "</p>" in out


def test_render_markdown_bold_wraps_in_b_tag():
    out = render_markdown("This is **bold** text.")
    assert "<b>bold</b>" in out


def test_render_markdown_italic_wraps_in_i_tag():
    out = render_markdown("This is _italic_ text.")
    assert "<i>italic</i>" in out


def test_render_markdown_inline_code_wraps_in_code_tag():
    out = render_markdown("Use `make build` to compile.")
    assert "<code>make build</code>" in out


def test_render_markdown_dash_bullets_become_ul_li():
    md = "- alpha\n- beta\n- gamma"
    out = render_markdown(md)
    assert out.count("<ul>") == 1
    assert out.count("</ul>") == 1
    assert "<li>alpha</li>" in out
    assert "<li>beta</li>" in out
    assert "<li>gamma</li>" in out


def test_render_markdown_star_bullets_also_work():
    md = "* one\n* two"
    out = render_markdown(md)
    assert "<li>one</li>" in out
    assert "<li>two</li>" in out


def test_render_markdown_headings_emit_h_tags():
    out = render_markdown("# Title\n## Subtitle\n### Section")
    assert "<h2>Title</h2>" in out
    assert "<h3>Subtitle</h3>" in out
    assert "<h4>Section</h4>" in out


def test_render_markdown_closes_list_before_paragraph():
    """A bare paragraph after a list must close the <ul> first."""
    md = "- alpha\n- beta\n\nA paragraph."
    out = render_markdown(md)
    # </ul> must appear before the next <p>
    assert out.index("</ul>") < out.index("<p>A paragraph.</p>")


def test_render_markdown_escapes_html_in_plain_text():
    out = render_markdown("Use <script>alert(1)</script> carefully")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_render_markdown_escapes_html_inside_bullets():
    out = render_markdown("- Foo & <b>bar</b>")
    # The <b> is literal text, not bold markdown
    assert "&lt;b&gt;bar&lt;/b&gt;" in out
    assert "&amp;" in out


# ---- Dialog construction smoke tests --------------------------------


def _all_label_texts(dialog: WhatsNewDialog) -> list[str]:
    return [w.text() for w in dialog.findChildren(QLabel)]


def test_dialog_constructs_with_simple_notes():
    dlg = WhatsNewDialog(version="2.0.0", release_notes_md="A paragraph.")
    assert dlg is not None
    assert dlg.objectName() == "whatsNewDialog"


def test_dialog_headline_includes_version():
    dlg = WhatsNewDialog(version="2.0.0", release_notes_md="x")
    assert dlg.headline_label.text() == "What's new in v2.0.0"


def test_dialog_version_label_text():
    dlg = WhatsNewDialog(version="2.1.0", release_notes_md="x")
    assert "2.1.0" in dlg.version_label.text()


def test_dialog_notes_label_renders_markdown_to_richtext():
    dlg = WhatsNewDialog(
        version="2.0.0",
        release_notes_md="**Important** change",
    )
    # The label was passed the HTML output of render_markdown
    assert "<b>Important</b>" in dlg.notes_label.text()


def test_dialog_has_single_got_it_button():
    dlg = WhatsNewDialog(version="2.0.0", release_notes_md="x")
    assert dlg.got_it_button.text() == "Got it"
    assert dlg.got_it_button.objectName() == "whatsNewDialog.gotItButton"


def test_dialog_got_it_button_accepts_dialog():
    dlg = WhatsNewDialog(version="2.0.0", release_notes_md="x")
    fired = []
    dlg.accepted.connect(lambda: fired.append(True))
    dlg.got_it_button.click()
    assert fired == [True]
