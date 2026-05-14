from locksmith.plugins.designer.widgets.editor_tab_bar import EditorTabBar


def test_renders_supplied_tabs(qapp):
    bar = EditorTabBar(["Envelope", "Schema", "Lifecycle"])
    assert bar.tab_names() == ["Envelope", "Schema", "Lifecycle"]


def test_active_tab_defaults_to_first(qapp):
    bar = EditorTabBar(["A", "B", "C"])
    assert bar.active_tab() == "A"


def test_set_active_changes_state(qapp):
    bar = EditorTabBar(["A", "B", "C"])
    bar.set_active("B")
    assert bar.active_tab() == "B"


def test_clicking_tab_emits_changed_signal(qapp):
    bar = EditorTabBar(["A", "B"])
    received: list[str] = []
    bar.tab_changed.connect(lambda name: received.append(name))
    bar._buttons["B"].click()
    assert received == ["B"]
    assert bar.active_tab() == "B"
