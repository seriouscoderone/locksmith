# -*- encoding: utf-8 -*-
"""
locksmith.ui.onboarding.form_builder module

``SchemaFormBuilder`` — a pure JSON-Schema -> Qt form factory (design spec
§7.4). It turns a command's ``payload_schema`` into a widget tree, and back
into values + validation messages. **Pure presentation layer only**: no
doers, no I/O, no resolver imports — schema in, ``QWidget``/values/messages
out. Callers (Task 6's ``OnboardingHomePage``/request flow) own everything
that touches the network, the vault, or serviceaid.

Widget mapping (spec §7.4 table)::

    string (+minLength, +pattern)        -> QLineEdit + validator
    string + format: email               -> QLineEdit + email validator
    string + enum                        -> QComboBox
    array of enum (+uniqueItems)         -> checkbox group (minItems enforced)
    number / integer (+minimum)          -> QDoubleSpinBox / QSpinBox
    boolean                              -> QCheckBox
    object                               -> nested QGroupBox (recurse)
    string + format: date-time           -> auto-filled at submit, not shown

Toolkit reuse (house style, per Task 4's ``setup_page.py``): fields reuse
``locksmith.ui.toolkit`` widgets **where the toolkit widget actually
subclasses the Qt base class the contract (and B6's tests) assert against**.
``LocksmithLineEdit`` and ``LocksmithCheckbox`` qualify (they subclass
``QLineEdit``/``QCheckBox`` directly) and are used for the ``string``
(non-enum) and ``boolean`` cases, including each checkbox-group item.
``FloatingLabelLineEdit`` and ``FloatingLabelComboBox`` do **not** qualify —
both wrap a Qt widget as a plain ``QWidget`` rather than subclassing it — so
this builder falls back to plain ``QComboBox``/``QSpinBox``/``QDoubleSpinBox``/
``QGroupBox`` for enum-select, numeric, and object-group fields, matching the
brief's explicit fallback list. See the Task 5 report for the full
toolkit-vs-plain rationale.

Unsupported constructs (any ``array`` whose ``items`` isn't an enum-of-string,
or any field missing/with an unrecognized ``type``) never fail silently: they
render a visible inline error row (a ``QLabel`` with ``objectName
"form-error"``) in place of the field, and are excluded from ``values()``/
``validate()``.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from locksmith.ui import colors
from locksmith.ui.toolkit.widgets import LocksmithCheckbox
from locksmith.ui.toolkit.widgets.fields import LocksmithLineEdit

# Simple, permissive email-shape check — this is a form-level UX guard, not a
# full RFC 5322 validator (that's not this module's job).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Generous numeric bounds so a schema's `minimum` is honored as a floor
# without the Qt spinbox's tiny (0-99) default ceiling clipping legitimate
# values (e.g. reserve amounts in the millions).
_INT_CEILING = 2_000_000_000
_FLOAT_CEILING = 1_000_000_000_000.0


# Acceptance-demo fix wave item 1: QSpinBox/QDoubleSpinBox/QComboBox/QGroupBox
# get NO color from the app-wide stylesheet (`ui/styles.py`'s selector list
# only covers QLabel/QPushButton/QLineEdit/QListWidget::Item), so — unlike
# LocksmithLineEdit/LocksmithCheckbox, which carry their own explicit
# background+text-color QSS — they render with the OS's native (and, under a
# dark system appearance, dark) palette regardless of this app's own light
# theme. These per-instance QSS snippets give every field-like widget this
# builder renders the SAME explicit light-theme colors, so none of them can
# go dark-on-dark independent of the surrounding page.
def _field_qss(widget_type: str) -> str:
    return f"""
        {widget_type} {{
            border: 1px solid {colors.BORDER_NEUTRAL};
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 14px;
            background-color: {colors.BACKGROUND_CONTENT};
            color: {colors.TEXT_PRIMARY};
        }}
        {widget_type} QAbstractItemView {{
            background-color: {colors.BACKGROUND_CONTENT};
            color: {colors.TEXT_PRIMARY};
            selection-background-color: {colors.BACKGROUND_SELECTION};
        }}
    """


_GROUP_BOX_QSS = f"""
    QGroupBox {{
        border: 1px solid {colors.BORDER};
        border-radius: 8px;
        margin-top: 14px;
        padding: 12px 8px 8px 8px;
        font-size: 13px;
        font-weight: 600;
        color: {colors.TEXT_PRIMARY};
        background-color: transparent;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 6px;
        padding: 0 4px;
        color: {colors.TEXT_PRIMARY};
    }}
