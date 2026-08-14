# main_window.py
import os
import sys
from typing import Optional

from PySide6.QtCore import QLocale, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHeaderView,
    QMainWindow,
    QTableWidget,
    QWidget,
)

from audio.synth_engine import SynthEngine
from controllers.attribute_controller import AttributeController
from controllers.focus_controller import FocusController
from controllers.navigation_controller import NavigationController
from controllers.playback_controller import PlaybackController
from controllers.region_presenter import RegionPresenter
from controllers.score_persistence import ScorePersistenceController
from controllers.score_session import ScoreSession
from models.vocabulary import bar_word
from persistence import app_settings
from persistence.app_settings import AppSettings
from widgets.about_dialog import AboutDialog
from widgets.attribute_order_dialog import AttributeOrderDialog
from widgets.goto_measure_dialog import GotoMeasureDialog
from widgets.menu_builder import MenuBuilder, goto_measure_action_text
from widgets.performance_report_dialog import PerformanceReportDialog
from widgets.region2_list_widget import Region2ListWidget
from widgets.region2_manager import node_breadcrumb
from widgets.region4_table_widget import Region4TableWidget
from widgets.region5_list_widget import Region5ListWidget
from widgets.region_table_widget import RegionTableWidget
from widgets.status_bar_widget import StatusBarWidget
from widgets.tempo_offset_dialog import TempoOffsetDialog
from widgets.timeline_list_widget import TimelineListWidget


def detect_default_uk_terms(system_locale: Optional[QLocale] = None) -> bool:
    """F4/D-6: UK is the safe default; only a positively-detected US locale
    switches it. Anything indeterminate (non-English, unresolvable) stays
    UK rather than guessing. Lives here, not models/vocabulary.py, because
    it needs QLocale and models/ stays Qt-free. system_locale is injectable
    so tests are deterministic regardless of the machine."""
    loc = system_locale if system_locale is not None else QLocale.system()
    # PySide6 6.11 exposes the non-deprecated .territory() method, but it
    # still returns the QLocale.Country enum (not a separate Territory enum
    # class, unlike some Qt6 versions/bindings) - verified via introspection.
    return loc.territory() != QLocale.Country.UnitedStates


