# widgets/menu_builder.py
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import QMenu

from models.vocabulary import bar_word


@dataclass
class Actions:
    """Every QAction the menus own, handed back for the window to keep.

    Held as attributes rather than locals because PySide can garbage-collect
    the Python wrapper for a QAction while the C++ object is still alive and
    parented, leaving "Internal C++ object already deleted" for anything
    later reaching it via menuBar().actions().
    """

    open: Optional[QAction] = None
    recent_files_menu: Optional[QMenu] = None
    import_from_ultimate_guitar: Optional[QAction] = None
    save_ug_import: Optional[QAction] = None
    close: Optional[QAction] = None
    exit: Optional[QAction] = None
    open_folder: Optional[QAction] = None
    clear_preferences: Optional[QAction] = None
    performance_report: Optional[QAction] = None
    instruments: Optional[QAction] = None
    key_signature: Optional[QAction] = None
    select_all: Optional[QAction] = None
    first_measure: Optional[QAction] = None
    last_measure: Optional[QAction] = None
    goto_measure: Optional[QAction] = None
    find: Optional[QAction] = None
    find_next: Optional[QAction] = None
    find_previous: Optional[QAction] = None
    move_to_metadata: Optional[QAction] = None
    move_to_parts: Optional[QAction] = None
    move_to_notes: Optional[QAction] = None
    move_to_attributes: Optional[QAction] = None
    move_to_performance: Optional[QAction] = None
    play_stop: Optional[QAction] = None
    pause_resume: Optional[QAction] = None
    play_metronome: Optional[QAction] = None
    commit_digits: Optional[QAction] = None
    play_settings: Optional[QAction] = None
    loop_toggle: Optional[QAction] = None
    lead_in_toggle: Optional[QAction] = None
    mute: Optional[QAction] = None
    solo: Optional[QAction] = None
    unmute_all: Optional[QAction] = None
    unsolo_all: Optional[QAction] = None
    mixer: Optional[QAction] = None
    part_order: Optional[QAction] = None
    uk_language: Optional[QAction] = None
    us_language: Optional[QAction] = None
    terminology_group: Optional[QActionGroup] = None
    metronome: Optional[QAction] = None
    position_announcer: Optional[QAction] = None
    live_midi_input: Optional[QAction] = None
    live_midi_input_settings: Optional[QAction] = None
    voice_control: Optional[QAction] = None
    voice_control_settings: Optional[QAction] = None
    attribute_order: Optional[QAction] = None
    tuner: Optional[QAction] = None
    user_guide: Optional[QAction] = None
    about: Optional[QAction] = None


def goto_measure_action_text(uk_terms: bool) -> str:
    return f"&Go to {bar_word(uk_terms).capitalize()}..."


