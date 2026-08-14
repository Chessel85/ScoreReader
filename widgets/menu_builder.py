# widgets/menu_builder.py
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence

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
    open_example: Optional[QAction] = None
    exit: Optional[QAction] = None
    open_folder: Optional[QAction] = None
    clear_preferences: Optional[QAction] = None
    performance_report: Optional[QAction] = None
    mixer: Optional[QAction] = None
    first_measure: Optional[QAction] = None
    last_measure: Optional[QAction] = None
    goto_measure: Optional[QAction] = None
    move_to_metadata: Optional[QAction] = None
    move_to_parts: Optional[QAction] = None
    move_to_notes: Optional[QAction] = None
    move_to_attributes: Optional[QAction] = None
    move_to_performance: Optional[QAction] = None
    tempo_offset: Optional[QAction] = None
    uk_language: Optional[QAction] = None
    us_language: Optional[QAction] = None
    terminology_group: Optional[QActionGroup] = None
    metronome: Optional[QAction] = None
    position_announcer: Optional[QAction] = None
    attribute_order: Optional[QAction] = None
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
        self._options_menu(menu_bar, a)
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
        # The same dialog as Open..., but starting in the bundled examples/
        # rather than the last-used location.
        a.open_example = self._action(
            "Open E&xample Score...", self.slots.open_example_file_dialog,
            status_tip="Open a bundled example score",
        )
        a.exit = self._action("E&xit", self.window.close, QKeySequence.Quit)

        file_menu.addAction(a.open)
        file_menu.addAction(a.open_example)
        file_menu.addSeparator()
        file_menu.addAction(a.exit)

    def _edit_menu(self, menu_bar, a: Actions) -> None:
        # Ref 27: users are meant to stay unaware .rsc files exist; these
        # entries are a deliberate minimal escape hatch, not a settings UI.
        edit_menu = menu_bar.addMenu("&Edit")

        a.open_folder = self._action(
            "Open Local &Folder", self.slots._open_score_config_folder,
            status_tip="Open the folder where saved preferences are stored",
        )
        edit_menu.addAction(a.open_folder)

        a.clear_preferences = self._action(
            self.slots._clear_preferences_action_text(),
            self.slots._clear_current_score_preferences,
        )
        edit_menu.addAction(a.clear_preferences)

        # Ref 29: read-only whole-score summary - see
        # widgets/performance_report_dialog.py.
        a.performance_report = self._action(
            "Performance &Report...", self.slots._show_performance_report_dialog
        )
        edit_menu.addAction(a.performance_report)

        # Wishlist #4: volume/pan per instrument plus the click, position
        # announcer and performance-cue channels.
        a.mixer = self._action(
            "&Mixer...", self.slots._show_mixer_dialog, "Ctrl+Shift+X",
            status_tip="Set volume and pan for each instrument and sound",
        )
        edit_menu.addAction(a.mixer)

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
        a.move_to_notes = self._action(
            "Move to &Notes", self.slots._navigation_menu_move_to_notes,
            QKeySequence("N"),
        )
        # A direct-jump shortcut per region. Letters chosen to avoid the
        # existing bare F/S/D tempo shortcuts - hence I for Info, not S.
        a.move_to_metadata = self._action(
            "Move to &Info", self.slots._navigation_menu_move_to_metadata,
            QKeySequence("I"),
        )
        a.move_to_parts = self._action(
            "Move to Parts List (&V)", self.slots._navigation_menu_move_to_parts,
            QKeySequence("V"),
        )
        a.move_to_attributes = self._action(
            "Move to &Attributes", self.slots._navigation_menu_move_to_attributes,
            QKeySequence("A"),
        )
        a.move_to_performance = self._action(
            "Move to &Performance", self.slots._navigation_menu_move_to_performance,
            QKeySequence("P"),
        )

        navigation_menu.addAction(a.first_measure)
        navigation_menu.addAction(a.last_measure)
        navigation_menu.addSeparator()
        navigation_menu.addAction(a.goto_measure)
        navigation_menu.addSeparator()
        navigation_menu.addAction(a.move_to_metadata)
        navigation_menu.addAction(a.move_to_parts)
        navigation_menu.addAction(a.move_to_notes)
        navigation_menu.addAction(a.move_to_attributes)
        navigation_menu.addAction(a.move_to_performance)

    def _options_menu(self, menu_bar, a: Actions) -> None:
        options_menu = menu_bar.addMenu("&Options")

        # Ctrl+T, same scope as Ctrl+G: fires anywhere in the window, not
        # only when a particular region has focus.
        a.tempo_offset = self._action(
            "&Tempo Offset...", self.slots._show_tempo_offset_dialog,
            QKeySequence("Ctrl+T"),
        )
        options_menu.addAction(a.tempo_offset)

        # Two mutually exclusive checkable items rather than one toggle:
        # the user wants "at least one ticked" always visible, which a
        # single checkable action can't convey as clearly.
        terminology_menu = options_menu.addMenu("&Terminology Language")
        a.terminology_group = QActionGroup(self.window)
        a.terminology_group.setExclusive(True)

        a.uk_language = self._action("&UK", self.slots._select_uk_terms, checkable=True)
        a.uk_language.setChecked(self.uk_terms)
        a.terminology_group.addAction(a.uk_language)
        terminology_menu.addAction(a.uk_language)

        a.us_language = self._action("&US", self.slots._select_us_terms, checkable=True)
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

        # Ref 15 AC4: the ordering half of the attribute-display system;
        # add/remove is Region 4's right-click menu.
        a.attribute_order = self._action(
            "Reorder &Attributes...", self.slots._show_attribute_order_dialog
        )
        options_menu.addAction(a.attribute_order)

    def _help_menu(self, menu_bar, a: Actions) -> None:
        help_menu = menu_bar.addMenu("&Help")
        a.user_guide = self._action("&User Guide...", self.slots._show_user_guide)
        help_menu.addAction(a.user_guide)
        a.about = self._action("&About Recall Score...", self.slots._show_about_dialog)
        help_menu.addAction(a.about)
