# -*- encoding: utf-8 -*-
"""The read-back that stands between "Attest" and a permanent public credential.

Until this existed, `attest()` ran straight from a page click to `vault.extend`:
no read-back, no acknowledgement, and three schema-required attributes the
actuary never saw. The sibling CUO flow had already established that an
irreversible mint gets a ceremony; this page was the one without it.

**Why a drawer and not the CUO's modal.** ux-patterns.md:66 -- "Modals are for
confirmation actions and small focused forms only. Use a drawer for anything
requiring a long form or rich detail view." This read-back is a rich detail view:
twelve rows, two 44-character digests and a prose thesis. The CUO's modal is
already the cautionary tale -- its own history records the caution clipping 37px
below the fold with the finality sentence cut mid-word, at six rows in 560px.
A drawer also keeps the page visible behind it, which is the point: the actuary
is cross-referencing what they observed against what they parsed.

Owner decision, 2026-08-09.

Geometry is the suite's (ux-patterns.md:30-47): slide from the right, 300ms
ease-out in and 200ms ease-in out, `bg-black/40` backdrop, `md` 600px width
(the stated default), sticky header, scrollable body at 24px padding, sticky
footer that never clips its actions.
"""
from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve, QEvent, QPropertyAnimation, Qt, Signal,
)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from locksmith.ui import colors
from locksmith.ui.styles import get_monospace_font_family
from locksmith.ui.toolkit.widgets import LocksmithButton
from locksmith.ui.toolkit.widgets.buttons import LocksmithInvertedButton

#: ux-patterns.md:41 "Width: `sm: 400px`, `md: 600px`, `lg: 50vw`. Default is
#: `md` (600px)." `lg` is reserved there for forms of 4+ sections; this is a
#: read-back, not a form.
DRAWER_WIDTH = 600
#: ux-patterns.md:31 "Semi-transparent dark overlay (`bg-black/40`)" -- 40% of
#: 255. Note this is LIGHTER than the modal's `bg-black/50`, deliberately: a
#: drawer is meant to keep the page behind it legible for cross-reference.
BACKDROP_ALPHA = 102
_SLIDE_IN_MS = 300
_SLIDE_OUT_MS = 200

TITLE = "Review this attestation before signing"
INTRO = ("Read every value. This is exactly what gets signed, and once you "
         "attest it is public and permanent.")
MANDATE_SECTION = "The mandate you are answering"
PROGRAM_SECTION = "The rate program you are attesting"
CAUTION_HEAD = "Attesting is final, and public."
CAUTION_BODY = (
    "This attestation can never be edited, and it is readable by anyone who "
    "asks. It is permanently edge-linked to the mandate above, so it answers "
    "that mandate and no other. To correct an attestation, publish a new one.")
ACK = "I have read this attestation and intend it to be published."
CONFIRM = "Attest and publish"
BACK = "Keep reviewing"
IN_FLIGHT = "Attesting…"


def _mono_css() -> str:
    """Quoted, with a real fallback -- see the page's own `_mono_css`. The module
    default is the literal "monospace", which is not a registered family on
    macOS and falls back SILENTLY to the proportional system face."""
    return f'"{get_monospace_font_family()}", Menlo, monospace'


def _row(label: str, value: str, mono: bool = False) -> QWidget:
    """One label/value pair, in the read-back vocabulary the CUO flow settled on:
    a 12px uppercase tracked data label over a 14px value, per
    design-system.md:261-262."""
    row = QWidget()
    layout = QVBoxLayout(row)
    layout.setContentsMargins(0, 4, 0, 4)
    layout.setSpacing(2)

    name = QLabel(label)
    name.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
    font = name.font()
    font.setWeight(QFont.Weight.Medium)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 105)
    font.setCapitalization(QFont.Capitalization.AllUppercase)
    name.setFont(font)
    layout.addWidget(name)

    shown = QLabel(value or "—")
    shown.setWordWrap(True)
    # PlainText unconditionally: the thesis is free prose and the likeliest field
    # to contain '<' or '&', and a read-back that renders its own content as
    # markup is showing something other than what will be signed.
    shown.setTextFormat(Qt.TextFormat.PlainText)
    shown.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    face = f" font-family: {_mono_css()};" if mono else ""
    shown.setStyleSheet(f"color: {colors.TEXT_PRIMARY}; font-size: 14px;{face}")
    layout.addWidget(shown)
    return row


