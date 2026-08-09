# -*- encoding: utf-8 -*-
"""The read-back shown between filling the form and anchoring the credential.

`ux-patterns.md:439` makes a confirmation modal the platform's irreversibility
pattern, carrying "This cannot be undone" -- literally true here.

It renders the CANONICAL payload, never the raw field text, because the payload
builder rewrites input and the difference is exactly what a reader needs to see. It
holds no rules: whatever it is handed, it shows.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from locksmith.plugins.cuo import mandate_copy as copy
from locksmith.ui import colors
from locksmith.ui.toolkit.widgets.buttons import (
    LocksmithButton,
    LocksmithInvertedButton,
)
from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog

_ROWS = ("line_of_business", "jurisdiction", "coverages")

#: ux-patterns.md:82 "Max width: `sm: 400px`, `md: 560px`", and :674 builds its
#: worked modal at `md`.
_MODAL_WIDTH = 560
#: `LocksmithDialog._build_button_section` gives the footer container 16px side
#: margins (dialogs.py:452), so this is the width the button row can occupy.
_FOOTER_WIDTH = _MODAL_WIDTH - 32
#: ux-patterns.md:80 "Backdrop: Dark overlay (`bg-black/50`)" — 50% of 255.
_BACKDROP_ALPHA = 128


def _row(label: str, value: str) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    # 4px, not 3: design-system.md:140 sets the base unit at 4px and the scale
    # (:144-160) has no 3px step.
    layout.setContentsMargins(0, 4, 0, 4)
    name = QLabel(label)
    # design-system.md:261 "Data label | text-sm font-medium uppercase
    # tracking-wide text-gray-500 | 12px medium, uppercase". Label and value were
    # both 14px regular, so the read-back rendered as two columns of body text
    # rather than as label/value pairs.
    #
    # Two deliberate departures, both measured:
    # * the spec's own `text-gray-500` (#9CA3AF) scores 2.54:1 on this surface and
    #   FAILS WCAG AA, which ui-conventions.md:69 requires. TEXT_SECONDARY is the
    #   Locksmith token playing the "secondary text, labels" role and passes.
    # * colours come from `colors.*`, never from the suite's literal greys:
    #   `apply_theme_overrides` rewrites these constants per brand, so a pasted
    #   hex would silently stop tracking the brand.
    name.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
    label_font = name.font()
    label_font.setWeight(QFont.Weight.Medium)
    # `letter-spacing` is NOT a Qt Style Sheet property -- it is silently ignored
    # there. QFont is the only way to get the spec's tracking.
    label_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 105)
    label_font.setCapitalization(QFont.Capitalization.AllUppercase)
    name.setFont(label_font)
    name.setFixedWidth(150)
    shown = QLabel(value)
    shown.setWordWrap(True)
    # Defensive, not reactive: today's schema patterns for these fields exclude
    # '<' and '>', but this module owns no rules and must not depend on another
    # layer's patterns holding. Force plain text so a value can never render as
    # markup regardless of what upstream validation does or stops doing.
    shown.setTextFormat(Qt.TextFormat.PlainText)
    shown.setStyleSheet(f"color: {colors.TEXT_PRIMARY}; font-size: 14px;")
    layout.addWidget(name)
    layout.addWidget(shown, 1)
    return row


class MandateReviewDialog(LocksmithDialog):
    """Read back the canonical payload; confirm or go back."""

    confirm = Signal()

    def __init__(self, payload: dict, signer_name: str, parent=None):
        self._confirmed = False
        self._finished = False

        body = QWidget()
        outer = QVBoxLayout(body)
        # The base class's content area has NO top padding (dialogs.py:436
        # margins are 20,0,20,0), so the signer line sat 3px under the header
        # divider -- measured, divider bottom y=70, signer top y=70. 16px is the
        # suite's `gap-4`, which ux-patterns.md:296 sets between fields.
        outer.setContentsMargins(0, 16, 0, 0)
        outer.setSpacing(16)

        signer = QLabel(copy.REVIEW_SIGNER.format(cuo_name=signer_name))
        signer.setObjectName("mandateReviewDialog.signer")
        signer.setWordWrap(True)
        signer.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
        outer.addWidget(signer)

        summary = QWidget()
        summary.setObjectName("mandateReviewDialog.summary")
        rows = QVBoxLayout(summary)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(0)
        for field in _ROWS:
            value = payload.get(field)
            shown = ", ".join(value) if isinstance(value, list) else str(value or "")
            rows.addWidget(_row(copy.FIELD_LABEL[field], shown))
        # ISO on purpose -- see the module docstring.
        rows.addWidget(_row(copy.REVIEW_IN_FORCE_LABEL, (
            f"{payload.get('window_opens', '')} through "
            f"{payload.get('window_closes', '')}, inclusive")))
        outer.addWidget(summary)

        thesis_label = QLabel(copy.REVIEW_THESIS_LABEL)
        # design-system.md:260 "Section header | text-lg font-semibold
        # text-gray-700 | 16px semibold". At 13px/400 it was pixel-identical to
        # the signer line and the caution text, so nothing on screen said it was
        # a heading.
        thesis_label.setStyleSheet(
            f"color: {colors.TEXT_SECONDARY}; font-size: 16px; font-weight: 600;")
        outer.addWidget(thesis_label)
        thesis = QLabel(str(payload.get("thesis") or ""))
        thesis.setObjectName("mandateReviewDialog.thesis")
        thesis.setWordWrap(True)
        # CRITICAL: the thesis is free, unpatterned prose -- the one field most
        # likely to contain '<', '>' or '&'. Left at Qt's default AutoText, a
        # thesis that happens to look like markup renders AS markup: tags vanish
        # and the text restyles, so the CUO would sign a string they cannot see.
        # This dialog's entire reason for existing is showing what will be
        # signed, so this must be plain text, unconditionally.
        thesis.setTextFormat(Qt.TextFormat.PlainText)
        # A quote rail, NOT a filled box. The grey chip it replaces was the one
        # element on this screen that looked like a form field, on the one screen
        # in the product where nothing is editable -- and that is a rule, not a
        # preference: ux-patterns.md:241 "Read-only | Plain text (not a disabled
        # input) ... Never render as a greyed-out input" and :463, while a
        # 4px-radius filled rect IS the design system's input token
        # (design-system.md:196, :206).
        #
        # Two further things the fill cost, both visible in renders: with a
        # one-word thesis it banded a 520px grey slab around three characters, and
        # at three lines it became a peer of the amber caution below it, so the
        # CUO's own declaration read as a second alert. With the fill gone, the
        # caution is the ONLY filled block -- fill now means "stop and read".
        #
        # BORDER_DARK, not BORDER: measured on this surface, #D0D5DD is ~1.4:1 and
        # fails the 3:1 that ui-conventions.md:77 requires of a non-text graphical
        # object; #757575 is ~4.5:1. The rail is load-bearing -- it is the only
        # thing on screen saying "these exact bytes are what publishes" -- so it
        # has to be visible.
        thesis.setStyleSheet(
            f"color: {colors.TEXT_PRIMARY}; font-size: 16px;"
            f" padding: 2px 0 2px 12px;"
            f" border-left: 3px solid {colors.BORDER_DARK};")
        outer.addWidget(thesis)

        caution = QLabel(copy.REVIEW_CAUTION)
        caution.setObjectName("mandateReviewDialog.caution")
        caution.setWordWrap(True)
        # Was WARNING_TEXT on BACKGROUND_HIGHLIGHT: the SAME grey chip as the
        # thesis directly above it, differing only in text colour, so nothing
        # marked the one sentence that says "Signing is final." as a warning at
        # all. Measured 3.83:1 -- below the 4.5:1 that ui-conventions.md:69
        # requires at this size. The amber fill with a 4px left rule takes it to
        # 4.65:1 and reuses the vocabulary `LocksmithDialog._build_warning_banner`
        # already ships, so it reads as caution rather than as a validation error.
        #
        # The suite defines no token for "caution before an irreversible act":
        # its Error is scoped to validation failures and its Warning to pending
        # actions and deadlines. This is a judgment call, not a citation.
        caution.setStyleSheet(
            f"color: {colors.WARNING_TEXT}; background: {colors.BACKGROUND_WARNING};"
            f" border-left: 4px solid {colors.WARNING_BORDER};"
            f" border-radius: 4px; padding: 10px 12px; font-size: 12px;")

        self._back = LocksmithInvertedButton(copy.REVIEW_BACK)
        self._back.setObjectName("mandateReviewDialog.back")
        self._confirm_button = LocksmithButton(copy.REVIEW_CONFIRM)
        self._confirm_button.setObjectName("mandateReviewDialog.confirm")

        # ux-patterns.md:288-289 puts the secondary on the LEFT of the footer and
        # the primary on the RIGHT. The obvious `addStretch(1)` between them does
        # NOT achieve that: `_build_button_section` wraps whatever layout it is
        # given in `addStretch()` on BOTH sides (dialogs.py:453, 465), and those
        # outer stretches absorb the space, so the pair rendered centred and
        # TOUCHING -- measured, a 0px gap between "Keep editing" and the
        # irreversible "Sign mandate". Handing the base class a single expanding
        # widget instead lets the inner stretch do its job.
        footer = QWidget()
        footer.setSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Preferred)
        # An Expanding size policy is NOT enough on its own: the base class puts a
        # stretch on either side of whatever layout it is handed, and a widget
        # with no minimum simply gets its sizeHint and sits centred between them
        # -- measured, 138px of dead space on each side. A minimum width is what
        # actually pushes the two buttons to the footer's edges.
        footer.setMinimumWidth(_FOOTER_WIDTH)

        # The caution is PINNED here, not added to `outer`, because the body is
        # inside `LocksmithDialog`'s QScrollArea. Measured with a three-line
        # thesis: content 397px in a 360px viewport, and the caution's own bottom
        # 37px below the fold -- the finality sentence was cut off mid-word at "To
        # correct a mandate, declare a", behind a scrollbar. The one block that
        # carries irreversibility could scroll out of view on the screen whose
        # entire job is to make irreversibility land before the click. Three
        # independent UX reviews each found this first.
        #
        # Everything above it may scroll. This may not.
        footer_column = QVBoxLayout(footer)
        footer_column.setContentsMargins(0, 0, 0, 0)
        footer_column.setSpacing(16)
        footer_column.addWidget(caution)

        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 0, 0, 0)
        footer_row.addWidget(self._back)
        footer_row.addStretch(1)
        footer_row.addWidget(self._confirm_button)
        footer_column.addLayout(footer_row)

        buttons = QHBoxLayout()
        buttons.addWidget(footer)

        # No header X. A confirmation modal has exactly two answers and both are
        # buttons; a third, unlabelled way out of the last screen before an
        # irreversible act is not an affordance, it is an accident waiting for a
        # mis-aimed click. It is also the one exit `_on_confirm` cannot disable.
        # `show_overlay=True` is what makes this actually modal. Measured before:
        # `isModal() False`, `self.overlay None` -- the base class defaults
        # show_overlay False (dialogs.py:87) and only calls `setModal(True)` when
        # it is on, so the app's one irreversibility confirmation left the whole
        # window visible and clickable behind it. ux-patterns.md:80 requires a
        # backdrop; its "clicking backdrop closes modal (except destructive
        # confirmations)" carve-out is why nothing here dismisses on scrim click.
        super().__init__(parent=parent, title=copy.REVIEW_TITLE,
                         content=body, buttons=buttons,
                         show_close_button=False, show_overlay=True)
        self.setObjectName("mandateReviewDialog")

        # ux-patterns.md:82 "Max width: sm: 400px, md: 560px" and :674 builds its
        # worked modal at `md`. This dialog set no width at all and came out at
        # 368px on sizeHint -- narrower than either token, which cost real
        # legibility: measured, the caution wrapped to 6 lines (116px, 23% of the
        # dialog) and the in-force dates wrapped to two. At 560 the caution is
        # 84px and the dates fit one line.
        #
        # MINIMUM, not fixed: the base class's `dialogHeight` setter calls
        # `setFixedSize(current_width, ...)` (dialogs.py:606) the first time any
        # banner animates, so the width freezes itself on first `show_error`.
        self.setMinimumWidth(_MODAL_WIDTH)

        # The header divider paints a pure BLACK line. `setFrameShape(HLine)`
        # (dialogs.py) makes Qt draw a frame in the palette's WindowText ON TOP of
        # the #E8E8E8 the stylesheet asks for. Measured by pixel scan: rows 67/68/69
        # read #e8e8e8 / #000000 / #e8e8e8. At 19.99:1 it was the highest-contrast
        # element in a dialog whose caution text sat at 3.83:1.
        #
        # Fixed here rather than in the base class, which every dialog in the app
        # inherits. The base class is where this belongs -- see the backlog item.
        divider = self.findChild(QFrame, "header-divider")
        if divider is not None:
            divider.setFrameShape(QFrame.Shape.NoFrame)
            divider.setFixedHeight(1)

        # ux-patterns.md:80 specifies the backdrop as `bg-black/50` -- alpha 128 of
        # 255. The base class paints `rgba(0, 0, 0, 150)` (dialogs.py:479), which
        # is 59%, and the difference is visible: the owner's first reaction to the
        # scrim landing was that it looked too dark. Restyled here rather than in
        # the base class, which every dialog in the app inherits.
        if self.overlay is not None:
            self.overlay.setStyleSheet(
                f"background-color: rgba(0, 0, 0, {_BACKDROP_ALPHA});")

        # `close()`, not `reject()`. `LocksmithDialog` now releases its class-level
        # `_current_dialog` on every exit path, so this is no longer load-bearing --
        # it stays because `close()` is the one exit that runs `closeEvent`, and any
        # future `closeEvent` cleanup on this dialog should run when the CUO backs
        # out. See `LocksmithDialog._release_current_dialog` for what went wrong
        # when `closeEvent` was the only place the pointer was cleared.
        self._back.clicked.connect(self.close)
        self._confirm_button.clicked.connect(self._on_confirm)

        # A confirmation modal exists to ADD friction, so the irreversible button
        # must be neither the default nor focused.
        # `LocksmithDialog._build_button_section` makes the LAST `LocksmithButton`
        # in the row the default and focuses it, and the primary is last -- which
        # put a single Return keystroke between an unread mandate and a permanent,
        # publicly-readable credential. Measured: one `Key_Return` on the freshly
        # opened dialog anchored.
        self._back.setDefault(True)
        self._back.setAutoDefault(True)
        self._confirm_button.setDefault(False)
        self._confirm_button.setAutoDefault(False)
        self._back.setFocus()

    def finish(self) -> None:
        """The outcome has arrived; release the in-flight guard and close.

        REQUIRED, not a convenience: `reject()` refuses while `_confirmed`, and
        `QWidget.close()` routes through `closeEvent` -> `QDialog::reject`, so a
        plain `close()` on a confirmed dialog is IGNORED. Shipped exactly that
        way for one commit -- the mandate signed, the SAID banner appeared behind
        the modal, and the modal sat on "Signing..." for the life of the process.

        So the guard yields to exactly one caller: the page, once issuance has
        actually resolved. Escape and the header X still cannot reach this.
        """
        self._finished = True
        self.close()

    def reject(self):
        """Escape must not destroy this modal once signing has begun.

        `_on_confirm` disables both buttons, but Escape reaches `QDialog::reject`
        through Qt's own key handling and no `setEnabled(False)` stands in its
        way. The issuance carries on regardless -- destroying the dialog only
        removes the surface that reports the outcome, and leaves `fail()` with
        nothing to re-arm.

        `_finished` is the deliberate exception. Without it this guard also
        blocks the page's own completion path, because `close()` is implemented
        in terms of `reject()`.
        """
        if self._confirmed and not self._finished:
            return
        super().reject()

    def _on_confirm(self) -> None:
        self._confirmed = True
        self._confirm_button.setEnabled(False)
        self._confirm_button.setText(copy.IN_FLIGHT)
        # Nothing can be kept-editing once it is being signed: clicking back
        # mid-flight destroyed the modal while the issuance carried on, leaving
        # no surface to report success or failure on. `fail()` re-arms it.
        self._back.setEnabled(False)
        self.confirm.emit()

    def confirmed(self) -> bool:
        return self._confirmed

    def fail(self, message: str) -> None:
        """Re-enable the primary after a failed anchor, so a retry is possible."""
        self._confirmed = False
        self._confirm_button.setEnabled(True)
        self._confirm_button.setText(copy.REVIEW_CONFIRM)
        self._back.setEnabled(True)
        self.show_error(message)
