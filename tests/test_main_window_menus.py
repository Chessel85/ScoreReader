# tests/test_main_window_menus.py
"""Menu shortcuts and mnemonics, the Ctrl+T / Ctrl+G / Ctrl+F wiring checks, the About dialog, and the goto-measure dialog focus. Split from test_main_window.py (S10).
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QDialog, QLabel

from widgets.about_dialog import AboutDialog
from widgets.goto_measure_dialog import GotoMeasureDialog
from tests.support.main_window_helpers import _focus, _show, load_and_wait


def test_ctrl_t_shortcut_opens_the_play_settings_dialog(window, qtbot, null_synth, minimal_score, monkeypatch):
    """Ctrl+T now opens Play Settings (it inherited the old Tempo Offset
    dialog's shortcut). Same scope as Ctrl+G: fires from anywhere normal
    for a shortcut, not just a particular region."""
    load_and_wait(window, qtbot, minimal_score)
    _show(window, qtbot)
    _focus(window.region_1)
    opened = []
    monkeypatch.setattr(
        "main_window.PlaySettingsDialog",
        lambda *a, **k: type(
            "FakeDialog", (), {"exec": lambda self: opened.append(True) or QDialog.DialogCode.Rejected}
        )(),
    )

    qtbot.keyClick(window, Qt.Key.Key_T, Qt.KeyboardModifier.ControlModifier)

    assert opened == [True]


def test_navigation_menu_items_use_home_and_end_shortcuts(window):
    assert window.first_measure_action.shortcut() == QKeySequence(Qt.Key.Key_Home)
    assert window.last_measure_action.shortcut() == QKeySequence(Qt.Key.Key_End)
    assert window.goto_measure_action.shortcut() == QKeySequence("Ctrl+G")
    assert window.move_to_notes_action.shortcut() == QKeySequence("C")
    assert window.move_to_metadata_action.shortcut() == QKeySequence("Z")
    assert window.move_to_parts_action.shortcut() == QKeySequence("X")
    assert window.move_to_attributes_action.shortcut() == QKeySequence("V")
    assert window.move_to_performance_action.shortcut() == QKeySequence("B")


def _mnemonic(text: str):
    """The '&'-prefixed letter Qt uses as this action/menu's Alt-access
    key, or None if it has none. '&&' is Qt's escape for a literal
    ampersand, not a mnemonic marker, and must be skipped rather than
    read as one."""
    i = 0
    while True:
        i = text.find("&", i)
        if i == -1:
            return None
        if text[i:i + 2] == "&&":
            i += 2
            continue
        return text[i + 1].upper() if i + 1 < len(text) else None


def test_reorder_and_performance_report_actions_have_global_dialog_shortcuts(window):
    """User-requested 2026-08-26: these three open a dialog exactly like
    Instruments/Key Signature/Mixer/etc, which all get a real
    Ctrl+Shift+<letter> shortcut - but these three never had one, only an
    Alt-only menu mnemonic that NVDA nonetheless announced as if it were a
    real global shortcut. Now they have the real thing, and (see the next
    test) no mnemonic to cause that confusion."""
    assert window.attribute_order_action.shortcut() == QKeySequence("Ctrl+Shift+A")
    assert window.part_order_action.shortcut() == QKeySequence("Ctrl+Shift+O")
    assert window.performance_report_action.shortcut() == QKeySequence("Ctrl+Shift+P")


def test_items_with_no_menu_mnemonic_have_no_ampersand(window):
    """User-requested 2026-08-26: NVDA was announcing an "alt+<letter>"
    hint for several items where that access key either duplicated a real
    global shortcut's own letter with no added value (Reorder Attributes/
    Parts, Performance Report - see the test above) or was never wanted at
    all (UK/US: "the user just changes them with the menu"; Help menu:
    "no shortcuts needed"). All of these must now have a literal "&"-free
    label so Qt never registers a mnemonic for them."""
    no_mnemonic_actions = [
        window.attribute_order_action,
        window.part_order_action,
        window.performance_report_action,
        window.uk_language_action,
        window.us_language_action,
        window.user_guide_action,
        window.about_action,
    ]
    for action in no_mnemonic_actions:
        assert "&" not in action.text(), f"{action.text()!r} still has a mnemonic"


def test_no_menu_mnemonic_collisions(window):
    """Regression guard for the 2026-08-26 mnemonic-collision sweep (see
    'Menus and shortcuts.txt'): within every menu, each item's mnemonic
    must be distinct from its siblings' AND from the menu's own top-level
    mnemonic. Both collision classes caused real, live NVDA bugs before
    being fixed (Tools > Tuner both "T"; several sibling pairs sharing a
    letter, e.g. Playback's old &Mute/&Mixer both "M") - this walks every
    menu (and one level into any submenu, e.g. Options > Language) rather
    than hardcoding the fixed set found by hand, so a future menu item
    that reintroduces either class of collision fails here instead of
    waiting for another live report."""
    for top_action in window.menuBar().actions():
        menu = top_action.menu()
        if menu is None:
            continue
        top_mnemonic = _mnemonic(top_action.text())
        seen = {}
        for action in menu.actions():
            if action.isSeparator():
                continue
            mnemonic = _mnemonic(action.text())
            if mnemonic is not None:
                assert mnemonic != top_mnemonic, (
                    f"{action.text()!r} in {top_action.text()!r} repeats "
                    f"its own menu's mnemonic ({mnemonic})"
                )
                assert mnemonic not in seen, (
                    f"{action.text()!r} and {seen.get(mnemonic)!r} in "
                    f"{top_action.text()!r} both use mnemonic {mnemonic}"
                )
                seen[mnemonic] = action.text()

            submenu = action.menu()
            if submenu is None:
                continue
            sub_seen = {}
            for sub_action in submenu.actions():
                if sub_action.isSeparator():
                    continue
                sub_mnemonic = _mnemonic(sub_action.text())
                if sub_mnemonic is None:
                    continue
                assert sub_mnemonic not in sub_seen, (
                    f"{sub_action.text()!r} and {sub_seen.get(sub_mnemonic)!r} "
                    f"in {action.text()!r} both use mnemonic {sub_mnemonic}"
                )
                sub_seen[sub_mnemonic] = sub_action.text()


def test_goto_measure_dialog_shows_with_focus_on_the_edit_field(window, qtbot):
    """The dialog used to call setFocus() in __init__, before the native
    window existed - Qt's own focus tracking accepted it, but no
    accessibility focus-changed event ever reached NVDA, which kept
    announcing whatever had focus before Ctrl+G was pressed. Deferring the
    setFocus() to after showEvent (see GotoMeasureDialog.showEvent) fixes
    that; this proves the edit field actually ends up with real Qt focus
    once the dialog is shown, not just tab-order to it."""
    dialog = GotoMeasureDialog(window)
    qtbot.addWidget(dialog)

    dialog.show()
    qtbot.waitExposed(dialog)
    qtbot.waitUntil(lambda: dialog.focusWidget() is dialog.measure_edit)

    assert dialog.focusWidget() is dialog.measure_edit


def test_about_dialog_shows_the_version_number(window):
    from version import __version__

    dialog = AboutDialog(window)
    labels = dialog.findChildren(QLabel)

    assert any(__version__ in label.text() for label in labels)


def test_about_dialog_labels_are_individually_tab_focusable(window):
    """Each piece of the About text (name, version, description) is its own
    Tab stop, so NVDA users can move through them one at a time instead of
    hearing one large label read all at once."""
    dialog = AboutDialog(window)
    labels = dialog.findChildren(QLabel)

    assert len(labels) >= 3
    for label in labels:
        assert label.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_about_action_opens_without_crashing(window, qtbot, monkeypatch):
    opened = []
    monkeypatch.setattr("main_window.AboutDialog", lambda parent: type(
        "FakeDialog", (), {"exec": lambda self: opened.append(True)}
    )())

    window._show_about_dialog()

    assert opened == [True]
