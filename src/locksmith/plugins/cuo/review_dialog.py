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
    QCheckBox,
    QFrame,
    QScrollArea,
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
from locksmith.ui.styles import get_monospace_font_family
from locksmith.ui.toolkit.widgets.dialogs import LocksmithDialog

_ROWS = ("line_of_business", "jurisdiction", "coverages")
#: Rendered in the monospace face — see `_row`. Codes and dates, not prose: these
#: are the values a human has to proof-read character by character.
_MONO_FIELDS = frozenset({"jurisdiction", "coverages"})

#: ux-patterns.md:82 "Max width: `sm: 400px`, `md: 560px`", and :674 builds its
#: worked modal at `md`.
_MODAL_WIDTH = 560
#: `LocksmithDialog._build_button_section` gives the footer container 16px side
#: margins (dialogs.py:452), so this is the width the button row can occupy.
_FOOTER_WIDTH = _MODAL_WIDTH - 32
#: ux-patterns.md:80 "Backdrop: Dark overlay (`bg-black/50`)" — 50% of 255.
_BACKDROP_ALPHA = 128
#: Header + pinned caution + acknowledgement + button row, i.e. everything the
#: body does NOT get. Measured on the built dialog rather than derived.
_DIALOG_CHROME_HEIGHT = 300
#: Never squeeze the body below this, however small the window.
_MIN_BODY_HEIGHT = 180
#: The width a body label actually wraps at: the modal less the base class's
#: 20px content-area side margins (dialogs.py:436), less the thesis rail's own
#: 15px of border and padding.
_BODY_WIDTH = _MODAL_WIDTH - 40 - 15


def _fit_wrapped(label: QLabel, width: int) -> None:
    """Give a word-wrapping QLabel the height it will actually paint at `width`.

    `sizeHint()` is computed at the label's NATURAL width -- one line -- so a
    label that wraps reports less height than it needs and the layout hands it
    exactly that. Measured: the thesis at four wrapped lines reported 80px and
    painted its last line underneath the pinned caution, while `visibleRegion()`
    still claimed 80 of 80. `page._fit` has the same blind spot; it works there
    only because those labels wrap at their natural width.

    `heightForWidth` is the only call that asks the real question.
    """
    if not label.text():
        label.setMinimumHeight(0)
        return
    label.setMinimumHeight(max(label.heightForWidth(width),
                               label.sizeHint().height()))


def _row(label: str, value: str, mono: bool = False) -> QWidget:
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
    # Machine-shaped values go in the monospace face. `US-AB` and `US-AU`, or
    # `2026-08-19` and `2026-08-91`, are near-identical shapes in a proportional
    # UI face at 14px -- and a transposed jurisdiction is precisely the error no
    # validation can catch, which is why the form's own help text delegates it to
    # this screen. Mono makes the substitution visible and signals "this is a
    # literal string, not prose".
    #
    # Resolved through `get_monospace_font_family()`, never a hardcoded stack: the
    # app picks the family centrally, and the suite's "SF Mono"/"Menlo" are its
    # FALLBACKS (design-system.md:94), not the face.
    face = f" font-family: {get_monospace_font_family()};" if mono else ""
    shown.setStyleSheet(
        f"color: {colors.TEXT_PRIMARY}; font-size: 14px;{face}")
    layout.addWidget(name)
    layout.addWidget(shown, 1)
    return row