"""


class SchemaFormBuilder:
    """Builds a Qt form from a JSON-Schema ``payload_schema`` object, and
    extracts values/validation messages back out of it.

    Usage::

        builder = SchemaFormBuilder(payload_schema)
        widget = builder.build(parent=some_page)
        ...
        errors = builder.validate()
        if not errors:
            data = builder.values()
    """

    def __init__(self, payload_schema: Dict[str, Any]):
        """
        Args:
            payload_schema: A JSON-Schema ``object`` schema (the command's
                payload contract — see design spec §7.4). Only the subset
                described in the widget-mapping table above is guaranteed
                to render as a real control; anything else renders as a
                visible error row rather than being silently dropped.
        """
        self._schema = payload_schema
        self._reset()

    def _reset(self) -> None:
        self._widgets: Dict[str, QWidget] = {}
        self._kind: Dict[str, str] = {}
        self._field_schema: Dict[str, Dict[str, Any]] = {}
        self._required: Dict[str, bool] = {}
        self._leaf_paths: List[str] = []
        self._hidden_fields: List[str] = []
        self._touched: set = set()
        self._checkbox_items: Dict[str, List[Tuple[str, QCheckBox]]] = {}

    # -- construction ---------------------------------------------------

    def build(self, parent: Optional[QWidget] = None) -> QWidget:
        """Build (or rebuild) the form widget tree.

        Returns:
            A ``QWidget`` containing one labeled row per renderable field
            (a ``QFormLayout``), with nested ``object`` schemas recursed
            into child ``QGroupBox`` rows.
        """
        self._reset()
        root = QWidget(parent)
        layout = QFormLayout(root)
        self._populate(
            layout,
            self._schema.get("properties", {}) or {},
            self._schema.get("required", []) or [],
            prefix="",
        )
        return root

    def _populate(
        self,
        layout: QFormLayout,
        properties: Dict[str, Any],
        required_list: List[str],
        prefix: str,
    ) -> None:
        for key, subschema in properties.items():
            path = f"{prefix}.{key}" if prefix else key
            required = key in required_list
            self._required[path] = required
            field_type = subschema.get("type")
            description = subschema.get("description", "")
            label_text = self._label_for(key, required)

            if field_type == "string" and subschema.get("format") == "date-time":
                # Auto-filled at submit time (client clock) — never rendered.
                self._hidden_fields.append(path)
                continue

            if field_type == "string":
                self._build_string_field(layout, path, label_text, subschema, description)
            elif field_type in ("number", "integer"):
                self._build_numeric_field(layout, path, label_text, field_type, subschema, description)
            elif field_type == "boolean":
                self._build_boolean_field(layout, path, label_text, subschema, description)
            elif field_type == "array":
                self._build_array_field(layout, path, label_text, subschema, description)
            elif field_type == "object":
                self._build_object_field(layout, path, label_text, subschema, description)
            else:
                self._add_error_row(layout, path, f"unsupported schema type {field_type!r}")

    def _build_string_field(self, layout, path, label_text, subschema, description) -> None:
        enum_values = subschema.get("enum")
        if enum_values:
            combo = QComboBox()
            combo.setStyleSheet(_field_qss("QComboBox"))
            combo.addItems([str(v) for v in enum_values])
            combo.setCurrentIndex(-1)
            if description:
                combo.setToolTip(description)
            combo.currentIndexChanged.connect(lambda _i, p=path: self._touched.add(p))
            self._register(path, combo, "combo", subschema)
            layout.addRow(label_text, combo)
        else:
            line = LocksmithLineEdit()
            if description:
                line.setToolTip(description)
            line.textChanged.connect(lambda _t, p=path: self._touched.add(p))
            self._register(path, line, "line_edit", subschema)
            layout.addRow(label_text, line)

    def _build_numeric_field(self, layout, path, label_text, field_type, subschema, description) -> None:
        minimum = subschema.get("minimum")
        if field_type == "number":
            spin = QDoubleSpinBox()
            spin.setStyleSheet(_field_qss("QDoubleSpinBox"))
            spin.setDecimals(2)
            spin.setMaximum(_FLOAT_CEILING)
            spin.setMinimum(float(minimum) if minimum is not None else -_FLOAT_CEILING)
            kind = "double_spin"
        else:
            spin = QSpinBox()
            spin.setStyleSheet(_field_qss("QSpinBox"))
            spin.setMaximum(_INT_CEILING)
            spin.setMinimum(int(minimum) if minimum is not None else -_INT_CEILING)
            kind = "int_spin"
        if description:
            spin.setToolTip(description)
        spin.valueChanged.connect(lambda _v, p=path: self._touched.add(p))
        self._register(path, spin, kind, subschema)
        layout.addRow(label_text, spin)

    def _build_boolean_field(self, layout, path, label_text, subschema, description) -> None:
        checkbox = LocksmithCheckbox(label_text)
        if description:
            checkbox.setToolTip(description)
        checkbox.toggled.connect(lambda _c, p=path: self._touched.add(p))
        self._register(path, checkbox, "checkbox", subschema)
        layout.addRow(checkbox)

    def _build_array_field(self, layout, path, label_text, subschema, description) -> None:
        items_schema = subschema.get("items", {}) or {}
        enum_values = items_schema.get("enum")
        if items_schema.get("type") == "string" and enum_values:
            group = QGroupBox(label_text)
            group.setStyleSheet(_GROUP_BOX_QSS)
            if description:
                group.setToolTip(description)
            group_layout = QFormLayout(group)
            checkboxes: List[Tuple[str, QCheckBox]] = []
            for value in enum_values:
                cb = LocksmithCheckbox(str(value))
                cb.toggled.connect(lambda _c, p=path: self._touched.add(p))
                group_layout.addRow(cb)
                checkboxes.append((str(value), cb))
            self._checkbox_items[path] = checkboxes
            self._register(path, group, "checkbox_group", subschema)
            layout.addRow(group)
        else:
            self._add_error_row(layout, path, "unsupported array construct (items must be a string enum)")

    def _build_object_field(self, layout, path, label_text, subschema, description) -> None:
        group = QGroupBox(label_text)
        group.setStyleSheet(_GROUP_BOX_QSS)
        if description:
            group.setToolTip(description)
        group_layout = QFormLayout(group)
        self._populate(
            group_layout,
            subschema.get("properties", {}) or {},
            subschema.get("required", []) or [],
            prefix=path,
        )
        # Container paths are addressable via widget_for() but carry no value
        # of their own — they must NOT enter the leaf iteration that drives
        # values()/validate(). (The real carrier application schema lists its
        # nested objects in the top-level `required`; registering containers
        # as leaves made values() crash on it.) Required-ness is enforced at
        # the LEAF level: each nested object's own `required` list is passed
        # into the recursion above.
        self._widgets[path] = group
        self._kind[path] = "group"
        self._field_schema[path] = subschema
        layout.addRow(group)

    def _add_error_row(self, layout: QFormLayout, path: str, reason: str) -> None:
        """Never drop an unsupported construct silently — render a visible
        inline error row instead so the gap is obvious to whoever is
        looking at the form (dev or user), rather than a field quietly
        missing from the UI."""
        message = QLabel(f"Cannot render field '{path}': {reason}")
        message.setObjectName("form-error")
        message.setWordWrap(True)
        message.setStyleSheet(
            f"color: {colors.DANGER}; background-color: {colors.BACKGROUND_ERROR}; "
            "border-radius: 6px; padding: 6px 10px;"
        )
        layout.addRow(message)

    @staticmethod
    def _label_for(key: str, required: bool) -> str:
        friendly = key.replace("_", " ").title()
        return f"{friendly} *" if required else friendly

    def _register(self, path: str, widget: QWidget, kind: str, subschema: Dict[str, Any]) -> None:
        self._widgets[path] = widget
        self._kind[path] = kind
        self._field_schema[path] = subschema
        self._leaf_paths.append(path)

    # -- introspection ----------------------------------------------------

    def widget_for(self, dotted_path: str) -> Optional[QWidget]:
        """Return the widget registered for a dotted field path (nested
        object fields use ``parent.child`` notation), or ``None`` if the
        path isn't a rendered field (e.g. hidden or unsupported)."""
        return self._widgets.get(dotted_path)

    def hidden_autofill_fields(self) -> List[str]:
        """Dotted paths of ``string``+``format: date-time`` fields — never
        rendered; the caller auto-fills these (client clock) at submit."""
        return list(self._hidden_fields)

    def replace_field_with_combo(self, path: str, options: List[Tuple[Any, str]]) -> QComboBox:
        """Replace an already-rendered leaf field's widget IN PLACE with a
        ``QComboBox`` offering exactly ``options`` (``(raw_value,
        display_text)`` pairs) as choices.

        This is the seam a caller uses to narrow a payload property's
        control to an authority-sourced option set (design spec §7.4's "one
        control serves both": a context dimension that matches a payload
        property becomes the SAME rendered field, not a duplicate widget)
        rather than the schema's own (wider, or entirely absent) enum —
        e.g. a free-text ``jurisdiction`` string becomes a combo of only
        the states an actual authority is registered for, so the user can
        never type an arbitrary, unmatchable value into it.

        The field's registered ``kind`` becomes ``"context_combo"``:
        ``values()``/``set_field()`` treat it like the ordinary enum
        ``"combo"`` kind, EXCEPT the extracted/set value is the combo's raw
        ``itemData`` (not its display text, which may carry a caller-added
        badge like ``" (pilot)"`` the underlying value must never include).
        ``validate()`` deliberately does NOT enforce requiredness for this
        kind — a caller that replaces a field this way takes over that
        field's requiredness messaging itself (the same way it already has
        to message a wholly separate "dedicated" context combo), keeping
        this builder ignorant of prompts/authorities/EGF concepts.

        Must be called AFTER ``build()``. ``path`` must already be a
        rendered ``line_edit`` or ``combo`` leaf field — anything else (a
        container/group path, a hidden autofill field, or an unknown path)
        raises ``KeyError``, mirroring ``set_field``'s own guard.
        """
        kind = self._kind.get(path)
        old_widget = self._widgets.get(path)
        if old_widget is None or kind not in ("line_edit", "combo"):
            raise KeyError(
                f"cannot replace non-field path {path!r} with a combo (kind={kind!r})"
            )

        # Every rendered leaf field's widget lives in a QFormLayout row —
        # either the root's own (top-level properties) or a nested
        # QGroupBox's (see _build_object_field) — by construction of
        # _populate/build, so parentWidget().layout() is always one.
        layout = old_widget.parentWidget().layout()

        row, _role = layout.getWidgetPosition(old_widget)
        label_item = layout.itemAt(row, QFormLayout.ItemRole.LabelRole)
        label_widget = label_item.widget() if label_item is not None else None
        label_text = label_widget.text() if label_widget is not None else path
        layout.removeRow(row)  # deletes old_widget (and its label) for us

        combo = QComboBox()
        combo.setStyleSheet(_field_qss("QComboBox"))
        for raw_value, display_text in options:
            combo.addItem(display_text, raw_value)
        combo.setCurrentIndex(-1)
        combo.currentIndexChanged.connect(lambda _i, p=path: self._touched.add(p))
        layout.insertRow(row, label_text, combo)

        self._widgets[path] = combo
        self._kind[path] = "context_combo"
        return combo

    # -- values / validation ----------------------------------------------

    def set_field(self, name: str, value: Any) -> None:
        """Programmatically set a rendered field's value by dotted path,
        and mark it as user-set (included by ``values()`` even if
        optional)."""
        kind = self._kind.get(name)
        widget = self._widgets.get(name)
        if kind is None or widget is None:
            raise KeyError(f"no rendered field for path {name!r}")

        if kind == "line_edit":
            widget.setText(str(value))
        elif kind == "combo":
            idx = widget.findText(str(value))
            widget.setCurrentIndex(idx)
        elif kind == "context_combo":
            idx = widget.findData(value)
            widget.setCurrentIndex(idx)
        elif kind in ("double_spin", "int_spin"):
            widget.setValue(value)
        elif kind == "checkbox":
            widget.setChecked(bool(value))
        elif kind == "checkbox_group":
            selected = set(value or [])
            for enum_value, cb in self._checkbox_items.get(name, []):
                cb.setChecked(enum_value in selected)
        else:
            raise KeyError(f"cannot set value for non-leaf path {name!r} (kind={kind!r})")

        self._touched.add(name)

    def values(self) -> Dict[str, Any]:
        """Extract current form values as a nested dict matching the
        schema's shape (dotted paths become nested keys).

        Only fields that are **required** or that the user has **touched**
        (via a UI edit or ``set_field``) are included — untouched optional
        fields are omitted rather than reported as empty/zero. ``boolean``
        fields are always included: an unchecked box is itself a
        meaningful ``False``, not an "unset" state."""
        result: Dict[str, Any] = {}
        for path in self._leaf_paths:
            kind = self._kind[path]
            if kind == "checkbox":
                include = True
            else:
                include = self._required.get(path, False) or path in self._touched
            if not include:
                continue
            self._assign_nested(result, path, self._extract_value(path, kind))
        return result

    def _extract_value(self, path: str, kind: str) -> Any:
        widget = self._widgets[path]
        if kind == "line_edit":
            return widget.text()
        if kind == "combo":
            return widget.currentText()
        if kind == "context_combo":
            return widget.currentData()
        if kind in ("double_spin", "int_spin"):
            return widget.value()
        if kind == "checkbox":
            return widget.isChecked()
        if kind == "checkbox_group":
            return [value for value, cb in self._checkbox_items.get(path, []) if cb.isChecked()]
        raise AssertionError(f"unhandled kind {kind!r}")

    @staticmethod
    def _assign_nested(result: Dict[str, Any], dotted_path: str, value: Any) -> None:
        parts = dotted_path.split(".")
        node = result
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def validate(self) -> List[str]:
        """Return human-readable validation messages (empty list == valid).
        Each message names the offending field by its dotted path so
        callers/tests can assert on the field involved (e.g.
        ``"applicant_legal_name is required"``)."""
        messages: List[str] = []
        for path in self._leaf_paths:
            kind = self._kind[path]
            required = self._required.get(path, False)
            field_schema = self._field_schema[path]
            widget = self._widgets[path]

            if kind == "line_edit":
                text = widget.text()
                if required and not text.strip():
                    messages.append(f"{path} is required")
                    continue
                if text:
                    min_length = field_schema.get("minLength")
                    if min_length is not None and len(text) < min_length:
                        messages.append(f"{path} must be at least {min_length} characters")
                    pattern = field_schema.get("pattern")
                    if pattern and not re.fullmatch(pattern, text):
                        messages.append(f"{path} does not match the required pattern")
                    if field_schema.get("format") == "email" and not _EMAIL_RE.fullmatch(text):
                        messages.append(f"{path} must be a valid email address")
            elif kind == "combo":
                if required and widget.currentIndex() == -1:
                    messages.append(f"{path} is required")
            elif kind == "context_combo":
                # Requiredness for a caller-installed context combo (see
                # replace_field_with_combo's docstring) is validated and
                # messaged by the CALLER, not this builder — it deliberately
                # treats the field as always "valid" from its own narrow,
                # EGF-ignorant perspective.
                pass
            elif kind == "checkbox_group":
                min_items = field_schema.get("minItems", 0)
                checked = sum(1 for _v, cb in self._checkbox_items.get(path, []) if cb.isChecked())
                if required and checked == 0:
                    messages.append(f"{path} is required")
                elif (required or path in self._touched) and checked < min_items:
                    # Same required-or-touched gating as the other kinds: an
                    # optional, untouched group is simply omitted — minItems
                    # only binds once the array will actually be submitted.
                    messages.append(f"{path} requires at least {min_items} selection(s)")
            elif kind in ("double_spin", "int_spin"):
                if required and path not in self._touched:
                    messages.append(f"{path} is required")
            elif kind == "checkbox":
                # A boolean always has a value (default False) — there is
                # no "unset" state for JSON-Schema `required` to enforce.
                pass
        return messages
