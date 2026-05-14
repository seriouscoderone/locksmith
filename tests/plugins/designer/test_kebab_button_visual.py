from locksmith.plugins.designer.widgets.kebab_button import KebabButton


def test_kebab_button_shows_three_dots(qapp):
    b = KebabButton()
    assert b.text() == "⋯"


def test_kebab_button_emits_clicked(qapp):
    b = KebabButton()
    fired = []
    b.clicked.connect(lambda: fired.append(True))
    b.click()
    assert fired == [True]