def _data_label(text: str) -> QLabel:
    """Just the label half of a row, for a value rendered by something other than
    `_row` -- the thesis, which gets a quote rail rather than a plain value."""
    label = QLabel(text)
    label.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
    font = label.font()
    font.setWeight(QFont.Weight.Medium)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 105)
    font.setCapitalization(QFont.Capitalization.AllUppercase)
    label.setFont(font)
    return label


def _section(title: str) -> QLabel:
    label = QLabel(title)
    label.setStyleSheet(
        f"color: {colors.TEXT_SECONDARY}; font-size: 16px; font-weight: 600;")
    return label


class AttestReviewDrawer(QWidget):
    """Slides in over the actuary page carrying the whole attestation."""

    confirm = Signal()
    cancelled = Signal()

    def __init__(self, mandate_said: str, mandate: dict, manifest_said: str,
                 workbook_digest: str, attributes: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("attestDrawer")
        self._confirmed = False
        self._finished = False
        self._open = False

        self._backdrop = QFrame(parent)
        self._backdrop.setObjectName("attestDrawer.backdrop")
        self._backdrop.setStyleSheet(
            f"background-color: rgba(0, 0, 0, {BACKDROP_ALPHA});")
        self._backdrop.hide()
        self._backdrop.installEventFilter(self)

        self.setStyleSheet(
            f"QWidget#attestDrawer {{ background-color: {colors.BACKGROUND_CONTENT};"
            f" border-left: 1px solid {colors.BORDER_TABLE}; }}")

        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        # -- sticky header ----------------------------------------------------
        header = QWidget()
        header.setStyleSheet(
            f"background-color: {colors.BACKGROUND_CONTENT};"
            f" border-bottom: 1px solid {colors.BORDER_TABLE};")
        head_layout = QVBoxLayout(header)
        head_layout.setContentsMargins(24, 20, 24, 16)
        head_layout.setSpacing(8)
        title = QLabel(TITLE)
        title.setObjectName("attestDrawer.title")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 600; color: {colors.TEXT_PRIMARY};")
        head_layout.addWidget(title)
        intro = QLabel(INTRO)
        intro.setObjectName("attestDrawer.intro")
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {colors.TEXT_PRIMARY}; font-size: 14px;")
        head_layout.addWidget(intro)
        shell.addWidget(header)

        # -- scrollable body --------------------------------------------------
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 24, 24, 24)
        body_layout.setSpacing(16)

        body_layout.addWidget(_section(MANDATE_SECTION))
        body_layout.addWidget(_row("Declared by", mandate.get("issuer", ""), mono=True))
        body_layout.addWidget(_row("Line of business", mandate.get("line_of_business", "")))
        body_layout.addWidget(_row("Jurisdiction", mandate.get("jurisdiction", ""), mono=True))
        body_layout.addWidget(_row(
            "Coverages", ", ".join(mandate.get("coverages", []) or []), mono=True))
        opens = mandate.get("window_opens", "")
        closes = mandate.get("window_closes", "")
        body_layout.addWidget(_row(
            "In force",
            f"{opens} through {closes}, inclusive" if opens or closes else "",
            mono=True))
        body_layout.addWidget(_row("Mandate", mandate_said, mono=True))

        thesis = QLabel(str(mandate.get("thesis") or "—"))
        thesis.setObjectName("attestDrawer.thesis")
        thesis.setWordWrap(True)
        thesis.setTextFormat(Qt.TextFormat.PlainText)
        # A quote rail, not a filled box: ux-patterns.md:241 forbids rendering
        # read-only data as a disabled input, and a filled 4px-radius rect IS the
        # design system's input token. BORDER_DARK because #D0D5DD measures
        # ~1.4:1 here, under the 3:1 graphical-object floor.
        thesis.setStyleSheet(
            f"color: {colors.TEXT_PRIMARY}; font-size: 16px;"
            f" padding: 2px 0 2px 12px;"
            f" border-left: 3px solid {colors.BORDER_DARK};")
        # The LABEL only: `_row` placeholders an empty value with an em dash, so
        # passing "" here printed "THESIS / —" directly above the thesis itself.
        body_layout.addWidget(_data_label("Thesis"))
        body_layout.addWidget(thesis)

        body_layout.addSpacing(8)
        body_layout.addWidget(_section(PROGRAM_SECTION))
        body_layout.addWidget(_row("Manifest SAID", manifest_said, mono=True))
        body_layout.addWidget(_row("Workbook digest", workbook_digest, mono=True))
        # The three the app asserts on the actuary's behalf. They are
        # schema-required and were committed without ever being shown -- every
        # attestation is permanently `Sandbox` / `1.0`, and `filing_date` claims
        # today rather than the date of the parse.
        for key, label in (("version", "Version"),
                           ("filing_date", "Filing date"),
                           ("action", "Action")):
            body_layout.addWidget(_row(label, str(attributes.get(key, "")),
                                       mono=True))
        body_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("attestDrawer.body")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setWidget(body)
        shell.addWidget(scroll, 1)

        # -- sticky footer ----------------------------------------------------
        footer = QWidget()
        footer.setStyleSheet(
            f"background-color: {colors.BACKGROUND_CONTENT};"
            f" border-top: 1px solid {colors.BORDER_TABLE};")
        foot = QVBoxLayout(footer)
        foot.setContentsMargins(24, 16, 24, 16)
        foot.setSpacing(12)

        caution = QFrame()
        caution.setObjectName("attestDrawer.caution")
        caution.setStyleSheet(
            f"QFrame#attestDrawer\\.caution {{"
            f" background: {colors.BACKGROUND_WARNING};"
            f" border-left: 4px solid {colors.WARNING_BORDER};"
            f" border-radius: 4px; }}")
        caution_layout = QVBoxLayout(caution)
        caution_layout.setContentsMargins(12, 10, 12, 10)
        caution_layout.setSpacing(4)
        head = QLabel(CAUTION_HEAD)
        head.setObjectName("attestDrawer.cautionHead")
        head.setWordWrap(True)
        head.setStyleSheet(
            f"color: {colors.WARNING_TEXT}; font-size: 14px; font-weight: 600;"
            f" background: transparent; border: none; padding: 0;")
        caution_layout.addWidget(head)
        body_text = QLabel(CAUTION_BODY)
        body_text.setObjectName("attestDrawer.cautionBody")
        body_text.setWordWrap(True)
        body_text.setStyleSheet(
            f"color: {colors.WARNING_TEXT}; font-size: 12px;"
            f" background: transparent; border: none; padding: 0;")
        caution_layout.addWidget(body_text)
        # In the FOOTER, so it can never scroll away from the button it governs.
        # The sibling's caution sat in its scroll area and was measured clipped
        # 37px below the fold with the finality sentence cut mid-word.
        foot.addWidget(caution)

        self._ack = QCheckBox(ACK)
        self._ack.setObjectName("attestDrawer.ack")
        self._ack.setStyleSheet(
            f"QCheckBox {{ color: {colors.TEXT_PRIMARY}; font-size: 12px; }}")
        foot.addWidget(self._ack)

        self._back = LocksmithInvertedButton(BACK)
        self._back.setObjectName("attestDrawer.back")
        self._confirm_button = LocksmithButton(CONFIRM)
        self._confirm_button.setObjectName("attestDrawer.confirm")
        self._confirm_button.setEnabled(False)
        self._ack.toggled.connect(self._confirm_button.setEnabled)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(self._back)
        buttons.addStretch(1)
        buttons.addWidget(self._confirm_button)
        foot.addLayout(buttons)
        shell.addWidget(footer)

        self._back.clicked.connect(self.close_drawer)
        self._confirm_button.clicked.connect(self._on_confirm)

        # The irreversible button is neither default nor focused; opening focus
        # goes to the acknowledgement, the first interactive element
        # (ux-patterns.md:426).
        self._back.setDefault(True)
        self._back.setAutoDefault(True)
        self._confirm_button.setDefault(False)
        self._confirm_button.setAutoDefault(False)

        self._animation = QPropertyAnimation(self, b"geometry")

    # -- open / close ---------------------------------------------------------

    def open_drawer(self) -> None:
        host = self.parentWidget()
        if host is None:
            return
        rect = host.rect()
        width = min(DRAWER_WIDTH, rect.width())
        self._backdrop.setGeometry(rect)
        self._backdrop.show()
        self._backdrop.raise_()
        self.setGeometry(rect.width(), rect.y(), width, rect.height())
        self.show()
        self.raise_()
        self._animation.stop()
        self._animation.setDuration(_SLIDE_IN_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.setStartValue(self.geometry())
        self._animation.setEndValue(
            self.geometry().adjusted(-width, 0, -width, 0))
        self._animation.start()
        self._open = True
        self._ack.setFocus()

    def close_drawer(self) -> None:
        """Dismiss without attesting. Refused once signing has begun -- the
        issuance carries on regardless, and closing would remove the only surface
        that reports the outcome."""
        if self._confirmed and not self._finished:
            return
        if not self._open:
            return
        self._open = False
        # Slide OUT, 200ms ease-in (ux-patterns.md:30). `_SLIDE_OUT_MS` was
        # defined and never used -- the drawer animated in and then vanished, so
        # the exit read as a glitch rather than as the reverse of the entrance.
        # The backdrop goes at once: it is the thing making the page unusable,
        # and there is no reason to hold it for the length of the animation.
        self._backdrop.hide()
        self._animation.stop()
        self._animation.setDuration(_SLIDE_OUT_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.InCubic)
        self._animation.setStartValue(self.geometry())
        self._animation.setEndValue(
            self.geometry().adjusted(self.width(), 0, self.width(), 0))
        try:
            self._animation.finished.disconnect(self._after_close)
        except (RuntimeError, TypeError):
            pass
        self._animation.finished.connect(self._after_close)
        self._animation.start()

    def _after_close(self) -> None:
        """Hide and report, once the slide-out has finished."""
        try:
            self._animation.finished.disconnect(self._after_close)
        except (RuntimeError, TypeError):
            pass
        self.hide()
        self.cancelled.emit()

    def finish(self) -> None:
        """The outcome has arrived; release the guard and close.

        REQUIRED, not a convenience: `close_drawer` refuses while `_confirmed`,
        so without this the drawer would survive its own success -- which is
        exactly the bug the sibling read-back shipped with for one commit.
        """
        self._finished = True
        self.close_drawer()

    def fail(self, message: str) -> None:
        """Re-arm after a failed attestation so a retry is possible. The
        acknowledgement is not re-demanded: it was given for these exact values,
        and they have not changed."""
        self._confirmed = False
        self._confirm_button.setEnabled(self._ack.isChecked())
        self._confirm_button.setText(CONFIRM)
        self._back.setEnabled(True)

    def confirmed(self) -> bool:
        return self._confirmed

    # -- events ---------------------------------------------------------------

    def _on_confirm(self) -> None:
        self._confirmed = True
        self._confirm_button.setEnabled(False)
        self._confirm_button.setText(IN_FLIGHT)
        self._back.setEnabled(False)
        self.confirm.emit()

    def eventFilter(self, obj, event):
        """ux-patterns.md:31 -- clicking the backdrop closes the drawer. Safe
        here because closing is a cancel: nothing has been minted yet, and
        `close_drawer` refuses once it has."""
        if obj is self._backdrop and event.type() == QEvent.Type.MouseButtonRelease:
            self.close_drawer()
            return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        """ux-patterns.md:33 -- Escape always closes. `close_drawer` is what
        enforces the in-flight exception, so this needs no special case."""
        if event.key() == Qt.Key.Key_Escape:
            self.close_drawer()
            return
        super().keyPressEvent(event)
