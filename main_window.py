# main_window.py
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
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
from widgets.about_dialog import AboutDialog
from widgets.goto_measure_dialog import GotoMeasureDialog
from widgets.region2_list_widget import Region2ListWidget
from widgets.region_table_widget import RegionTableWidget
from widgets.status_bar_widget import StatusBarWidget
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

        # C6: real QMainWindow status bar so NVDA+End ("report status bar")
        # works via Qt's native accessibility role.
        self.status_bar = StatusBarWidget()
        self.setStatusBar(self.status_bar)

        # Region cycling deliberately does NOT use QWidget.setTabOrder/
        # focusNextChild: Qt's focus chain is ONE shared window-wide doubly
        # linked ring, and setTabOrder(a, b) works by relocating b's node in
        # that ring. Closing a 4-widget loop needs region_1 to be relocated
        # too (the wrap-around region_4->region_1 call), which resets
        # region_1's own outgoing pointer as a side effect - silently
        # breaking the region_1->region_2 edge set earlier. This isn't
        # fixable by reordering the calls: with 4 widgets each used once as
        # a source and once as a target, the dependency between the calls is
        # circular. So each region widget's keyPressEvent calls
        # focus_next_region/focus_previous_region below directly instead,
        # bypassing the global chain entirely.

        # C7: F6/Shift+F6 toggle focus between the regions area (restoring
        # whichever region was last focused) and the status bar. Menu bar
        # access stays on the OS's native Alt mechanism, not F6/Tab.
        self._last_focused_region = self.region_1
        QApplication.instance().focusChanged.connect(self._on_focus_changed)

        # WindowShortcut (Qt's default context) fires regardless of which
        # child widget within this window currently holds focus - exactly
        # what's needed here - without ApplicationShortcut's app-wide scope,
        # which caused ambiguous-shortcut conflicts between MainWindow
        # instances left alive across tests in the same QApplication.
        self.f6_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F6), self)
        self.f6_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.f6_shortcut.activated.connect(self._toggle_pane)

        self.shift_f6_shortcut = QShortcut(QKeySequence("Shift+F6"), self)
        self.shift_f6_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.shift_f6_shortcut.activated.connect(self._toggle_pane)

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

        # C8: Navigation duplicates, as menu items, the keyboard-only ways of
        # moving to the start, end, or a specific measure (Refs 5, 6) - for
        # anyone who prefers a menu over typing into the Note region.
        # Edit/View/Options are deliberately not added yet - see tasks.txt C8.
        navigation_menu = menu_bar.addMenu("&Navigation")

        # Kept as attributes, not local variables - PySide's Python wrapper
        # for a QAction/QMenu can be garbage-collected even though the
        # underlying C++ object is still parented and alive, leaving a
        # "libshiboken: Internal C++ object already deleted" trap for any
        # later code (tests included) that tries to reach it via
        # menuBar().actions() traversal instead.
        self.first_measure_action = QAction("Move to &First Note", self)
        self.first_measure_action.setShortcut(QKeySequence(Qt.Key.Key_Home))
        self.first_measure_action.triggered.connect(self._navigation_menu_first_measure)

        self.last_measure_action = QAction("Move to &Last Note", self)
        self.last_measure_action.setShortcut(QKeySequence(Qt.Key.Key_End))
        self.last_measure_action.triggered.connect(self._navigation_menu_last_measure)

        self.goto_measure_action = QAction("&Go to Measure...", self)
        self.goto_measure_action.setShortcut(QKeySequence("Ctrl+G"))
        self.goto_measure_action.triggered.connect(self._show_goto_measure_dialog)

        navigation_menu.addAction(self.first_measure_action)
        navigation_menu.addAction(self.last_measure_action)
        navigation_menu.addSeparator()
        navigation_menu.addAction(self.goto_measure_action)

        help_menu = menu_bar.addMenu("&Help")

        self.about_action = QAction("&About Recall Score...", self)
        self.about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(self.about_action)

    def _region_cycle_order(self) -> list:
        return [self.region_1, self.region_2, self.region_3, self.region_4]

    def focus_next_region(self, current):
        """Tab within the regions area (the MAA): cycles 1->2->3->4->1 and
        cannot leave the MAA. Called directly by each region widget's
        keyPressEvent rather than relying on Qt's global focus chain - see
        the comment in setup_ui for why setTabOrder can't do this here."""
        regions = self._region_cycle_order()
        index = regions.index(current)
        regions[(index + 1) % len(regions)].setFocus()

    def focus_previous_region(self, current):
        """Shift+Tab within the regions area: the reverse of focus_next_region."""
        regions = self._region_cycle_order()
        index = regions.index(current)
        regions[(index - 1) % len(regions)].setFocus()

    def _navigation_menu_first_measure(self):
        self.navigate_timeline_home()
        self.region_3.setFocus()

    def _navigation_menu_last_measure(self):
        self.navigate_timeline_end()
        self.region_3.setFocus()

    def _show_goto_measure_dialog(self):
        current_measure = None
        if self._music_data:
            current_slice = self._music_data.get_current_slice()
            if current_slice:
                current_measure = current_slice.measure
        dialog = GotoMeasureDialog(self, current_measure=current_measure)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            measure_number = dialog.measure_number()
            if measure_number is not None:
                self.navigate_to_typed_measure(str(measure_number))
                self.region_3.setFocus()

    def _show_about_dialog(self):
        AboutDialog(self).exec()

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

    def on_pending_digits_changed(self, digits: str):
        """C6/C4: while a bar number is being typed, show it in the status
        bar's position field in place of "Measure X beat Y" - reverts once
        the digits are cleared (Enter, Escape, or any other key)."""
        if not self._music_data:
            return
        if digits:
            fields = self._music_data.get_status_bar_fields()
            fields[0] = f"Go to bar: {digits}"
            self.status_bar.set_fields(fields)
        else:
            self._update_status_bar()

    def navigate_to_typed_measure(self, digits: str):
        """Ref 6 (C4): Enter with pending digits in the Note region jumps to
        that bar's first active event; an unknown bar plays the boundary cue
        and leaves the position unchanged (AC4)."""
        if not self._music_data:
            return
        measure_number = int(digits)
        if self._music_data.jump_to_measure(measure_number):
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
        self._update_status_bar()

        if play_all:
            self._play_selected_region_3_notes()

    def _update_status_bar(self):
        if not self._music_data:
            return
        self.status_bar.set_fields(self._music_data.get_status_bar_fields())

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

    def _on_focus_changed(self, old, now):
        """C7: remembers which region last held focus, so F6's "regions"
        pane stop can restore it rather than always landing on Region 1."""
        if now in (self.region_1, self.region_2, self.region_3, self.region_4):
            self._last_focused_region = now

    def _current_pane(self) -> str:
        focus = self.focusWidget()
        if focus is not None and (focus is self.status_bar or self.status_bar.isAncestorOf(focus)):
            return "status"
        return "region"

    def _focus_region_pane(self):
        (self._last_focused_region or self.region_1).setFocus()

    def _toggle_pane(self):
        """F6/Shift+F6 (C7): toggle focus between the regions area
        (restoring whichever region was last focused) and the status bar.
        Just these two panes - menu bar access is left to the OS's native
        Alt mechanism, not F6."""
        if self._current_pane() == "status":
            self._focus_region_pane()
        else:
            self.status_bar.first_field().setFocus()

    def closeEvent(self, event):
        if self._load_thread is not None:
            self._load_thread.wait()
        self.synth.close()
        super().closeEvent(event)