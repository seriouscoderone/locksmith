import os
import gc

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

try:
    from PySide6.QtWidgets import QApplication
    _PYSIDE6_AVAILABLE = True
except ImportError:
    _PYSIDE6_AVAILABLE = False


if _PYSIDE6_AVAILABLE:
    @pytest.fixture(scope="session")
    def qapp():
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app
        app.closeAllWindows()
        app.processEvents()
        app.quit()
        gc.collect()


    @pytest.fixture(autouse=True)
    def cleanup_qt_widgets(qapp):
        yield
        for widget in list(qapp.topLevelWidgets()):
            widget.close()
            widget.deleteLater()
        qapp.processEvents()
        gc.collect()
