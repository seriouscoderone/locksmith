from locksmith.plugins.designer.widgets.payload_schema_table import (
    PayloadSchemaTable,
)


def test_renders_one_row_per_property(qapp):
    schema = {
        "type": "object",
        "required": ["a"],
        "properties": {
            "a": {"type": "string"},
            "b": {"type": "integer"},
        },
    }
    table = PayloadSchemaTable(schema)
    rows = table.field_rows()
    assert len(rows) == 2
    assert rows[0]["field"] == "a"
    assert rows[1]["field"] == "b"


def test_required_field_is_marked(qapp):
    schema = {
        "type": "object",
        "required": ["a"],
        "properties": {"a": {"type": "string"}, "b": {"type": "integer"}},
    }
    table = PayloadSchemaTable(schema)
    rows = table.field_rows()
    a = next(r for r in rows if r["field"] == "a")
    b = next(r for r in rows if r["field"] == "b")
    assert a["required"] is True
    assert b["required"] is False


def test_pattern_constraint_rendered(qapp):
    schema = {
        "type": "object",
        "properties": {"license_number": {"type": "string", "pattern": "^[A-Z0-9-]+$"}},
    }
    table = PayloadSchemaTable(schema)
    rows = table.field_rows()
    assert "^[A-Z0-9-]+$" in rows[0]["constraint"]


def test_enum_constraint_rendered(qapp):
    schema = {
        "type": "object",
        "properties": {
            "lines": {"type": "array",
                       "items": {"type": "string",
                                 "enum": ["property", "casualty", "life", "health"]}}
        },
    }
    table = PayloadSchemaTable(schema)
    rows = table.field_rows()
    assert "enum" in rows[0]["constraint"]
    assert "property" in rows[0]["constraint"]


def test_empty_schema_renders_no_rows(qapp):
    table = PayloadSchemaTable({})
    assert table.field_rows() == []
