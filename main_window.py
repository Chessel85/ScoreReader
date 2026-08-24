# main_window.py
import os
import sys
from typing import Optional

from PySide6.QtCore import QLocale, QUrl, Qt
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QGridLayout,
    QMainWindow,
    QWidget,
)

from audio.synth_engine import SynthEngine
from controllers.attribute_controller import AttributeController
from controllers.focus_controller import FocusController
from controllers.live_midi_input_controller import LiveMidiInputController
from controllers.navigation_controller import NavigationController
from controllers.playback_controller import PlaybackController
from controllers.region_presenter import RegionPresenter
from controllers.score_persistence import ScorePersistenceController
from controllers.score_session import ScoreSession
from controllers.voice_control_controller import VoiceControlController
from models.vocabulary import bar_word
from parsers.ug_source import write_ug_source
from persistence import app_settings
from widgets.about_dialog import AboutDialog
from widgets.attribute_order_dialog import AttributeOrderDialog
from widgets.find_dialog import FindDialog
from widgets.goto_measure_dialog import GotoMeasureDialog
from widgets.instrument_dialog import InstrumentDialog
from widgets.key_signature_dialog import KeySignatureDialog
from widgets.live_midi_input_dialog import LiveMidiInputDialog
from widgets.menu_builder import MenuBuilder, goto_measure_action_text
from widgets.mixer_dialog import MixerDialog
from widgets.part_order_dialog import PartOrderDialog
from widgets.performance_report_dialog import PerformanceReportDialog
from widgets.preview_settings_dialog import PreviewSettingsDialog
from widgets.region1_list_widget import Region1ListWidget
from widgets.region2_list_widget import Region2ListWidget
from widgets.region2_manager import node_breadcrumb
from widgets.region4_list_widget import Region4ListWidget
from widgets.region5_list_widget import Region5ListWidget
from widgets.status_bar_widget import StatusBarWidget
from widgets.tempo_offset_dialog import TempoOffsetDialog
from widgets.timeline_list_widget import TimelineListWidget
from widgets.ultimate_guitar_import_dialog import UltimateGuitarImportDialog
from widgets.voice_control_dialog import VoiceControlDialog
from widgets.voice_control_test_dialog import VoiceControlTestDialog


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

    def __init__(
        self, synth=None, uk_terms: bool | None = None, live_midi_manager=None,
        voice_control_manager=None,
    ):
        """Create the main window.

        synth: any object with the SynthEngine interface (play_chord /
        play_notes / stop_all_notes / set_program / close). Tests pass a
        stand-in so no audio device opens and they can assert what would
        have sounded.

        uk_terms: startup dialect override. None resolves to the saved
        AppSettings value, falling back to OS-locale detection when nothing
        has ever been saved. An explicit value skips both and is not
        persisted, so tests are deterministic regardless of the machine.

        live_midi_manager: any object with the MidiInputManager interface
        (set_callback / list_ports / open / close / is_open / device_name).
        Tests pass a NullMidiInputManager stand-in so no real MIDI device is
        touched - same reasoning as synth above.

        voice_control_manager: any object with the VoiceRecognitionManager
        interface (set_callback / set_diagnostic_callback / list_devices /
        start / stop / is_running / rebuild_grammar / set_confidence_
        threshold). Tests pass a NullVoiceRecognizer stand-in so no real
        SAPI COM recognizer is touched - same reasoning as live_midi_manager.
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
        self._live_midi_manager = live_midi_manager
        self._voice_control_manager = voice_control_manager

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
        self.region_1 = Region1ListWidget()
        self.region_1.setFocusPolicy(Qt.FocusPolicy.TabFocus)

        # Region 2: Parts/Staves/Voices hierarchy, navigated Up/Down, O to toggle
        self.region_2 = Region2ListWidget()
        self.region_2.setFocusPolicy(Qt.FocusPolicy.TabFocus)

        # Region 3: Timeline List
        self.region_3 = TimelineListWidget()
        self.region_3.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.region_3.setFocusPolicy(Qt.FocusPolicy.TabFocus)

        # Region 4: note attributes. Region4ListWidget (not the plain
        # Region1ListWidget-shaped base) adds the Ref 15 AC4 context menu
        # for appending/removing an attribute in Region 3's note display.
        self.region_4 = Region4ListWidget()
        self.region_4.setFocusPolicy(Qt.FocusPolicy.TabFocus)

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
        # Space/Ctrl+Space are bound via the Playback menu's play_stop/
        # pause_resume QAction shortcuts instead of a QShortcut here - two
        # bindings for the same key sequence in the same WindowShortcut
        # context would be ambiguous and neither would fire. Same pattern
        # Ctrl+M/Ctrl+P/Ctrl+G/Ctrl+T already use.

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
        # Preview lead-in/length/looping is a global preference (all
        # scores), so it is loaded once here rather than per file load -
        # unlike the mixer, which travels with the score's own config.
        self.playback.set_preview_settings(app_settings.load().preview)
        # Live MIDI input (device/instrument/volume/pan) is likewise global,
        # not per-score - constructed once here, outliving every file load,
        # the same lifetime ScoreSession/SynthEngine already have. .start()
        # auto-connects to the last-used device if enabled and present this
        # session; degrades silently otherwise.
        self.live_midi = LiveMidiInputController(
            self.session.synth, parent=self, midi_manager=self._live_midi_manager,
        )
        self.live_midi.start()
        self.navigation = NavigationController(self.session, parent=self)
        # Hands-free voice control (Ref 19): recognized commands call
        # straight into navigation/playback, so it's constructed once both
        # exist. Global like live_midi above, for the same reasoning -
        # confirmed with the user. .start() auto-starts listening if enabled
        # and pywin32/SAPI are available; degrades silently otherwise.
        self.voice_control = VoiceControlController(
            self.session.synth, self.navigation, self.playback, parent=self,
            voice_manager=self._voice_control_manager,
        )
        self.voice_control.start()
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
        self.play_stop_action = actions.play_stop
        self.pause_resume_action = actions.pause_resume
        self.preview_action = actions.preview
        self.preview_settings_action = actions.preview_settings
        self.mute_action = actions.mute
        self.solo_action = actions.solo
        self.unmute_all_action = actions.unmute_all
        self.unsolo_all_action = actions.unsolo_all
        self.mixer_action = actions.mixer
        self.instruments_action = actions.instruments
        self.key_signature_action = actions.key_signature
        self.first_measure_action = actions.first_measure
        self.last_measure_action = actions.last_measure
        self.goto_measure_action = actions.goto_measure
        self.find_action = actions.find
        self.find_next_action = actions.find_next
        self.find_previous_action = actions.find_previous
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
        self.live_midi_input_action = actions.live_midi_input
        self.live_midi_input_settings_action = actions.live_midi_input_settings
        # Global (AppSettings), not per-score like metronome/position
        # announcer above - set once here, never re-set on score load.
        self.live_midi_input_action.setChecked(self.live_midi.settings.enabled)
        self.voice_control_action = actions.voice_control
        self.voice_control_settings_action = actions.voice_control_settings
        # Global (AppSettings), not per-score - set once here, never re-set
        # on score load, same reasoning as live_midi_input above.
        self.voice_control_action.setChecked(self.voice_control.settings.enabled)
        self.attribute_order_action = actions.attribute_order
        self.user_guide_action = actions.user_guide
        self.about_action = actions.about

        self.persistence.clear_action = actions.clear_preferences
        self.persistence.refresh_clear_action()
        self.focus.first_measure_action = actions.first_measure
        self.focus.last_measure_action = actions.last_measure
        self.focus.update_navigation_actions_enabled()
        self.focus.mute_action = actions.mute
        self.focus.solo_action = actions.solo
        self.focus.unmute_all_action = actions.unmute_all
        self.focus.unsolo_all_action = actions.unsolo_all
        self.focus.update_region2_actions_enabled()

        self.recent_files_menu = actions.recent_files_menu
        self._refresh_recent_files_menu()

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

    def _open_score_file_dialog(self, start_dir: str):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Score",
            start_dir,
            "Score Files (*.xml *.musicxml *.mxl *.mid *.midi *.gp *.ug);;"
            "MusicXML Files (*.xml *.musicxml *.mxl);;"
            "MIDI Files (*.mid *.midi);;"
            "Guitar Pro Files (*.gp);;"
            "Recall Score UG Import Files (*.ug);;"
            "All Files (*)",
        )
        if file_path:
            self.load_score_from_file(file_path)

    def load_score_from_file(self, file_path: str):
        if self.session.is_loading():
            return
        self._save_current_score_config()
        self.session.load(file_path)

    def open_ultimate_guitar_import_dialog(self):
        """Experimental (feature/ug-import): File > Import from Ultimate
        Guitar... - no self._music_data guard, same as open_file_dialog,
        since this is a loading action that works with no score loaded
        yet."""
        dialog = UltimateGuitarImportDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_ultimate_guitar_url(dialog.url())

    def load_ultimate_guitar_url(self, url: str):
        if self.session.is_loading():
            return
        self._save_current_score_config()
        self.session.import_from_url(url)

    def save_ultimate_guitar_import_as(self):
        """Experimental (feature/ug-import): File > Save Ultimate Guitar
        Import As... - the app's first-ever save capability, deliberately
        scoped to just this one format (MusicXML/MIDI/GP files are already
        real files on disk; there's nothing to "save" there). Always
        prompts for a location rather than a silent-overwrite Save, to keep
        this first save path simple.

        After writing, the score behaves exactly like a file that was
        opened normally: file_path becomes the real saved path, so .rsc
        persistence/the window title/Edit > Open Local Folder all key off
        it the same way every other format already does."""
        if not self._music_data or not self._music_data.is_ug:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Ultimate Guitar Import", "", "Recall Score UG Import Files (*.ug)"
        )
        if not file_path:
            return
        write_ug_source(self._music_data.ug_source, file_path)
        self._music_data.file_path = file_path
        self.setWindowTitle(f"Recall Score - {os.path.basename(file_path)}")
        self.persistence.refresh_clear_action()
        self._save_current_score_config()
        app_settings.add_recent_file(file_path)
        self._refresh_recent_files_menu()

    def _refresh_recent_files_menu(self):
        """Rebuilds File > Recent Files from AppSettings - called on
        startup and again after every successful load/save, since either
        can change the list. A stale entry (moved/deleted since) is not
        specially detected or pruned here - clicking it just fails the same
        way opening any other missing file would, through the existing
        load_failed path."""
        menu = self.recent_files_menu
        menu.clear()
        recent_files = app_settings.load().recent_files
        if not recent_files:
            placeholder = QAction("No recent files", self)
            placeholder.setEnabled(False)
            menu.addAction(placeholder)
            return
        for file_path in recent_files:
            action = QAction(file_path, self)
            action.triggered.connect(lambda checked=False, p=file_path: self.load_score_from_file(p))
            menu.addAction(action)

    def _on_score_loaded(self, music_data):
        """Orchestration only - which is why it stays in the shell. The order
        matters: the saved config has to be applied to MusicData before the
        regions render, and Region 2's own per-node toggles have to be in
        effect before the first audition, or the opening chord includes
        voices the user had switched off."""
        self.setWindowTitle(f"Recall Score - {os.path.basename(music_data.file_path)}")

        # Ref 19: "go to bar N"'s numeric vocabulary is bounded to this
        # score's own real measure numbers - see audio/voice_commands.
        # go_to_bar_phrases. Safe to call regardless of whether voice
        # control is currently enabled/listening - a no-op grammar rebuild
        # request queued for a stopped recognizer is simply picked up by the
        # next start().
        self.voice_control.rebuild_grammar(music_data.total_measures)

        # A URL-imported UG score's file_path is a synthetic slug with
        # nothing on disk at it (see UgReader) - os.path.exists naturally
        # excludes that case without needing to special-case is_ug here.
        if os.path.exists(music_data.file_path):
            app_settings.add_recent_file(music_data.file_path)
            self._refresh_recent_files_menu()

        saved_config = self.persistence.load_for_current()
        if saved_config is not None:
            music_data.apply_config(saved_config)
        self.persistence.refresh_clear_action()

        self.presenter.reset_performance_labels()
        self.playback.attach_score(music_data)

        # Suppress the initial audition when there's a config to restore,
        # and fire it once Region 2's restored state is actually in effect -
        # otherwise the first sound heard on load includes voices that were
        # saved as off, even though every later move excludes them.
        self._update_ui_regions(play_all=saved_config is None)
        if saved_config is not None:
            self.region_2.apply_muted_node_keys(
                saved_config.parts_muted, saved_config.staves_muted, saved_config.voices_muted
            )
            self.region_2.apply_soloed_node_keys(
                saved_config.parts_soloed, saved_config.staves_soloed, saved_config.voices_soloed
            )
            self._audition_current_selection()

    def _on_score_load_failed(self, error_text: str):
        print(f"[ERROR] Failed to load score file:\n{error_text}")

    def _update_ui_regions(self, play_all: bool = True):
        if not self._music_data:
            return
        self.presenter.refresh_region_1()
        self.region_2.load_score_structure(
            self._music_data.get_score_structure(),
            collapse_to_parts=self._music_data.collapsed_part_ids,
        )
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

    def find_next(self):
        self.navigation.find_next()

    def find_previous(self):
        self.navigation.find_previous()

    # --- playback (delegators) ----------------------------------------

    def toggle_play_stop(self):
        self.playback.toggle_play_stop()

    def toggle_pause_resume(self):
        self.playback.toggle_pause_resume()

    def audition_phrase(self):
        self.playback.audition_phrase()

    def increase_preview_bars(self):
        """Alt+PageUp in the Note region. Persisted globally right away,
        like Preview Settings' own OK - a bar count set this way is the
        same practice habit, not a per-score value."""
        self.playback.adjust_preview_bars(1)
        app_settings.set_preview_settings(self.playback.preview_settings)

    def decrease_preview_bars(self):
        """Alt+PageDown counterpart of increase_preview_bars."""
        self.playback.adjust_preview_bars(-1)
        app_settings.set_preview_settings(self.playback.preview_settings)

    def toggle_mute_current_region2_row(self):
        self.region_2.toggle_mute_current()

    def toggle_solo_current_region2_row(self):
        self.region_2.toggle_solo_current()

    def unmute_all_region2(self):
        self.region_2.unmute_all()

    def unsolo_all_region2(self):
        self.region_2.unsolo_all()

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

    def toggle_live_midi_input(self):
        self.live_midi_input_action.setChecked(self.live_midi.toggle_enabled())

    def toggle_voice_control(self):
        self.voice_control_action.setChecked(self.voice_control.toggle_enabled())

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

    def show_region_4_attribute_menu(self, row: int, global_pos):
        self.attributes.show_menu(row, global_pos)

    def _region_4_attribute_menu_actions(self, row: int) -> list:
        return self.attributes.menu_actions(row)

    def _build_region_4_attribute_menu(self, row: int):
        return self.attributes.build_menu(row)

    def _restore_region_4_focus_after_menu(self, row: int):
        self.attributes.restore_focus_after_menu(row)

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
        dialog.add_remove_requested.connect(
            lambda attribute_key: self.attributes.show_order_menu(dialog, node, attribute_key)
        )
        dialog.exec()
        self.region_2.setFocus()

    def _show_part_order_dialog(self):
        """Reported: NVDA reads whichever part's row Region 3 lands on
        first (always row 0 - see RegionPresenter.update_timeline_views's
        setCurrentRow(0, NoUpdate)) after every navigation step. This lets
        the user choose that order directly - most relevant for a UG
        import's Chords/Lyrics parts, but works for any multi-part score.

        Applying goes through MusicData.reorder_parts (the note-order
        half) and Region2ListWidget.reorder_parts (the Region 2 row-order
        half, an in-place reorder - NOT load_score_structure, which would
        reset every on/off toggle back to enabled)."""
        if not self._music_data:
            return
        previous_focus = self.focusWidget()
        parts = [(p.part_id, p.name) for p in self._music_data.parts_info]
        dialog = PartOrderDialog(self, parts=parts)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_order = dialog.part_order()
            if new_order != [p.part_id for p in self._music_data.parts_info]:
                self._music_data.reorder_parts(new_order)
                self.region_2.reorder_parts(new_order)
                self.presenter.update_timeline_views(play_all=False)
        if previous_focus is not None:
            previous_focus.setFocus()

    # --- presentation (delegators) ------------------------------------

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
        # load-mutate-save, not a fresh AppSettings(uk_terms=uk_terms) -
        # the latter would silently wipe recent_files back to empty on
        # every terminology toggle.
        settings = app_settings.load()
        settings.uk_terms = uk_terms
        app_settings.save(settings)
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

    def _show_find_dialog(self):
        """Navigation > Find... (Ctrl+F). OK arms the selected FindTarget
        and performs the initial jump in one step (NavigationController.
        find_next from wherever the cursor already is); Alt+Right/Alt+Left
        then cycle further occurrences without reopening this dialog."""
        if not self._music_data:
            return
        dialog = FindDialog(self, targets=self._music_data.available_find_targets())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            target = dialog.selected_target()
            if target is not None:
                self.navigation.arm_find_target(target)
                self.find_next()
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

    def _show_preview_settings_dialog(self):
        """Playback > Preview Settings... (Ctrl+Shift+V) - the count-in
        before Preview starts, how many bars it runs, and whether it loops.

        Saved GLOBALLY (app_settings, like the UK/US dialect) rather than
        per score, the user's own decision: a lead-in length is a practice
        habit, not a property of one piece. Pushed to the controller as
        well as saved, so it applies to the very next Enter without a
        reload."""
        previous_focus = self.focusWidget()
        dialog = PreviewSettingsDialog(
            self, settings=self.playback.preview_settings, uk_terms=self._uk_terms
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            settings = dialog.preview_settings()
            self.playback.set_preview_settings(settings)
            app_settings.set_preview_settings(settings)
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

    def _show_mixer_dialog(self):
        """Wishlist #4. rows/commit/cancel all live on PlaybackController -
        this dialog is a pure view (see widgets/mixer_dialog.py's own
        docstring), so the only thing this method does is wire its signals
        and decide commit vs. revert from exec()'s result."""
        if not self._music_data:
            return
        previous_focus = self.focusWidget()
        dialog = MixerDialog(self, rows=self.playback.begin_mixer_edit())
        dialog.volume_changed.connect(self.playback.set_mixer_volume)
        dialog.pan_changed.connect(self.playback.set_mixer_pan)
        dialog.preview_requested.connect(self.playback.audition_phrase)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.playback.commit_mixer_edit()
        else:
            self.playback.cancel_mixer_edit()
        # is_preview_active as well as is_playing: the dialog's own Preview
        # button (Alt+W) can leave a count-in or a loop running, neither of
        # which the Sequencer's own flags can see.
        if self.playback.is_preview_active or (
            self.sequencer is not None and (self.sequencer.is_playing or self.sequencer.is_paused)
        ):
            self.playback.stop()
        if previous_focus is not None:
            previous_focus.setFocus()

    def _show_live_midi_input_dialog(self):
        """Options > Live MIDI Input Settings... (Ctrl+Shift+L). Pure view
        (see widgets/live_midi_input_dialog.py's own docstring) - this
        method wires its signals and decides commit vs. revert from exec()'s
        result, the same shape _show_mixer_dialog already has. Unlike the
        Mixer dialog, this needs no loaded score at all - the feature is
        global, not per-score."""
        previous_focus = self.focusWidget()
        dialog = LiveMidiInputDialog(
            self,
            devices=self.live_midi.available_devices(),
            settings=self.live_midi.begin_settings_edit(),
        )
        dialog.instrument_changed.connect(self.live_midi.preview_instrument)
        dialog.volume_changed.connect(self.live_midi.preview_volume)
        dialog.pan_changed.connect(self.live_midi.preview_pan)
        dialog.refresh_requested.connect(
            lambda: dialog.set_devices(self.live_midi.available_devices())
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.live_midi.commit_settings_edit(dialog.result_settings())
        else:
            self.live_midi.cancel_settings_edit()
        self.live_midi_input_action.setChecked(self.live_midi.settings.enabled)
        if previous_focus is not None:
            previous_focus.setFocus()

    def _show_voice_control_dialog(self):
        """Options > Voice Control Settings... (Ref 19). Pure view (see
        widgets/voice_control_dialog.py's own docstring) - this method wires
        its signals and decides commit vs. revert from exec()'s result, the
        same shape _show_live_midi_input_dialog already has. Needs no loaded
        score at all - the feature is global, not per-score."""
        previous_focus = self.focusWidget()
        dialog = VoiceControlDialog(
            self,
            devices=self.voice_control.available_devices(),
            settings=self.voice_control.begin_settings_edit(),
        )
        dialog.refresh_requested.connect(
            lambda: dialog.set_devices(self.voice_control.available_devices())
        )
        dialog.test_requested.connect(self._show_voice_control_test_dialog)
        dialog.cue_volume_changed.connect(self.voice_control.preview_cue_volume)
        dialog.cue_pan_changed.connect(self.voice_control.preview_cue_pan)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.voice_control.commit_settings_edit(dialog.result_settings())
        else:
            self.voice_control.cancel_settings_edit()
        self.voice_control_action.setChecked(self.voice_control.settings.enabled)
        if previous_focus is not None:
            previous_focus.setFocus()

    def _show_voice_control_test_dialog(self, device_name: str, confidence_threshold: float):
        """Voice Control Settings' Test... button. Pauses the real listening
        session for the duration - VoiceControlTestDialog runs its own
        isolated recognizer, and two in-process SAPI recognizers competing
        for the same microphone at once is untested and best avoided."""
        was_listening = self.voice_control.is_listening()
        if was_listening:
            self.voice_control.stop_listening()
        dialog = VoiceControlTestDialog(
            self, device_name=device_name, confidence_threshold=confidence_threshold,
        )
        dialog.exec()
        if was_listening:
            self.voice_control.resume_listening()

    def _show_instrument_dialog(self):
        """S5: rename a part and/or change its playback instrument, for
        both MusicXML and MIDI scores - "piano may not always be a suitable
        default", and some MIDI files carry no track names at all
        (BluePeter.mid).

        Applying goes through MusicData.apply_part_overrides, which also
        keeps NoteData.part_name in sync - Region 2's part row is updated
        in place (rename_part, never a full load_score_structure rebuild,
        which would reset every on/off toggle back to enabled) and Region
        3/4/5 through the normal update_timeline_views refresh, same as any
        other display-only change.

        Wishlist #8 follow-up: a percussion part also contributes one
        dialog row per distinct item it carries (MusicData.
        get_percussion_items_for_part). Applying those goes through the new
        MusicData.apply_percussion_overrides, which also recomputes the
        affected voices' labels (part.voice_names) - Region 2 is told about
        each one via region_2.rename_voice (mirrors rename_part: an
        in-place label update, never a load_score_structure rebuild, which
        would reset every mute/solo toggle and expand state)."""
        if not self._music_data:
            return
        previous_focus = self.focusWidget()
        rows = [
            (p.part_id, p.name, p.gmidi_program) for p in self._music_data.parts_info
        ]
        percussion_part_ids = [p.part_id for p in self._music_data.parts_info if p.is_percussion]
        percussion_rows = {
            part_id: self._music_data.get_percussion_items_for_part(part_id)
            for part_id in percussion_part_ids
        }
        dialog = InstrumentDialog(
            self,
            rows=rows,
            percussion_part_ids=percussion_part_ids,
            percussion_rows=percussion_rows,
            auto_correct_enabled=self._music_data.percussion_auto_correct_enabled,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            (
                name_overrides,
                program_overrides,
                item_name_overrides,
                item_sound_overrides,
                auto_correct_enabled,
            ) = dialog.overrides()
            percussion_changed = (
                item_name_overrides
                or item_sound_overrides
                or auto_correct_enabled != self._music_data.percussion_auto_correct_enabled
            )
            if name_overrides or program_overrides:
                self._music_data.apply_part_overrides(name_overrides, program_overrides)
                for part_id, name in name_overrides.items():
                    self.region_2.rename_part(part_id, name)
            if percussion_changed:
                self._music_data.percussion_item_name_overrides.update(item_name_overrides)
                self._music_data.percussion_item_overrides.update(item_sound_overrides)
                self._music_data.percussion_auto_correct_enabled = auto_correct_enabled
                self._music_data.apply_percussion_overrides()
                for part in self._music_data.parts_info:
                    if not part.is_percussion:
                        continue
                    for (staff_id, voice_id), label in part.voice_names.items():
                        self.region_2.rename_voice(part.part_id, staff_id, voice_id, label)
            if name_overrides or program_overrides or percussion_changed:
                self.presenter.update_timeline_views(play_all=False)
        if previous_focus is not None:
            previous_focus.setFocus()

    def _show_key_signature_dialog(self):
        """S6: a single whole-piece key signature override, for MIDI files
        that lack correct (or any) key metadata - its own dialog, not
        folded into Instruments above (see widgets/key_signature_dialog.py's
        own docstring for why).

        Applying goes through MusicData.apply_key_signature_override, which
        re-spells MIDI notes in place - update_timeline_views picks that up
        for Region 3/4, and Region 1's credits / the status bar's key field
        need their own direct refresh since neither is part of that
        refresh's normal scope."""
        if not self._music_data:
            return
        previous_focus = self.focusWidget()
        current_key = (
            self._music_data.key_signature_override_fifths,
            self._music_data.key_signature_override_mode,
        )
        dialog = KeySignatureDialog(self, current_key=current_key)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            key_fifths, key_mode = dialog.key_override()
            if (key_fifths, key_mode) != current_key:
                self._music_data.apply_key_signature_override(key_fifths, key_mode)
                self.presenter.update_timeline_views(play_all=False)
                self.presenter.refresh_region_1()
                self.presenter.update_status_bar()
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
        # Directly, not via playback.stop(), for the same reason the
        # Sequencer is stopped directly below: no signals into regions that
        # are being torn down.
        self.playback.cancel_preview()
        if self.playback.sequencer is not None:
            self.playback.sequencer.stop()
        # Before synth.close(): needs self._fs still alive to send the real
        # note-offs for any note still physically held on a live-input
        # device.
        self.live_midi.close()
        self.voice_control.close()
        self.synth.close()
        super().closeEvent(event)
