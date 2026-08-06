# main_window.py
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGridLayout,
    QHeaderView,
    QListWidgetItem,
    QMainWindow,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from audio.synth_engine import SynthEngine
from models.music_data import MusicData
from widgets.region2_list_widget import Region2ListWidget
from widgets.region_table_widget import RegionTableWidget
from widgets.timeline_list_widget import TimelineListWidget
from workers.score_load_worker import ScoreLoadThread


class MainWindow(QMainWindow):

    # Boundary ("doh") cue for Ref 2 AC4 / Ref 3 AC4 (C5) - a short, quiet,
    # low double-bass note played instead of moving, so it isn't mistaken
    # for a note in the score. Not part of any part's playback, so it gets
    # a channel of its own rather than reusing get_channel_for_part: D-5
    # allocates channels 0-8,10-15 in part-list order, so channel 15 is the
    # one least likely to collide with a real part (only would on a 15+
    # part score). See D-9 in tasks.txt.
    BOUNDARY_CHANNEL = 15
    BOUNDARY_GM_PROGRAM = 43  # GM 44 Contrabass, 0-indexed on the wire
    BOUNDARY_MIDI_PITCH = 37  # C#2 - low
    BOUNDARY_DURATION_MS = 100  # roughly a semiquaver; independent of score tempo

    def __init__(self, synth=None):
        """Create the main window.

        synth: any object exposing the SynthEngine interface
        (play_chord / play_notes / stop_all_notes / set_program / close). Defaults to a
        real SynthEngine. Tests pass a stand-in so no audio device is
        opened, and so they can assert what would have sounded.
        """
        super().__init__()
        self.setWindowTitle("Score View & Editor")
        self.resize(800, 600)

        self._music_data: MusicData | None = None
        self._load_thread: ScoreLoadThread | None = None
        self.synth = synth if synth is not None else SynthEngine()

        self.setup_ui()
        self.setup_menu()

    def setup_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        grid_layout = QGridLayout(central_widget)

        # Region 1: Property List
        self.region_1 = self.create_property_list([])

        # Region 2: Parts/Staves/Voices hierarchy, navigated Up/Down, O to toggle
        self.region_2 = Region2ListWidget()
        self.region_2.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.region_2.filter_changed.connect(self._on_region_2_filter_changed)

        # Region 3: Timeline List
        self.region_3 = TimelineListWidget()
        self.region_3.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.region_3.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.region_3.itemSelectionChanged.connect(self._on_region_3_selection_changed)

        self.select_all_shortcut = QShortcut(QKeySequence("Ctrl+A"), self.region_3)
        self.select_all_shortcut.activated.connect(self.select_all_region_3)

        # Region 4: Property List
        self.region_4 = self.create_property_list([])

        grid_layout.addWidget(self.region_1, 0, 0)
        grid_layout.addWidget(self.region_2, 0, 1)
        grid_layout.addWidget(self.region_3, 1, 0)
        grid_layout.addWidget(self.region_4, 1, 1)

        grid_layout.setRowStretch(0, 1)
        grid_layout.setRowStretch(1, 1)
        grid_layout.setColumnStretch(0, 1)
        grid_layout.setColumnStretch(1, 1)

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

    def create_property_list(self, items: list) -> RegionTableWidget:
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
        if self._load_thread is not None:
            return

        self._load_thread = ScoreLoadThread(file_path, self)
        self._load_thread.loaded.connect(self._on_score_loaded)
        self._load_thread.failed.connect(self._on_score_load_failed)
        self._load_thread.finished.connect(self._on_load_thread_finished)
        self._load_thread.start()

    def _on_score_loaded(self, music_data: MusicData):
        self._music_data = music_data
        self._update_ui_regions()

    def _on_score_load_failed(self, error_text: str):
        print(f"[ERROR] Failed to load score file:\n{error_text}")

    def _on_load_thread_finished(self):
        self._load_thread = None

    def navigate_timeline_left(self):
        if not self._music_data:
            return
        if self._music_data.move_timeline_left():
            self._update_timeline_views(play_all=True)
        else:
            self._play_boundary_cue()

    def navigate_timeline_right(self):
        if not self._music_data:
            return
        if self._music_data.move_timeline_right():
            self._update_timeline_views(play_all=True)
        else:
            self._play_boundary_cue()

    def navigate_measure_left(self):
        if not self._music_data:
            return
        if self._music_data.move_timeline_left_by_measure():
            self._update_timeline_views(play_all=True)
        else:
            self._play_boundary_cue()

    def navigate_measure_right(self):
        if not self._music_data:
            return
        if self._music_data.move_timeline_right_by_measure():
            self._update_timeline_views(play_all=True)
        else:
            self._play_boundary_cue()

    def navigate_timeline_home(self):
        if not self._music_data:
            return
        self._music_data.move_timeline_home()
        self._update_timeline_views(play_all=True)

    def navigate_timeline_end(self):
        if not self._music_data:
            return
        self._music_data.move_timeline_end()
        self._update_timeline_views(play_all=True)

    def _play_boundary_cue(self):
        """Ref 2 AC4 / Ref 3 AC4: plays instead of moving, when a navigation
        key would move past a boundary of the active timeline (C5)."""
        self.synth.play_notes(
            midi_notes=[self.BOUNDARY_MIDI_PITCH],
            duration_ms=self.BOUNDARY_DURATION_MS,
            channel=self.BOUNDARY_CHANNEL,
            program=self.BOUNDARY_GM_PROGRAM,
        )

    def select_all_region_3(self):
        self.region_3.selectAll()
        self._play_selected_region_3_notes()

    def on_region_3_vertical_move(self):
        self._play_selected_region_3_notes()

    def _on_region_2_filter_changed(self, active_voice_tuples: set):
        if self._music_data:
            self._music_data.set_active_voice_filter(active_voice_tuples)
            self._update_timeline_views(play_all=False)

    def _on_region_3_selection_changed(self):
        if not self._music_data:
            return

        selected_indices = [item.row() for item in self.region_3.selectedIndexes()]
        region_4_data = self._music_data.get_region_4_data_for_indices(selected_indices)
        self._populate_table(self.region_4, region_4_data)

    def _play_selected_region_3_notes(self):
        if not self._music_data:
            return

        selected_indices = [item.row() for item in self.region_3.selectedIndexes()]
        events = self._music_data.get_playback_events_for_indices(selected_indices)

        if not events:
            return

        duration_ms = self._music_data.get_current_duration_ms()

        self.synth.play_chord(events, duration_ms=duration_ms)

    def _update_timeline_views(self, play_all: bool = True):
        if not self._music_data:
            return

        self.region_3.blockSignals(True)
        self.region_3.clear()

        for item in self._music_data.get_region_3_data():
            self.region_3.addItem(QListWidgetItem(item))

        self.region_3.selectAll()
        self.region_3.blockSignals(False)

        self._on_region_3_selection_changed()

        if play_all:
            self._play_selected_region_3_notes()

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

        self._populate_table(self.region_1, self._music_data.get_region_1_data())
        self.region_2.load_score_structure(self._music_data.get_score_structure())
        self._update_timeline_views(play_all=True)

    def closeEvent(self, event):
        if self._load_thread is not None:
            self._load_thread.wait()
        self.synth.close()
        super().closeEvent(event)