def _app_base_dir() -> str:
    """A data file's parent directory: next to main_window.py (repo root) in
    dev, or the frozen bundle root (sys._MEIPASS) once packaging/
    RecallScore.spec bundles it - same idiom as main.py's _app_icon_path()."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def user_guide_html_path() -> str:
    return os.path.join(_app_base_dir(), "docs", "user_guide.html")


def examples_dir() -> str:
    return os.path.join(_app_base_dir(), "examples")


class MainWindow(QMainWindow):
    """The window shell: builds the widgets, owns the controllers, and wires
    them together. Deliberately holds almost no logic of its own.

    The methods below are mostly one-line delegators. They are the stable
    API the region widgets call (via window()) and the tests drive, so they
    stay here as a facade even though the work happens in controllers/.
    """

    # Re-exported so callers (and tests) can name the boundary cue's voice
    # without reaching into the playback controller.
    BOUNDARY_CHANNEL = PlaybackController.BOUNDARY_CHANNEL
    BOUNDARY_GM_PROGRAM = PlaybackController.BOUNDARY_GM_PROGRAM
    BOUNDARY_MIDI_PITCH = PlaybackController.BOUNDARY_MIDI_PITCH
    BOUNDARY_DURATION_MS = PlaybackController.BOUNDARY_DURATION_MS

    def __init__(self, synth=None, uk_terms: bool | None = None):
        """Create the main window.

        synth: any object with the SynthEngine interface (play_chord /
        play_notes / stop_all_notes / set_program / close). Tests pass a
        stand-in so no audio device opens and they can assert what would
        have sounded.

        uk_terms: startup dialect override. None resolves to the saved
        AppSettings value, falling back to OS-locale detection when nothing
        has ever been saved. An explicit value skips both and is not
        persisted, so tests are deterministic regardless of the machine.
        """
        super().__init__()
        self.setWindowTitle("Recall Score")
        self.resize(800, 600)

        if uk_terms is None:
            saved_uk_terms = app_settings.load().uk_terms
            uk_terms = (
                saved_uk_terms if saved_uk_terms is not None else detect_default_uk_terms()
            )

        self.session = ScoreSession(
            synth if synth is not None else SynthEngine(), uk_terms, parent=self
        )

        self.setup_ui()
        self.setup_controllers()
        self.setup_menu()
        self.connect_signals()

        self.region_1.setFocus()

    # --- construction -------------------------------------------------

    def setup_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        grid_layout = QGridLayout(central_widget)

        # Region 1: score info
        self.region_1 = self.create_property_list()

        # Region 2: Parts/Staves/Voices hierarchy, navigated Up/Down, O to toggle
        self.region_2 = Region2ListWidget()
        self.region_2.setFocusPolicy(Qt.FocusPolicy.TabFocus)

        # Region 3: Timeline List
        self.region_3 = TimelineListWidget()
        self.region_3.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.region_3.setFocusPolicy(Qt.FocusPolicy.TabFocus)

        # Region 4: note attributes. Region4TableWidget (not the plain
        # RegionTableWidget Region 1 uses) adds the Ref 15 AC4 context menu
        # for appending/removing an attribute in Region 3's note display.
        self.region_4 = self.create_property_list(table_cls=Region4TableWidget)

        # Region 5 (Ref 29, the "Performance region"): duration-spanning
        # markers (repeat barlines, 1st/2nd endings, crescendo/diminuendo
        # hairpins) active at the cursor's current position.
        self.region_5 = Region5ListWidget()
        self.region_5.setFocusPolicy(Qt.FocusPolicy.TabFocus)

        # Row 1 = 2 regions, row 2 = 3 - a deliberate departure from the
        # original 2x2 (agreed with the user: consistent region numbering
        # matters far more than visual layout here). A 6-column grid, the
        # LCM of 2 and 3, keeps both rows aligned under one layout.
        grid_layout.addWidget(self.region_1, 0, 0, 1, 3)
        grid_layout.addWidget(self.region_2, 0, 3, 1, 3)
        grid_layout.addWidget(self.region_3, 1, 0, 1, 2)
        grid_layout.addWidget(self.region_4, 1, 2, 1, 2)
        grid_layout.addWidget(self.region_5, 1, 4, 1, 2)

        grid_layout.setRowStretch(0, 1)
        grid_layout.setRowStretch(1, 1)
        for col in range(6):
            grid_layout.setColumnStretch(col, 1)

        # A real QMainWindow status bar, so NVDA+End ("report status bar")
        # works through Qt's native accessibility role.
        self.status_bar = StatusBarWidget()
        self.setStatusBar(self.status_bar)

        self.setup_shortcuts()

    def setup_shortcuts(self):
        """WindowShortcut fires regardless of which child widget has focus,
        which is what's wanted, without ApplicationShortcut's app-wide scope
        - that causes ambiguous-shortcut conflicts between MainWindow
        instances alive in the same QApplication.

        Ctrl+M/Ctrl+P/Ctrl+G/Ctrl+T have no QShortcut here: their menu
        actions carry the shortcut themselves.
        """
        self.select_all_shortcut = QShortcut(QKeySequence("Ctrl+A"), self.region_3)
        self.select_all_shortcut.activated.connect(self.select_all_region_3)

        def window_shortcut(sequence, slot):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(slot)
            return shortcut

        # C7: F6/Shift+F6 toggle between the regions area (restoring the
        # last-focused region) and the status bar. Menu bar access stays on
        # the OS's native Alt mechanism.
        self.f6_shortcut = window_shortcut(Qt.Key.Key_F6, self._toggle_pane)
        self.shift_f6_shortcut = window_shortcut("Shift+F6", self._toggle_pane)

        # Tempo controls (Ref 12) are global, not Note-region-scoped like
        # arrow-key navigation: they adjust a playback-wide setting rather
        # than a per-row position. Playback transport is global for the
        # same reason.
        self.tempo_faster_shortcut = window_shortcut(Qt.Key.Key_F, self.tempo_faster)
        self.tempo_slower_shortcut = window_shortcut(Qt.Key.Key_S, self.tempo_slower)
        self.tempo_reset_shortcut = window_shortcut(Qt.Key.Key_D, self.tempo_reset)
        self.play_stop_shortcut = window_shortcut(Qt.Key.Key_Space, self.toggle_play_stop)
        self.pause_resume_shortcut = window_shortcut("Ctrl+Space", self.toggle_pause_resume)

        # Ref 13: re-trigger the chord at the cursor on demand. No held-key
        # tracking needed - AC2's "hold for the marked length" is already
        # each note's own duration, and "or pressed again" is a plain
        # retrigger, which play_chord's default already handles.
        self.chord_audition_shortcut = window_shortcut(
            "Shift+Space", self._audition_current_selection
        )

    def setup_controllers(self):
        regions = [self.region_1, self.region_2, self.region_3, self.region_4, self.region_5]

        self.playback = PlaybackController(self.session, parent=self)
        self.navigation = NavigationController(self.session, parent=self)
        self.focus = FocusController(self, regions, self.status_bar)
        self.presenter = RegionPresenter(
            self.session, self.region_1, self.region_2, self.region_3,
            self.region_4, self.region_5, self.status_bar,
            playback_status_fields=self.playback.status_fields,
            parent=self,
        )
        self.attributes = AttributeController(self.session, self.presenter, self)
        self.persistence = ScorePersistenceController(self.session, self.region_2)

        self.focus.connect_tracking()

    def setup_menu(self):
        actions = MenuBuilder(self, self, self.session.uk_terms).build()
        self._actions = actions

        # Kept as individual attributes: the names the tests and the rest of
        # the window already use.
        self.clear_preferences_action = actions.clear_preferences
        self.performance_report_action = actions.performance_report
        self.first_measure_action = actions.first_measure
        self.last_measure_action = actions.last_measure
        self.goto_measure_action = actions.goto_measure
        self.move_to_notes_action = actions.move_to_notes
        self.move_to_metadata_action = actions.move_to_metadata
        self.move_to_parts_action = actions.move_to_parts
        self.move_to_attributes_action = actions.move_to_attributes
        self.move_to_performance_action = actions.move_to_performance
        self.tempo_offset_action = actions.tempo_offset
        self.terminology_language_group = actions.terminology_group
        self.uk_language_action = actions.uk_language
        self.us_language_action = actions.us_language
        self.metronome_action = actions.metronome
        self.position_announcer_action = actions.position_announcer
        self.attribute_order_action = actions.attribute_order
        self.user_guide_action = actions.user_guide
        self.about_action = actions.about

        self.persistence.clear_action = actions.clear_preferences
        self.persistence.refresh_clear_action()
        self.focus.first_measure_action = actions.first_measure
        self.focus.last_measure_action = actions.last_measure
        self.focus.update_navigation_actions_enabled()

    def connect_signals(self):
        """The one place the controllers are joined up. Each is otherwise
        unaware of the others."""
        self.session.score_loaded.connect(self._on_score_loaded)
        self.session.load_failed.connect(self._on_score_load_failed)

        # Both "the cursor moved" sources land on the same redraw.
        self.navigation.position_changed.connect(self.presenter.update_timeline_views)
        self.navigation.boundary_hit.connect(self.playback.play_boundary_cue)
        self.playback.cursor_moved.connect(self.presenter.update_timeline_views)
        self.playback.status_text_changed.connect(self.presenter.update_status_bar)
        self.playback.playback_state_changed.connect(
            self.presenter.update_playback_status_field
        )

        # Emitted from inside update_timeline_views, and delivered
        # synchronously, so the notes still sound before the performance cue.
        self.presenter.audition_requested.connect(self._audition_current_selection)

        self.region_2.filter_changed.connect(self.presenter.on_region_2_filter_changed)
        self.region_3.itemSelectionChanged.connect(
            self.presenter.on_region_3_selection_changed
        )

    def create_property_list(self, table_cls: type = RegionTableWidget) -> RegionTableWidget:
        """An empty two-column property table for Region 1 or Region 4.
        Population is RegionPresenter.populate_table's job, once a score is
        loaded."""
        table = table_cls(0, 2)
        table.setHorizontalHeaderLabels(["Property", "Value"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        return table

    # --- state exposed for the widgets and tests ----------------------

    @property
    def _music_data(self):
        return self.session.music_data

    @property
    def synth(self):
        return self.session.synth

    @property
    def sequencer(self):
        return self.playback.sequencer

    @property
    def _uk_terms(self) -> bool:
        return self.session.uk_terms

    @property
    def _load_thread(self):
        return self.session.load_thread

    @property
    def _last_focused_region(self):
        return self.focus.last_focused_region

    @property
    def _focus_tracking_connected(self) -> bool:
        return self.focus.tracking_connected

    # --- loading -------------------------------------------------------

    def open_file_dialog(self):
        self._open_score_file_dialog(start_dir="")

    def open_example_file_dialog(self):
        self._open_score_file_dialog(start_dir=examples_dir())

    def _open_score_file_dialog(self, start_dir: str):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open MusicXML Score",
            start_dir,
            "MusicXML Files (*.xml *.musicxml *.mxl);;All Files (*)",
        )
        if file_path:
            self.load_score_from_file(file_path)

    def load_score_from_file(self, file_path: str):
        if self.session.is_loading():
            return
        self._save_current_score_config()
        self.session.load(file_path)

    def _on_score_loaded(self, music_data):
        """Orchestration only - which is why it stays in the shell. The order
        matters: the saved config has to be applied to MusicData before the
        regions render, and Region 2's own per-node toggles have to be in
        effect before the first audition, or the opening chord includes
        voices the user had switched off."""
        self.setWindowTitle(f"{os.path.basename(music_data.file_path)} - Recall Score")

        saved_config = self.persistence.load_for_current()
        if saved_config is not None:
            music_data.apply_config(saved_config)
        self.persistence.refresh_clear_action()

        self.presenter.reset_performance_labels()
        self.playback.attach_score(
            music_data, mixer=saved_config.mixer if saved_config is not None else None
        )

        # Suppress the initial audition when there's a config to restore,
        # and fire it once Region 2's restored state is actually in effect -
        # otherwise the first sound heard on load includes voices that were
        # saved as off, even though every later move excludes them.
        self._update_ui_regions(play_all=saved_config is None)
        if saved_config is not None:
            self.region_2.apply_off_node_keys(
                saved_config.parts_off, saved_config.staves_off, saved_config.voices_off
            )
            self._audition_current_selection()

    def _on_score_load_failed(self, error_text: str):
        print(f"[ERROR] Failed to load score file:\n{error_text}")

    def _update_ui_regions(self, play_all: bool = True):
        if not self._music_data:
            return
        self.presenter.refresh_region_1()
        self.region_2.load_score_structure(self._music_data.get_score_structure())
        self.metronome_action.setChecked(self._music_data.metronome_enabled)
        self.position_announcer_action.setChecked(self._music_data.position_announcer_enabled)
        self.presenter.update_timeline_views(play_all=play_all)

    # --- navigation (delegators) --------------------------------------

    def navigate_timeline_left(self):
        self.navigation.timeline_left()

    def navigate_timeline_right(self):
        self.navigation.timeline_right()

    def navigate_measure_left(self):
        self.navigation.measure_left()

    def navigate_measure_right(self):
        self.navigation.measure_right()

    def navigate_timeline_home(self):
        self.navigation.timeline_home()

    def navigate_timeline_end(self):
        self.navigation.timeline_end()

    def navigate_to_typed_measure(self, digits: str):
        self.navigation.to_typed_measure(digits)

    def on_pending_digits_changed(self, digits: str):
        self.presenter.show_pending_digits(digits)

    def jump_to_performance_span_start(self):
        self.navigation.jump_to_span(self.region_5.current_row_data(), is_start=True)

    def jump_to_performance_span_end(self):
        self.navigation.jump_to_span(self.region_5.current_row_data(), is_start=False)

    # --- playback (delegators) ----------------------------------------

    def toggle_play_stop(self):
        self.playback.toggle_play_stop()

    def toggle_pause_resume(self):
        self.playback.toggle_pause_resume()

    def audition_phrase(self):
        self.playback.audition_phrase()

    def tempo_faster(self):
        self.playback.tempo_faster()

    def tempo_slower(self):
        self.playback.tempo_slower()

    def tempo_reset(self):
        self.playback.tempo_reset()

    def toggle_metronome(self):
        self.metronome_action.setChecked(self.playback.toggle_metronome())

    def toggle_position_announcer(self):
        self.position_announcer_action.setChecked(
            self.playback.toggle_position_announcer()
        )

    def _play_boundary_cue(self):
        self.playback.play_boundary_cue()

    def _audition_current_selection(self):
        self.playback.audition_selection(self.presenter.selected_region_3_indices())

    def select_all_region_3(self):
        self.presenter.select_all_region_3()

    def on_region_3_vertical_move(self):
        self._audition_current_selection()

    # --- focus (delegators) -------------------------------------------

    def focus_next_region(self, current):
        self.focus.focus_next(current)

    def focus_previous_region(self, current):
        self.focus.focus_previous(current)

    def _toggle_pane(self):
        self.focus.toggle_pane()

    def _navigation_menu_first_measure(self):
        self.navigate_timeline_home()
        self.region_3.setFocus()

    def _navigation_menu_last_measure(self):
        self.navigate_timeline_end()
        self.region_3.setFocus()

    def _navigation_menu_move_to_notes(self):
        self.region_3.setFocus()

    def _navigation_menu_move_to_metadata(self):
        self.region_1.setFocus()

    def _navigation_menu_move_to_parts(self):
        self.region_2.setFocus()

    def _navigation_menu_move_to_attributes(self):
        self.region_4.setFocus()

    def _navigation_menu_move_to_performance(self):
        self.region_5.setFocus()

    # --- attributes (delegators) --------------------------------------

    def show_region_4_attribute_menu(self, row: int, column: int, global_pos):
        self.attributes.show_menu(row, column, global_pos)

    def _region_4_attribute_menu_actions(self, row: int) -> list:
        return self.attributes.menu_actions(row)

    def _build_region_4_attribute_menu(self, row: int):
        return self.attributes.build_menu(row)

    def _restore_region_4_focus_after_menu(self, row: int, column: int):
        self.attributes.restore_focus_after_menu(row, column)

    def _apply_display_attribute_change(self, attribute_key: str, scope: str,
                                        notes: list, add: bool):
        self.attributes.apply_change(attribute_key, scope, notes, add)

    def _attribute_order_pairs_for_node(self, node) -> list:
        return self.attributes.order_pairs_for_node(node)

    def _show_attribute_order_dialog(self):
        """Ref 15 AC4: scoped to whichever part/staff/voice Region 2 has
        selected. The dialog's whole context comes from there, so that is
        where focus returns afterwards."""
        node = self.attributes.scope_node()
        if node is None:
            return
        dialog = AttributeOrderDialog(
            self,
            pairs=self.attributes.order_pairs_for_node(node),
            scope_description=node_breadcrumb(node),
        )
        dialog.move_requested.connect(
            lambda attribute_key, up: self.attributes.on_order_move(
                dialog, node, attribute_key, up
            )
        )
        dialog.exec()
        self.region_2.setFocus()

    # --- presentation (delegators) ------------------------------------

    def _populate_table(self, table: QTableWidget, data_dict: dict):
        self.presenter.populate_table(table, data_dict)

    def _update_timeline_views(self, play_all: bool = True):
        self.presenter.update_timeline_views(play_all)

    def _refresh_region_3_labels(self):
        self.presenter.refresh_region_3_labels()

    def _refresh_region_5(self):
        self.presenter.refresh_region_5()

    def _update_status_bar(self):
        self.presenter.update_status_bar()

    def _on_region_3_selection_changed(self):
        self.presenter.on_region_3_selection_changed()

    def _on_region_2_filter_changed(self, active_voice_tuples: set):
        self.presenter.on_region_2_filter_changed(active_voice_tuples)

    # --- persistence (delegators) -------------------------------------

    def _save_current_score_config(self):
        self.persistence.save_current()

    def _open_score_config_folder(self):
        self.persistence.open_config_folder()

    def _clear_preferences_action_text(self) -> str:
        return self.persistence.clear_action_text()

    def _refresh_clear_preferences_action(self):
        self.persistence.refresh_clear_action()

    def _clear_current_score_preferences(self):
        self.persistence.clear_current()

    # --- dialects ------------------------------------------------------

    def _select_uk_terms(self, checked: bool = False):
        self.set_uk_terms(True)

    def _select_us_terms(self, checked: bool = False):
        self.set_uk_terms(False)

    def set_uk_terms(self, uk_terms: bool):
        """Options > Terminology Language. Unlike toggle_metronome this must
        work with no score loaded - it is a global preference - and is
        persisted immediately rather than batched to closeEvent, so it
        survives a crash. Refreshes everything the vocabulary touches:
        Region 1, Regions 3/4 (via the lightweight label refresh, so no
        re-audition or lost selection) and the status bar."""
        self.session.set_uk_terms(uk_terms)
        app_settings.save(AppSettings(uk_terms=uk_terms))
        self.uk_language_action.setChecked(uk_terms)
        self.us_language_action.setChecked(not uk_terms)
        self.goto_measure_action.setText(goto_measure_action_text(uk_terms))
        if not self._music_data:
            return
        self.presenter.refresh_region_1()
        self.presenter.refresh_region_3_labels()
        self.presenter.update_status_bar()

    # --- dialogs -------------------------------------------------------

    def _show_goto_measure_dialog(self):
        current_measure = None
        if self._music_data:
            current_slice = self._music_data.get_current_slice()
            if current_slice:
                current_measure = current_slice.measure
        dialog = GotoMeasureDialog(
            self, current_measure=current_measure,
            word=bar_word(self._uk_terms).capitalize(),
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            measure_number = dialog.measure_number()
            if measure_number is not None:
                self.navigate_to_typed_measure(str(measure_number))
                self.region_3.setFocus()

    def _show_tempo_offset_dialog(self):
        """Unlike GotoMeasureDialog there's no obvious "next place" for
        focus after a tempo change, so it returns to wherever it was."""
        previous_focus = self.focusWidget()
        current_offset = self._music_data.playback_tempo_offset if self._music_data else 0.0
        beat_unit_name = (
            self._music_data.tempo_beat_unit_name_at() if self._music_data else "quarter"
        )
        dialog = TempoOffsetDialog(
            self, current_offset=current_offset, beat_unit_name=beat_unit_name
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and self._music_data:
            offset = dialog.tempo_offset()
            if offset is not None:
                self.playback.set_tempo_offset(offset)
        if previous_focus is not None:
            previous_focus.setFocus()

    def _show_performance_report_dialog(self):
        """Ref 29: read-only, no live signal wiring - build from current
        data, exec, restore previous focus."""
        if not self._music_data:
            return
        previous_focus = self.focusWidget()
        dialog = PerformanceReportDialog(
            self, lines=self._music_data.get_performance_report_lines()
        )
        dialog.exec()
        if previous_focus is not None:
            previous_focus.setFocus()

    def _show_about_dialog(self):
        AboutDialog(self).exec()

    def _show_user_guide(self):
        guide_path = user_guide_html_path()
        if not os.path.exists(guide_path):
            # I1 (accessible error dialog) is still open - print-based error
            # handling matches every other failure path in this codebase.
            print(f"[ERROR] User guide not found at {guide_path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(guide_path))

    # --- teardown -------------------------------------------------------

    def _disconnect_focus_tracking(self):
        self.focus.disconnect_tracking()

    def closeEvent(self, event):
        self._save_current_score_config()
        self.focus.disconnect_tracking()
        self.session.wait_for_load()
        if self.playback.sequencer is not None:
            self.playback.sequencer.stop()
        self.synth.close()
        super().closeEvent(event)
