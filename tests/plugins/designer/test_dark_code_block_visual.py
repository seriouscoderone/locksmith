from locksmith.plugins.designer.widgets.dark_code_block import DarkCodeBlock


def test_renders_supplied_text(qapp):
    block = DarkCodeBlock("event.attributes.amount > 100")
    assert block.toPlainText() == "event.attributes.amount > 100"


def test_is_read_only(qapp):
    block = DarkCodeBlock("anything")
    assert block.isReadOnly() is True


def test_uses_dark_palette(qapp):
    block = DarkCodeBlock("anything")
    style = block.styleSheet()
    assert "#1A1C20" in style or "#222" in style
    assert "#E0E0E0" in style or "#fff" in style or "#eaeaea" in style.lower()


def test_empty_string_renders_clean(qapp):
    block = DarkCodeBlock("")
    assert block.toPlainText() == ""
