# widgets/list_focus_helper.py
import shiboken6
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QListWidget

# Gap between each step below. Reported live (2026-08-29): the original,
# single-tick version of this function (setFocus() then an immediate
# setCurrentRow(-1)/setCurrentRow(row) toggle, all inside one
# QTimer.singleShot(0, ...) callback) did NOT fix the bug - NVDA's
# automatic dialog-open announcement, and a follow-up NVDA+Up ("read
# current line"), both still spoke the previous window's last-focused row
# text, not the dialog's. Only a genuine, manually-typed Up/Down inside the
# dialog produced correct speech. Doing every step within one JS-style
# "tick" apparently doesn't give NVDA's own event processing (it receives
# these as Windows accessibility events, dispatched via its own message
# loop/COM marshaling) a chance to catch up between steps, so it seems to
# only ever observe the LAST state change and reads text cached from
# before any of this ran. Spacing the steps across real timer delays fixed
# it - confirmed live with NVDA, same day: NVDA+Up now reads the dialog's
# actual current row on the first try, no manual Up/Down needed first.
# Accepted trade-off (confirmed live, not treated as a bug): the dialog's
# opening announcement (title, list label, current row) is now spoken
# twice - once for the real focus-in, once more when this function's
# setCurrentRow(-1)/setCurrentRow(row) replays it a beat later. Judged
# worth it for "NVDA+Up correctly reads the current row" actually working.
_STEP_DELAY_MS = 120


def focus_list_and_reannounce_current_row(list_widget: QListWidget) -> None:
    """Give list_widget real keyboard focus and re-fire its current-row
    change so NVDA's review cursor actually lands on the current row.

    Root cause (confirmed live - see _STEP_DELAY_MS above for the fix
    attempt that didn't work before this one): every dialog here
    sets its list's initial current row in __init__/_populate, before the
    dialog's native window exists - at that point
    QAbstractItemView::hasFocus() is False, and Qt's own accessibility
    plumbing (qabstractitemview.cpp's currentChanged handler) only posts a
    QAccessible::Focus event for the *item* when the view already has
    focus at the moment currentChanged fires. A bare list_widget.setFocus()
    (the older showEvent idiom, see docs/dialog_widget_patterns.md) only
    posts a widget-level Focus event - nothing ever tells NVDA which row is
    current. A manual Up/Down press fixes it because that keypress is the
    first currentChanged to fire while the view genuinely has focus.

    Call this from showEvent instead of a bare list_widget.setFocus(),
    still deferred via QTimer.singleShot(0, ...) for the native-window-must-
    exist-first reason every dialog's focus-on-show already follows. This
    function then does its own further-delayed setFocus() -> setCurrentRow
    (-1) -> setCurrentRow(row) sequence, spaced by _STEP_DELAY_MS each, to
    give NVDA's own event handling room to process each step rather than
    only observing the final state.
    """
    # Each step is deferred by a real timer, which can fire after the
    # dialog (and list_widget's underlying C++ object) has already been
    # closed and destroyed - e.g. a test or a fast Escape/Ok press. Guard
    # every step with shiboken6.isValid so a stale callback is a silent
    # no-op instead of "Internal C++ object already deleted".
    def _do_focus():
        if not shiboken6.isValid(list_widget):
            return
        list_widget.setFocus()
        QTimer.singleShot(_STEP_DELAY_MS, _do_clear)

    def _do_clear():
        if not shiboken6.isValid(list_widget):
            return
        row = list_widget.currentRow()
        if row < 0:
            return
        list_widget.setCurrentRow(-1)
        QTimer.singleShot(_STEP_DELAY_MS, _do_restore(row))

    def _do_restore(row: int):
        def _run():
            if not shiboken6.isValid(list_widget):
                return
            list_widget.setCurrentRow(row)
        return _run

    _do_focus()
