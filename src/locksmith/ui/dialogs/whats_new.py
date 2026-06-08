"""'What's New' major-version modal (Phase 5 §8.3 / Task 10).

Shown after a major-version install + relaunch, to explain what changed.
Tone is factual and anti-hype — this is a security-critical app, not
a consumer surface that earns attention with confetti.

Constraints from spec §8.3:
- Native Qt only (NO QWebEngineView / embedded browser).
- Single "Got it" button — no nag, no nested CTAs, no "share" buttons.
- Release notes consumed as Markdown text but rendered via QLabel's
  native lightweight Markdown → HTML conversion so we don't drag in a
  Markdown library or a JavaScript runtime.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from keri import help

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog

logger = help.ogler.getLogger(__name__)


def render_markdown(text: str) -> str:
    """Convert a small subset of Markdown to HTML for QLabel.

    Pure-Python conversion — kept here (not in a shared util) because
    it is dialog-scoped and intentionally narrow: lists, bold, italics,
    inline code, paragraphs. Anything fancier should be in the release
    notes URL the user opens externally, not in this modal.

    The function is the unit-tested seam — tests exercise it without
    needing a QApplication.
    """
    if not text:
        return ""

    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    in_list = False

    def _inline(s: str) -> str:
        # bold **x**
        result: list[str] = []
        i = 0
        while i < len(s):
            if s[i:i + 2] == "**":
                end = s.find("**", i + 2)
                if end != -1:
                    result.append("<b>")
                    result.append(_escape(s[i + 2:end]))
                    result.append("</b>")
                    i = end + 2
                    continue
            if s[i] == "`":
                end = s.find("`", i + 1)
                if end != -1:
                    result.append("<code>")
                    result.append(_escape(s[i + 1:end]))
                    result.append("</code>")
                    i = end + 1
                    continue
            if s[i] == "_":
                end = s.find("_", i + 1)
                if end != -1:
                    result.append("<i>")
                    result.append(_escape(s[i + 1:end]))
                    result.append("</i>")
                    i = end + 1
                    continue
            result.append(_escape(s[i]))
            i += 1
        return "".join(result)

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("- ") or line.startswith("* "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(line[2:])}</li>")
        elif not line:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append("")
        elif line.startswith("### "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h4>{_inline(line[4:])}</h4>")
        elif line.startswith("## "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h3>{_inline(line[3:])}</h3>")
        elif line.startswith("# "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h2>{_inline(line[2:])}</h2>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{_inline(line)}</p>")

    if in_list:
        out.append("</ul>")

    return "\n".join(out)


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )


class WhatsNewDialog(LocksmithDialog):
    """Single-CTA modal explaining what changed in a major release.

    Args:
        version: Semver string of the running release (e.g. "2.0.0").
        release_notes_md: Markdown body to render. Caller supplies
            already-fetched text — this dialog does no network I/O.
        parent: Parent widget (typically the main window).
    """

    def __init__(
        self,
        *,
        version: str,
        release_notes_md: str,
        parent: QWidget | None = None,
    ) -> None:
        self._version = version
        self._release_notes_md = release_notes_md
        content = self._build_content(version, release_notes_md)
        buttons = self._build_buttons()
        super().__init__(
            parent=parent,
            title="What's New",
            content=content,
            buttons=buttons,
            show_overlay=True,
        )
        self.setObjectName("whatsNewDialog")

    # ---- layout ---------------------------------------------------------

    def _build_content(self, version: str, notes_md: str) -> QWidget:
        wrap = QWidget()
        wrap.setMinimumWidth(560)
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(12)

        self.headline_label = QLabel(f"What's new in v{version}")
        self.headline_label.setObjectName("whatsNewDialog.headline")
        self.headline_label.setStyleSheet(
            f"color: {colors.TEXT_DARK}; font-size: 20px; font-weight: 700;"
        )
        layout.addWidget(self.headline_label)

        self.version_label = QLabel(f"Version {version}")
        self.version_label.setObjectName("whatsNewDialog.version")
        self.version_label.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 12px;"
        )
        layout.addWidget(self.version_label)

        self.notes_label = QLabel(render_markdown(notes_md))
        self.notes_label.setObjectName("whatsNewDialog.notes")
        self.notes_label.setWordWrap(True)
        self.notes_label.setTextFormat(Qt.TextFormat.RichText)
        self.notes_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.notes_label.setStyleSheet(
            f"color: {colors.TEXT_PRIMARY}; font-size: 13px; padding-top: 6px;"
        )
        layout.addWidget(self.notes_label)
        return wrap

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addStretch(1)

        self.got_it_button = QPushButton("Got it")
        self.got_it_button.setObjectName("whatsNewDialog.gotItButton")
        self.got_it_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.got_it_button.setDefault(True)
        self.got_it_button.setStyleSheet(f"""
            QPushButton {{
                padding: 10px 30px;
                background-color: {colors.PRIMARY};
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {colors.PRIMARY_HOVER}; }}
            QPushButton:pressed {{ background-color: {colors.PRIMARY_PRESSED}; }}
        """)
        self.got_it_button.clicked.connect(self.accept)
        row.addWidget(self.got_it_button)
        return row