class MenuBuilder:
    """Builds the menu bar and returns its actions.

    `slots` is any object exposing the callbacks below - MainWindow, whose
    delegating methods are the stable names the widgets and tests already
    use. Keeping construction here means adding a menu item is a change to
    one file rather than to the window class.
    """

    def __init__(self, window, slots, uk_terms: bool):
        self.window = window
        self.slots = slots
        self.uk_terms = uk_terms

    def build(self) -> Actions:
        a = Actions()
        menu_bar = self.window.menuBar()
        self._file_menu(menu_bar, a)
        self._edit_menu(menu_bar, a)
        self._navigation_menu(menu_bar, a)
        self._playback_menu(menu_bar, a)
        self._options_menu(menu_bar, a)
        self._tools_menu(menu_bar, a)
        self._help_menu(menu_bar, a)
        return a

    def _action(self, text: str, slot, shortcut=None, status_tip=None,
                checkable: bool = False) -> QAction:
        action = QAction(text, self.window)
        if shortcut is not None:
            action.setShortcut(shortcut)
        if status_tip is not None:
            action.setStatusTip(status_tip)
        if checkable:
            action.setCheckable(True)
        action.triggered.connect(slot)
        return action

    def _file_menu(self, menu_bar, a: Actions) -> None:
        file_menu = menu_bar.addMenu("&File")
        a.open = self._action(
            "&Open...", self.slots.open_file_dialog,
            QKeySequence.Open, "Open a MusicXML file",
        )
        # Populated dynamically by main_window.py's
        # _refresh_recent_files_menu (on startup and after every load/save)
        # - not a static QAction like the rest of this menu, since the item
        # count/text changes over time. Built empty here (bare constructor,
        # not file_menu.addMenu(title) - that inserts immediately, which
        # would place it before &Open below); actually added to file_menu
        # in the addAction block, in the position it belongs.
        a.recent_files_menu = QMenu("&Recent Files", self.window)
        # Experimental (feature/ug-import): chords + lyrics from an
        # Ultimate Guitar chord-tab page - no natural OS-standard/single-
        # letter binding and infrequent, so no shortcut, just a status tip.
        a.import_from_ultimate_guitar = self._action(
            "Import from &Ultimate Guitar...", self.slots.open_ultimate_guitar_import_dialog,
            status_tip="Import chords and lyrics from an Ultimate Guitar tab page",
        )
        # Same "infrequent, no natural OS-standard/single-letter binding"
        # reasoning as Import above - no shortcut, just a status tip. Only
        # meaningful for a currently-loaded UG import; silently no-ops
        # otherwise, same guard style every other MusicData-dependent
        # dialog already uses (main_window.py's save_ultimate_guitar_import_as).
        a.save_ug_import = self._action(
            "Save Ultimate Guitar Import &As...", self.slots.save_ultimate_guitar_import_as,
            status_tip="Save the current Ultimate Guitar import to a file",
        )
        # Close the loaded score (commit its .rsc, blank the window back to
        # first-run) without quitting the app. No mnemonic - it carries the
        # OS-standard Ctrl+W, so an Alt-only access key would only be one
        # more thing for NVDA to announce as a pseudo-shortcut (the same
        # reasoning as Reorder Attributes/Parts etc.), and "C"/"l"/"o" all
        # already collide with siblings in this menu. Disabled until a
        # score is loaded (main_window.py keeps it in sync, like Clear
        # Preferences).
        a.close = self._action(
            "Close", self.slots.close_score, QKeySequence.Close,
            status_tip="Close the current score and save its preferences",
        )
        a.close.setEnabled(False)

        a.exit = self._action("E&xit", self.window.close, QKeySequence.Quit)

        # Moved here from Edit (user-requested review, 2026-08-26): these are
        # file-level housekeeping (where a file's saved settings live, and
        # clearing them), not score-editing actions like Find/Instruments/Key
        # Signature, which stayed in Edit. Mnemonic on &Local, not &Folder -
        # &Folder would repeat this menu's own &File mnemonic.
        a.open_folder = self._action(
            "Open &Local Folder", self.slots._open_score_config_folder,
            status_tip="Open the folder where saved preferences are stored",
        )
        a.clear_preferences = self._action(
            self.slots._clear_preferences_action_text(),
            self.slots._clear_current_score_preferences,
        )

        file_menu.addAction(a.open)
        file_menu.addMenu(a.recent_files_menu)
        file_menu.addAction(a.import_from_ultimate_guitar)
        file_menu.addAction(a.save_ug_import)
        file_menu.addAction(a.close)
        file_menu.addSeparator()
        file_menu.addAction(a.open_folder)
        file_menu.addAction(a.clear_preferences)
        file_menu.addSeparator()
        file_menu.addAction(a.exit)

    def _edit_menu(self, menu_bar, a: Actions) -> None:
        edit_menu = menu_bar.addMenu("&Edit")

        # Ref 6/13: makes the existing Ctrl+A behaviour discoverable and
        # gives it a real, greyable QAction - previously a bare QShortcut
        # with no menu presence at all. Deliberately only enabled with the
        # Note region focused (FocusController.update_navigation_actions_
        # enabled, same "greyed out elsewhere" treatment as Move to First/
        # Last Note): selecting every note at the cursor is what makes
        # Shift+Space's "play them all together" audition meaningful, and
        # it has no sensible target from any other region.
        a.select_all = self._action(
            "Select &All", self.slots.select_all_region_3, QKeySequence("Ctrl+A"),
            status_tip="Select every note at the current position, so Shift+Space plays them all together",
        )
        edit_menu.addAction(a.select_all)

        # S5: per-part display-name/instrument override, for both MusicXML
        # and MIDI scores.
        a.instruments = self._action(
            "&Instruments...", self.slots._show_instrument_dialog, "Ctrl+Shift+I",
            status_tip="Rename a part or change what instrument it plays back as",
        )
        edit_menu.addAction(a.instruments)

        # S6: a single whole-piece key signature override, for both
        # MusicXML and MIDI scores. Its own dialog, not folded into
        # Instruments above - the user found the two too different a pair
        # of actions to share one dialog.
        a.key_signature = self._action(
            "&Key Signature...", self.slots._show_key_signature_dialog, "Ctrl+Shift+K",
            status_tip="Override the score's key signature",
        )
        edit_menu.addAction(a.key_signature)

    def _navigation_menu(self, menu_bar, a: Actions) -> None:
        # Navigation duplicates, as menu items, the keyboard-only ways of
        # reaching the start, end or a given measure - for anyone who
        # prefers a menu to typing into the Note region.
        navigation_menu = menu_bar.addMenu("&Navigation")

        # Move to First/Last Note are greyed out unless the Note region has
        # focus (kept in sync by FocusController), since otherwise Home/End
        # silently move the timeline underneath whatever the user is
        # actually reading. The Move to <region> items are the exception -
        # staying enabled everywhere is their whole job.
        a.first_measure = self._action(
            "Move to &First Note", self.slots._navigation_menu_first_measure,
            QKeySequence(Qt.Key.Key_Home),
        )
        a.last_measure = self._action(
            "Move to &Last Note", self.slots._navigation_menu_last_measure,
            QKeySequence(Qt.Key.Key_End),
        )
        a.goto_measure = self._action(
            goto_measure_action_text(self.uk_terms),
            self.slots._show_goto_measure_dialog, QKeySequence("Ctrl+G"),
        )
        # Find (attributes like "articulation"/"string", and performance
        # markings like repeat/ending/hairpin/Segno/Coda/D.C./D.S./key/
        # time-sig/tempo changes): pick a target, jump to occurrences of it.
        # Lives ONLY here, right before Find Next/Previous - moved out of
        # Edit in this review (user-requested 2026-08-26: "weird having
        # find in the edit menu and the find prev and find next in
        # navigation"). This also fixes a real bug: the same QAction added
        # to TWO different QMenus (its old home in Edit, plus here) left
        # NVDA silently announcing nothing at all when arrowed onto in
        # whichever menu built second - Qt's accessibility bridge doesn't
        # reliably expose one QAction's name across two separate QMenu
        # parents. A QAction now has exactly one menu home.
        a.find = self._action(
            "Fin&d...", self.slots._show_find_dialog, QKeySequence("Ctrl+F"),
        )

        # Find Next/Previous: once a target is armed, Alt+Right/Alt+Left
        # (global - work regardless of which region has focus, like the
        # tempo F/S/D shortcuts) cycle further occurrences without
        # reopening the dialog. Alt+Page Up/Down was ruled out - already
        # bound to the Note region's preview-length adjustment. Mnemonic
        # on N&ext, not &Next - &Next would repeat this menu's own
        # &Navigation mnemonic (the same class of bug once reported for
        # Tools > &Tuner, both T). Not &X either ("Find Ne&xt") - X
        # already belongs to Move to Parts List below in this same menu.
        a.find_next = self._action(
            "Find N&ext", self.slots.find_next, QKeySequence("Alt+Right"),
        )
        a.find_previous = self._action(
            "Find Previo&us", self.slots.find_previous, QKeySequence("Alt+Left"),
        )
        # A direct-jump shortcut per region. Z/X/C/V/B (user-requested
        # 2026-08-22, replacing the old scattered I/V/N/A/P): the five keys
        # sit together on the keyboard's bottom row, left-to-right in the
        # same order as the five regions, so they're easy to find by feel -
        # still no collision with the existing bare F/S/D tempo shortcuts.
        a.move_to_metadata = self._action(
            "Move to Info (&Z)", self.slots._navigation_menu_move_to_metadata,
            QKeySequence("Z"),
        )
        a.move_to_parts = self._action(
            "Move to Parts List (&X)", self.slots._navigation_menu_move_to_parts,
            QKeySequence("X"),
        )
        a.move_to_notes = self._action(
            "Move to Notes (&C)", self.slots._navigation_menu_move_to_notes,
            QKeySequence("C"),
        )
        a.move_to_attributes = self._action(
            "Move to Attributes (&V)", self.slots._navigation_menu_move_to_attributes,
            QKeySequence("V"),
        )
        a.move_to_performance = self._action(
            "Move to Performance (&B)", self.slots._navigation_menu_move_to_performance,
            QKeySequence("B"),
        )

        navigation_menu.addAction(a.first_measure)
        navigation_menu.addAction(a.last_measure)
        navigation_menu.addSeparator()
        navigation_menu.addAction(a.goto_measure)
        navigation_menu.addSeparator()
        navigation_menu.addAction(a.find)
        navigation_menu.addAction(a.find_next)
        navigation_menu.addAction(a.find_previous)
        navigation_menu.addSeparator()
        navigation_menu.addAction(a.move_to_metadata)
        navigation_menu.addAction(a.move_to_parts)
        navigation_menu.addAction(a.move_to_notes)
        navigation_menu.addAction(a.move_to_attributes)
        navigation_menu.addAction(a.move_to_performance)

    def _playback_menu(self, menu_bar, a: Actions) -> None:
        """The existing transport controls plus mute/solo and Mixer, all in
        one menu - Play/Stop and Pause use a QAction carrying the shortcut
        instead of a bare QShortcut in main_window.py (same pattern
        Ctrl+M/Ctrl+P/Ctrl+G/Ctrl+T already use), so Space/Ctrl+Space show
        up here too.

        Mute/Solo/Unmute All/Unsolo All act on Region 2's focused row -
        FocusController greys all four out unless Region 2 has focus, the
        same "only meaningful with a particular region focused" pattern
        already used for Move to First/Last Note.
        """
        playback_menu = menu_bar.addMenu("&Playback")

        # Mnemonic on St&op, not &Play/Stop - the latter would repeat this
        # menu's own &Playback mnemonic (the same class of bug once reported
        # for Tools > &Tuner, both T).
        a.play_stop = self._action(
            "Play/St&op", self.slots.toggle_play_stop, QKeySequence(Qt.Key.Key_Space),
        )
        playback_menu.addAction(a.play_stop)

        # Text shortened from "Pause/Resume" to plain "Pause" (user-requested
        # 2026-08-26): Ctrl+Space only ever pauses - resuming is Space, the
        # same key Play/Stop already uses - so "Resume" in this item's own
        # name was misleading about what THIS shortcut does.
        a.pause_resume = self._action(
            "Pa&use", self.slots.toggle_pause_resume, QKeySequence("Ctrl+Space"),
        )
        playback_menu.addAction(a.pause_resume)

        # A free-running click track for playing along by ear - sounds at
        # the current playback tempo, does not move the timeline, and is
        # separate from Toggle Metronome (which only clicks as the cursor
        # steps through real playback). Not checkable, matching Play/Stop
        # above - it is a start/stop action, not a persistent state. No "&"
        # mnemonic: it carries a real shortcut, and an Alt-only mnemonic
        # would just be one more thing NVDA announces as a pseudo-shortcut
        # (same reasoning as Reorder Attributes/Parts). Ctrl+Alt+Space, not
        # a bare Alt+Space - the Windows window menu grabs Alt+Space before
        # Qt sees it.
        a.play_metronome = self._action(
            "Play Metronome", self.slots.toggle_play_metronome,
            QKeySequence("Ctrl+Alt+Space"),
            status_tip="Play a free-running metronome click at the current tempo, without moving the timeline",
        )
        playback_menu.addAction(a.play_metronome)

        # Enter/Return only ever commits a typed bar number now (Preview is
        # gone - Space is the single play control). Kept as a hidden
        # window action, NOT a visible menu item, purely so the global
        # Enter/Return shortcut still fires; its slot
        # (MainWindow.audition_phrase) is now just
        # NavigationController.commit_pending_digits(). Two shortcuts, not
        # one - the numpad-Enter-vs-main-Return distinction documented for
        # Voice Control.
        a.commit_digits = self._action(
            "Commit Typed Bar Number", self.slots.audition_phrase,
            status_tip="Completes a typed bar number, if one is pending",
        )
        a.commit_digits.setShortcuts([
            QKeySequence(Qt.Key.Key_Enter), QKeySequence(Qt.Key.Key_Return),
        ])
        self.window.addAction(a.commit_digits)

        # Mnemonic on T: O, u, M, S, A and l are already taken in this menu.
        # Ctrl+Shift+V alongside the other dialogs' Ctrl+Shift+I/K/X, plus
        # Ctrl+T (which the old Tempo Offset... dialog used to carry - this
        # dialog now owns the absolute playback tempo too).
        a.play_settings = self._action(
            "Play Se&ttings...", self.slots._show_play_settings_dialog,
            status_tip="Set the playback tempo, lead-in and looping",
        )
        a.play_settings.setShortcuts([
            QKeySequence("Ctrl+Shift+V"), QKeySequence("Ctrl+T"),
        ])
        playback_menu.addAction(a.play_settings)

        # Quick toggles for the two play-session habits, checkable so a
        # screen reader announces their state on focus (pattern like Toggle
        # Metronome). Ctrl+L / Ctrl+I - Ctrl+L was Toggle Live MIDI Input,
        # which moves to Ctrl+D below.
        a.loop_toggle = self._action(
            "Toggle Loopin&g", self.slots.toggle_loop,
            QKeySequence("Ctrl+L"), checkable=True,
            status_tip="Loop the loop-length window from the cursor when playing",
        )
        playback_menu.addAction(a.loop_toggle)

        a.lead_in_toggle = self._action(
            "Toggle Lead-&in", self.slots.toggle_lead_in,
            QKeySequence("Ctrl+I"), checkable=True,
            status_tip="Play a metronome count-in before playback starts",
        )
        playback_menu.addAction(a.lead_in_toggle)

        playback_menu.addSeparator()

        a.mute = self._action(
            "&Mute", self.slots.toggle_mute_current_region2_row, QKeySequence(Qt.Key.Key_F8),
            status_tip="Mute the focused row in the Parts region",
        )
        playback_menu.addAction(a.mute)

        a.solo = self._action(
            "&Solo", self.slots.toggle_solo_current_region2_row, QKeySequence(Qt.Key.Key_F9),
            status_tip="Solo the focused row in the Parts region",
        )
        playback_menu.addAction(a.solo)

        a.unmute_all = self._action(
            "Unmute &All", self.slots.unmute_all_region2, QKeySequence("Alt+F8"),
        )
        playback_menu.addAction(a.unmute_all)

        a.unsolo_all = self._action(
            "Unsolo A&ll", self.slots.unsolo_all_region2, QKeySequence("Alt+F9"),
        )
        playback_menu.addAction(a.unsolo_all)

        playback_menu.addSeparator()

        # Wishlist #4: volume/pan per instrument plus the click, position
        # announcer and performance-cue channels. Mnemonic on Mi&xer, not
        # &Mixer - &Mixer would collide with &Mute above in this same menu.
        a.mixer = self._action(
            "Mi&xer...", self.slots._show_mixer_dialog, "Ctrl+Shift+X",
            status_tip="Set volume and pan for each instrument and sound",
        )
        playback_menu.addAction(a.mixer)

    def _options_menu(self, menu_bar, a: Actions) -> None:
        options_menu = menu_bar.addMenu("&Options")

        # Two mutually exclusive checkable items rather than one toggle:
        # the user wants "at least one ticked" always visible, which a
        # single checkable action can't convey as clearly. "Terminology
        # (UK/US)" (user-requested 2026-08-26, reverting an earlier
        # "Language (UK/US)" rename) - mnemonic freed up by moving Tempo
        # Offset's own mnemonic above, rather than shortening this menu's
        # own wording.
        terminology_menu = options_menu.addMenu("&Terminology (UK/US)")
        a.terminology_group = QActionGroup(self.window)
        a.terminology_group.setExclusive(True)

        # No mnemonics at all (user-requested 2026-08-26): NVDA announces a
        # QAction's "&"-mnemonic as its own "alt+<letter>" keyboard-shortcut
        # hint even inside a two-item submenu reached purely by arrowing in
        # - not a real global shortcut, just noise here, since switching
        # terminology is something the user picks from this menu directly
        # rather than needing a quick-jump letter for.
        a.uk_language = self._action("UK", self.slots._select_uk_terms, checkable=True)
        a.uk_language.setChecked(self.uk_terms)
        a.terminology_group.addAction(a.uk_language)
        terminology_menu.addAction(a.uk_language)

        a.us_language = self._action("US", self.slots._select_us_terms, checkable=True)
        a.us_language.setChecked(not self.uk_terms)
        a.terminology_group.addAction(a.us_language)
        terminology_menu.addAction(a.us_language)

        # Checkable so screen readers announce its state on focus - one of
        # three ways to discover it, with the shortcut and the status bar.
        a.metronome = self._action(
            "Toggle &Metronome", self.slots.toggle_metronome,
            QKeySequence("Ctrl+M"), checkable=True,
        )
        options_menu.addAction(a.metronome)

        # Ref 28: same checkable-action pattern, independently toggleable -
        # both exist side by side, neither disables the other.
        a.position_announcer = self._action(
            "Toggle &Position Announcer", self.slots.toggle_position_announcer,
            QKeySequence("Ctrl+P"), checkable=True,
        )
        options_menu.addAction(a.position_announcer)

        # Play a connected MIDI keyboard/controller live through the app's
        # own synth. Ctrl+D to turn it on/off (moved off Ctrl+L, which is
        # now Toggle Looping in the Playback menu; bare D is tempo-reset, a
        # different modifier), Ctrl+Shift+L for the settings dialog
        # (matching the Ctrl+Shift+letter family Instruments/Key Signature/
        # Mixer already use). Mnemonic on &Input, not &MIDI - &MIDI would
        # collide with Toggle &Metronome above in this same menu.
        a.live_midi_input = self._action(
            "Toggle Live MIDI &Input", self.slots.toggle_live_midi_input,
            QKeySequence("Ctrl+D"), checkable=True,
            status_tip="Play a connected MIDI keyboard live through Recall Score",
        )
        options_menu.addAction(a.live_midi_input)

        a.live_midi_input_settings = self._action(
            "Live MIDI Input &Settings...", self.slots._show_live_midi_input_dialog,
            QKeySequence("Ctrl+Shift+L"),
            status_tip="Choose the MIDI device, instrument, volume and pan for live input",
        )
        options_menu.addAction(a.live_midi_input_settings)

        # Hands-free voice control (Ref 19): spoken commands ("play",
        # "forward", "next bar", ...) call the same NavigationController/
        # PlaybackController methods a keyboard shortcut would, for a
        # musician whose hands are already busy holding their instrument.
        # Alt+Enter/Alt+Return (moved off Ctrl+Enter/Ctrl+Return, which now
        # commits a typed number as the loop length - see main_window.py's
        # setup_shortcuts).
        a.voice_control = self._action(
            "Toggle Voice &Control", self.slots.toggle_voice_control,
            checkable=True,
            status_tip="Control playback and navigation hands-free by voice",
        )
        # Two shortcuts, not one: QKeySequence("Alt+Enter") parses to the
        # NUMPAD Enter key (Qt::Key_Enter), not the main keyboard Return key
        # - the same numpad-vs-main-keyboard distinction previously reported
        # for the Ctrl variant. Enter listed FIRST so it is the
        # primary/displayed shortcut while the main Return key still
        # triggers the action too.
        a.voice_control.setShortcuts([
            QKeySequence("Alt+Enter"), QKeySequence("Alt+Return"),
        ])
        options_menu.addAction(a.voice_control)

        # Mnemonic on &Voice, not &Settings - &Settings collided with
        # Live MIDI Input &Settings above in this same menu (an earlier
        # version of this mnemonic, on a different letter, had also
        # collided with the top-level &Edit menu's own mnemonic - each fix
        # so far has moved the ampersand without checking the whole menu,
        # which is what let it drift into a new collision each time).
        a.voice_control_settings = self._action(
            "&Voice Control Settings...", self.slots._show_voice_control_dialog,
            "Ctrl+Shift+R",
            status_tip="Choose the microphone and confidence threshold for voice control",
        )
        options_menu.addAction(a.voice_control_settings)

        # Ref 15 AC4: the ordering half of the attribute-display system;
        # add/remove is Region 4's right-click menu. Given a real global
        # Ctrl+Shift+A shortcut and NO mnemonic (user-requested
        # 2026-08-26: these open a dialog like Instruments/Key Signature/
        # Mixer/etc, which all get a Ctrl+Shift+<letter> shortcut, but this
        # one never had - its only "shortcut" was an Alt+A mnemonic that
        # only worked with the Options menu already open, which NVDA
        # nonetheless announced as if it were a real global "alt+a").
        # Removing the "&" stops that misleading announcement; the visible
        # "Ctrl+Shift+A" Qt now appends automatically is the real thing.
        a.attribute_order = self._action(
            "Reorder Attributes...", self.slots._show_attribute_order_dialog,
            QKeySequence("Ctrl+Shift+A"),
        )
        options_menu.addAction(a.attribute_order)

        # Reported: NVDA reads whichever part's row Region 3 lands on
        # first (always row 0) after every navigation step - this
        # controls that order directly. Same real-global-shortcut-instead-
        # of-a-misleading-mnemonic treatment as Reorder Attributes above;
        # Ctrl+Shift+P was already Toggle Position Announcer's single-Ctrl
        # binding, a different modifier combination, so Ctrl+Shift+O is
        # used here instead to avoid any risk of confusing the two.
        a.part_order = self._action(
            "Reorder Parts...", self.slots._show_part_order_dialog,
            QKeySequence("Ctrl+Shift+O"),
        )
        options_menu.addAction(a.part_order)

    def _tools_menu(self, menu_bar, a: Actions) -> None:
        # New top-level menu (the user's own framing) - a microphone-based
        # chromatic tuner for guitar/bass/violin/etc (see the tuner plan).
        # Ctrl+Shift+T, matching every other Options/Edit dialog's own
        # Ctrl+Shift+<letter> shortcut (Mixer/X, Instruments/I, Key
        # Signature/K, Live MIDI Input/L, Voice Control/R) - reported live:
        # with no real QAction shortcut, the item's original "&Tuner..."
        # mnemonic (T) collided with the parent "&Tools" menu's own
        # mnemonic (also T), so NVDA reading "Alt+T" against the item just
        # opened the Tools menu instead of the dialog. Worked around at the
        # time by adding the Ctrl+Shift+T shortcut above rather than fixing
        # the mnemonic itself; now actually fixed below (T&uner..., U) as
        # part of a full mnemonic-collision sweep (2026-08-26).
        tools_menu = menu_bar.addMenu("&Tools")
        a.tuner = self._action(
            "T&uner...", self.slots._show_tuner_dialog, "Ctrl+Shift+T",
            status_tip="Tune a guitar, bass, violin or other stringed instrument by microphone",
        )
        tools_menu.addAction(a.tuner)

        # Moved here from Edit (user-requested review, 2026-08-26): a
        # read-only whole-score summary - see
        # widgets/performance_report_dialog.py. Given a real global
        # Ctrl+Shift+P shortcut and no mnemonic, same "an Alt-only mnemonic
        # that NVDA announces as if it were a real global shortcut, for an
        # item that opens a dialog like every other Ctrl+Shift+<letter>
        # item, is misleading" reasoning as Reorder Attributes/Parts above.
        tools_menu.addSeparator()
        a.performance_report = self._action(
            "Performance Report...", self.slots._show_performance_report_dialog,
            QKeySequence("Ctrl+Shift+P"),
        )
        tools_menu.addAction(a.performance_report)

    def _help_menu(self, menu_bar, a: Actions) -> None:
        # No mnemonics on either item (user-requested 2026-08-26: "false
        # shortcuts being announced here, no shortcuts needed") - neither
        # opens a dialog worth a global shortcut, so an Alt-only mnemonic
        # here was pure noise for NVDA to announce.
        help_menu = menu_bar.addMenu("&Help")
        a.user_guide = self._action("User Guide...", self.slots._show_user_guide)
        help_menu.addAction(a.user_guide)
        a.about = self._action("About Recall Score...", self.slots._show_about_dialog)
        help_menu.addAction(a.about)
