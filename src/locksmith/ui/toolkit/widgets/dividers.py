from PySide6.QtWidgets import QFrame

from locksmith.ui import colors


class LocksmithDivider(QFrame):

    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet(f"background-color: {colors.DIVIDER};")