class MandateReviewDialog(LocksmithDialog):
    """Read back the canonical payload; confirm or go back."""

    confirm = Signal()

    def __init__(self, payload: dict, signer_name: str, signer_aid: str = "",
                 parent=None):
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

        # FIRST, above the values. A prompt to check that arrives after the thing
        # to be checked is a prompt to check nothing.
        intro = QLabel(copy.REVIEW_INTRO)
        intro.setObjectName("mandateReviewDialog.intro")
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {colors.TEXT_PRIMARY}; font-size: 14px;")
        outer.addWidget(intro)

        summary = QWidget()
        summary.setObjectName("mandateReviewDialog.summary")
        rows = QVBoxLayout(summary)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(0)
        for field in _ROWS:
            value = payload.get(field)
            shown = ", ".join(value) if isinstance(value, list) else str(value or "")
            rows.addWidget(_row(copy.FIELD_LABEL[field], shown,
                                mono=field in _MONO_FIELDS))
        # ISO on purpose -- see the module docstring.
        rows.addWidget(_row(copy.REVIEW_IN_FORCE_LABEL, (
            f"{payload.get('window_opens', '')} through "
            f"{payload.get('window_closes', '')}, inclusive"), mono=True))
        # The signer is a ROW, not prose: a label in front of the value stops a
        # keystore alias like "default" reading as an adverb. The AID rides with
        # it because the alias is a local label and the prefix is what signs.
        signed_by = signer_name if not signer_aid else f"{signer_name}\n{signer_aid}"
        signer_row = _row(copy.REVIEW_SIGNER_LABEL, signed_by, mono=bool(signer_aid))
        signer_row.setObjectName("mandateReviewDialog.signer")
        rows.addWidget(signer_row)
        outer.addWidget(summary)

        authority = QLabel(copy.REVIEW_AUTHORITY)
        authority.setObjectName("mandateReviewDialog.authority")
        authority.setWordWrap(True)
        authority.setStyleSheet(f"color: {colors.TEXT_SECONDARY}; font-size: 12px;")
        outer.addWidget(authority)

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

        # Split into a lede and a body inside ONE amber frame. 44 words at a
        # single size is texture by the fifth mandate of the day; the lede is the
        # whole decision and the body is the detail behind it. The frame carries
        # the fill so the two labels read as one block.
        caution = QFrame()
        caution.setObjectName("mandateReviewDialog.caution")
        caution_column = QVBoxLayout(caution)
        caution_column.setContentsMargins(12, 10, 12, 10)
        caution_column.setSpacing(4)

        caution_head = QLabel(copy.REVIEW_CAUTION_HEAD)
        caution_head.setObjectName("mandateReviewDialog.cautionHead")
        caution_head.setWordWrap(True)
        # 14px/600, not bold: design-system.md:118 reserves "bold" for 700, and
        # WCAG's 3:1 relaxation for large-bold text therefore does NOT apply here
        # -- this has to clear 4.5:1 on the amber fill, which WARNING_TEXT does.
        caution_head.setStyleSheet(
            f"color: {colors.WARNING_TEXT}; font-size: 14px; font-weight: 600;"
            f" background: transparent; border: none; padding: 0;")
        caution_column.addWidget(caution_head)

        caution_body = QLabel(copy.REVIEW_CAUTION)
        caution_body.setObjectName("mandateReviewDialog.cautionBody")
        caution_body.setWordWrap(True)
        caution_body.setStyleSheet(
            f"color: {colors.WARNING_TEXT}; font-size: 12px;"
            f" background: transparent; border: none; padding: 0;")
        caution_column.addWidget(caution_body)
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
        # objectName-scoped so the fill and rule land on the FRAME only. An
        # unscoped rule cascades to both child labels, and each would then paint
        # its own amber box with its own left rule inside the outer one.
        caution.setStyleSheet(
            f"QFrame#mandateReviewDialog\\.caution {{"
            f" background: {colors.BACKGROUND_WARNING};"
            f" border-left: 4px solid {colors.WARNING_BORDER};"
            f" border-radius: 4px; }}")

        self._back = LocksmithInvertedButton(copy.REVIEW_BACK)
        self._back.setObjectName("mandateReviewDialog.back")
        self._confirm_button = LocksmithButton(copy.REVIEW_CONFIRM)
        self._confirm_button.setObjectName("mandateReviewDialog.confirm")

        # The affirmative act. Signing used to be two clicks in a straight line
        # from a filled form, the second landing on an already-enabled primary, so
        # what stood between a mandate and the world was the ABSENCE of an
        # objection. The modal's opening state is now non-signable.
        #
        # Honest about what this does and does not buy: it will not make anyone
        # read. What it buys is that a fast stray click cannot land on an enabled
        # primary, and that publishing requires an action taken on purpose.
        self._ack = QCheckBox(copy.REVIEW_ACK)
        self._ack.setObjectName("mandateReviewDialog.ack")
        self._ack.setStyleSheet(
            f"QCheckBox {{ color: {colors.TEXT_PRIMARY}; font-size: 12px; }}")
        self._confirm_button.setEnabled(False)
        self._ack.toggled.connect(self._confirm_button.setEnabled)

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
        footer_column.addWidget(self._ack)

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
        # NO `show_overlay`. ux-patterns.md:80 asks for a `bg-black/50` backdrop
        # and this dialog carried one for two commits -- but NOTHING else in the
        # application does (`AppSettingsDialog` and the rest all take the
        # show_overlay=False default), and the owner, looking at the CUO modal
        # beside Settings and the vault drawer, found this one visibly darker than
        # every other dialog in the product. It was two layers: the app already
        # reads as dimmed behind a modal, and this added a second scrim over it.
        #
        # The suite is a web spec and its backdrop rule assumes it is the only
        # dimming mechanism. House consistency wins over a rule that produces a
        # dialog unlike every other one. Owner decision, 2026-08-08.
        #
        # Modality is NOT lost with it: the page calls `dialog.open()`, which sets
        # WindowModal on its own -- measured, `isModal() True`. `show_overlay` was
        # only ever an additional `setModal(True)` (dialogs.py:105-106), i.e.
        # APPLICATION modality, which is also what greyed the window's own title
        # bar and made this dialog look different from Settings.
        super().__init__(parent=parent, title=copy.REVIEW_TITLE,
                         content=body, buttons=buttons,
                         show_close_button=False)
        self.setObjectName("mandateReviewDialog")

        # Grow to fit rather than scroll. Measured after the caution moved to the
        # footer: the scroll viewport was 238px against 345px of content, so the
        # THESIS -- the thing actually being signed -- was below the fold on open,
        # which is a worse failure than the clipped caution that prompted the
        # move. Nothing was forcing the dialog taller: the base class already
        # allowed 1000px (`_max_dialog_height`) and the dialog was using 533.
        #
        # Bounded, not unbounded: `_max_dialog_height` is the window's own height
        # less a margin, and the chrome allowance keeps the header, the pinned
        # caution and the buttons on screen. Past that the body scrolls again,
        # which is the correct behaviour for a genuinely long thesis.
        # Before measuring the body: every wrapping label must first know the
        # height it will really paint at this width, or the body's own height is
        # computed from labels that are each a line short.
        for wrapped in body.findChildren(QLabel):
            if wrapped.wordWrap():
                _fit_wrapped(wrapped, _BODY_WIDTH)
        body.adjustSize()

        scroll = self.findChild(QScrollArea)
        if scroll is not None:
            # `_max_dialog_height` is populated in the base class's showEvent and
            # is still None here, so ask the calculator directly.
            ceiling = self._calculate_max_dialog_height() or 1000
            budget = max(_MIN_BODY_HEIGHT, ceiling - _DIALOG_CHROME_HEIGHT)
            # heightForWidth at the REAL width, not sizeHint. A word-wrapped
            # QLabel's sizeHint is computed at its natural width and
            # under-reports once it wraps -- measured, the long thesis's last
            # line painted underneath the pinned caution while Qt reported
            # content and viewport both 402px and showed no scrollbar.
            width = _FOOTER_WIDTH
            layout = body.layout()
            wanted = (layout.heightForWidth(width) if layout is not None
                      and layout.hasHeightForWidth() else body.sizeHint().height())
            scroll.setMinimumHeight(min(max(wanted, body.sizeHint().height()),
                                        budget))

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

        # Kept, and harmless, for whenever a scrim is switched back on: the base
        # class paints `rgba(0, 0, 0, 150)` = 59% (dialogs.py:479) where
        # ux-patterns.md:80 says `bg-black/50` = 128. `self.overlay` is None while
        # `show_overlay` stays off, so this is a no-op today.
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
        # ux-patterns.md:426 puts opening focus on the first interactive element,
        # which is now the acknowledgement. The safety property is unchanged and
        # is what matters here: Space toggles a focused checkbox, Return still
        # activates the DEFAULT button, which is "Keep editing" -- so no single
        # keystroke on the freshly-opened dialog can sign.
        self._ack.setFocus()

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
        """Re-enable the primary after a failed anchor, so a retry is possible.

        The acknowledgement is not re-demanded: the CUO already gave it for these
        exact values, which have not changed, and clearing it would read as the
        app doubting them rather than as a fresh decision. The primary comes back
        only if it is still ticked.
        """
        self._confirmed = False
        self._confirm_button.setEnabled(self._ack.isChecked())
        self._confirm_button.setText(copy.REVIEW_CONFIRM)
        self._back.setEnabled(True)
        self.show_error(message)
