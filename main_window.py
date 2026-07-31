# main_window.py
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHeaderView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from music_data import MusicData
from musicXML_reader import MusicXMLReader


class RegionTableWidget(QTableWidget):
    """Custom QTableWidget that forwards Tab/Shift+Tab to top-level window focus loop."""

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Tab:
            self.window().focusNextChild()
        elif event.key() == Qt.Key.Key_Backtab:
            self.window().focusPreviousChild()
        else:
            super().keyPressEvent(event)


class TimelineListWidget(QListWidget):
    """Single-column QListWidget for Region 3 supporting Left/Right timeline traversal."""

    def keyPressEvent(self, event):
        key = event.key()
        main_win = self.window()

        if key == Qt.Key.Key_Left:
            if hasattr(main_win, "navigate_timeline_left"):
                main_win.navigate_timeline_left()
        elif key == Qt.Key.Key_Right:
            if hasattr(main_win, "navigate_timeline_right"):
                main_win.navigate_timeline_right()
        elif key == Qt.Key.Key_Tab:
            main_win.focusNextChild()
        elif key == Qt.Key.Key_Backtab:
            main_win.focusPreviousChild()
        else:
            super().keyPressEvent(event)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Score View & Editor")
        self.resize(800, 600)

        self._music_data: MusicData | None = None

        self.setup_ui()
        self.setup_menu()

    def setup_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        grid_layout = QGridLayout(central_widget)

        self.region_1 = self.create_property_list([])
        self.region_2 = self.create_property_list([])

        self.region_3 = TimelineListWidget()
        self.region_3.setFocusPolicy(Qt.FocusPolicy.TabFocus)

        self.region_4 = self.create_property_list([])

        # Grid positioning
        grid_layout.addWidget(self.region_1, 0, 0)
        grid_layout.addWidget(self.region_2, 0, 1)
        grid_layout.addWidget(self.region_3, 1, 0)
        grid_layout.addWidget(self.region_4, 1, 1)

        # 1:1 proportional stretching
        grid_layout.setRowStretch(0, 1)
        grid_layout.setRowStretch(1, 1)
        grid_layout.setColumnStretch(0, 1)
        grid_layout.setColumnStretch(1, 1)

        # Tab navigation order
        QWidget.setTabOrder(self.region_1, self.region_2)
        QWidget.setTabOrder(self.region_2, self.region_3)
        QWidget.setTabOrder(self.region_3, self.region_4)
        QWidget.setTabOrder(self.region_4, self.region_1)

        self.region_1.setFocus()

    def setup_menu(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.setStatusTip("Open a MusicXML file")
        open_action.triggered.connect(self.open_file_dialog)

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)

        file_menu.addAction(open_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

    def create_property_list(self, items: list) -> QTableWidget:
        table = RegionTableWidget(len(items), 2)
        table.setHorizontalHeaderLabels(["Property", "Value"])

        for row, (prop, val) in enumerate(items):
            table.setItem(row, 0, QTableWidgetItem(prop))
            table.setItem(row, 1, QTableWidgetItem(val))

        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setFocusPolicy(Qt.FocusPolicy.TabFocus)

        return table

    def open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open MusicXML Score",
            "",
            "MusicXML Files (*.xml *.musicxml *.mxl);;All Files (*)",
        )

        if file_path:
            self.load_score_from_file(file_path)

    def load_score_from_file(self, file_path: str):
        reader = MusicXMLReader(file_path)
        self._music_data = reader.load()
        self._update_ui_regions()

    def navigate_timeline_left(self):
        """Handler for Left Arrow key in Region 3."""
        if self._music_data and self._music_data.move_timeline_left():
            self._update_timeline_views()

    def navigate_timeline_right(self):
        """Handler for Right Arrow key in Region 3."""
        if self._music_data and self._music_data.move_timeline_right():
            self._update_timeline_views()

    def _update_timeline_views(self):
        """Updates Region 3 and Region 4 on timeline position change."""
        if not self._music_data:
            return

        # Update Region 3 (List)
        self.region_3.clear()
        for item in self._music_data.get_region_3_data():
            self.region_3.addItem(QListWidgetItem(item))
        if self.region_3.count() > 0:
            self.region_3.setCurrentRow(0)

        # Update Region 4 (Table)
        self._populate_table(self.region_4, self._music_data.get_region_4_data())

    def _populate_table(self, table: QTableWidget, data_dict: dict):
        items = list(data_dict.items())
        table.clearContents()
        table.setRowCount(len(items))
        for row, (key, value) in enumerate(items):
            table.setItem(row, 0, QTableWidgetItem(str(key)))
            table.setItem(row, 1, QTableWidgetItem(str(value)))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def _update_ui_regions(self):
        if not self._music_data:
            return

        # Region 1: Score Metadata & Credits
        self._populate_table(self.region_1, self._music_data.get_region_1_data())

        # Region 2: Score Hierarchy
        self._populate_table(self.region_2, self._music_data.get_region_2_data())

        # Regions 3 & 4: Timeline & Detail View
        self._update_timeline_views()