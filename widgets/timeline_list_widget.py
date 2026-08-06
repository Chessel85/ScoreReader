# timeline_list_widget.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget


class TimelineListWidget(QListWidget):
    """
    Region 3 list widget handling custom timeline traversal (Left/Right)
    and single-note selection collapsing (Up/Down).
    """

    def keyPressEvent(self, event):
        key = event.key()
        main_win = self.window()
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)

        if key == Qt.Key.Key_Left:
            if ctrl:
                if hasattr(main_win, "navigate_measure_left"):
                    main_win.navigate_measure_left()
            elif hasattr(main_win, "navigate_timeline_left"):
                main_win.navigate_timeline_left()
        elif key == Qt.Key.Key_Right:
            if ctrl:
                if hasattr(main_win, "navigate_measure_right"):
                    main_win.navigate_measure_right()
            elif hasattr(main_win, "navigate_timeline_right"):
                main_win.navigate_timeline_right()
        elif key == Qt.Key.Key_Home:
            if hasattr(main_win, "navigate_timeline_home"):
                main_win.navigate_timeline_home()
        elif key == Qt.Key.Key_End:
            if hasattr(main_win, "navigate_timeline_end"):
                main_win.navigate_timeline_end()
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            super().keyPressEvent(event)
            if hasattr(main_win, "on_region_3_vertical_move"):
                main_win.on_region_3_vertical_move()
        elif key == Qt.Key.Key_Tab:
            main_win.focusNextChild()
        elif key == Qt.Key.Key_Backtab:
            main_win.focusPreviousChild()
        else:
            super().keyPressEvent(event)