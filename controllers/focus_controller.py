# controllers/focus_controller.py
from PySide6.QtWidgets import QApplication


class FocusController:
    """The region focus cycle, the F6 regions/status-bar pane toggle, and the
    focus tracking both depend on.

    Region cycling deliberately does NOT use QWidget.setTabOrder /
    focusNextChild: Qt's focus chain is ONE shared window-wide doubly linked
    ring, and setTabOrder(a, b) relocates b's node within it. Closing an
    N-widget loop needs region_1 relocated too (the wrap-around call), which
    resets region_1's own outgoing pointer as a side effect and silently
    breaks the region_1->region_2 edge set earlier. It isn't fixable by
    reordering: with every widget used once as a source and once as a
    target, the dependency between the calls is circular. So the region
    widgets call focus_next/previous directly (via
    widgets/region_focus_cycle.py's RegionFocusCycleMixin), bypassing the
    global chain entirely.
    """

    def __init__(self, window, regions: list, status_bar,
                 first_measure_action=None, last_measure_action=None):
        # `window` is kept specifically for window.focusWidget(), which is
        # NOT the same as QApplication.focusWidget(): the former reports the
        # focus widget within this window's own subtree even when the window
        # isn't the active one, which is what the pane and Home/End enabling
        # checks rely on.
        self._window = window
        self._regions = regions
        self._status_bar = status_bar
        self.first_measure_action = first_measure_action
        self.last_measure_action = last_measure_action
        self.last_focused_region = regions[0] if regions else None
        self._tracking_connected = False

    # --- focus tracking ----------------------------------------------

    def connect_tracking(self) -> None:
        QApplication.instance().focusChanged.connect(self.on_focus_changed)
        self._tracking_connected = True

    @property
    def tracking_connected(self) -> bool:
        return self._tracking_connected

    def disconnect_tracking(self) -> None:
        """focusChanged is an APPLICATION-level signal: a closed window that
        stays subscribed keeps reacting to focus moves for the life of the
        process, and reaches its own widgets after the C++ objects are gone.

        Guarded by a flag, not try/except - closeEvent legitimately runs
        more than once, and PySide6 emits a RuntimeWarning rather than
        raising on a stale disconnect, so an except clause would never fire.
        """
        if not self._tracking_connected:
            return
        QApplication.instance().focusChanged.disconnect(self.on_focus_changed)
        self._tracking_connected = False

    def on_focus_changed(self, old, now) -> None:
        """Remembers the last-focused region so F6 restores it rather than
        always landing on Region 1."""
        if now in self._regions:
            self.last_focused_region = now
        self.update_navigation_actions_enabled(now)

    def update_navigation_actions_enabled(self, focus_widget=None) -> None:
        """Home/End only act on the Note region, so they are greyed out
        elsewhere - otherwise pressing Home in Region 1 silently jumps the
        timeline underneath what the user is reading. Called with no
        argument at menu-build time, before any focusChanged has fired."""
        if self.first_measure_action is None or self.last_measure_action is None:
            return
        if focus_widget is None:
            focus_widget = self._window.focusWidget()
        in_note_region = focus_widget is self.note_region
        self.first_measure_action.setEnabled(in_note_region)
        self.last_measure_action.setEnabled(in_note_region)

    # --- the cycle ----------------------------------------------------

    @property
    def note_region(self):
        return self._regions[2]

    def focus_next(self, current) -> None:
        """Tab within the regions area: cycles 1->2->3->4->5->1 and never
        leaves."""
        index = self._regions.index(current)
        self._regions[(index + 1) % len(self._regions)].setFocus()

    def focus_previous(self, current) -> None:
        """Shift+Tab within the regions area: the reverse of focus_next."""
        index = self._regions.index(current)
        self._regions[(index - 1) % len(self._regions)].setFocus()

    # --- panes --------------------------------------------------------

    def current_pane(self) -> str:
        focus = self._window.focusWidget()
        if focus is not None and (
            focus is self._status_bar or self._status_bar.isAncestorOf(focus)
        ):
            return "status"
        return "region"

    def focus_region_pane(self) -> None:
        (self.last_focused_region or self._regions[0]).setFocus()

    def toggle_pane(self) -> None:
        """F6/Shift+F6: toggle between the regions area (restoring the
        last-focused region) and the status bar. Two panes only - the menu
        bar is left to the OS's native Alt mechanism."""
        if self.current_pane() == "status":
            self.focus_region_pane()
        else:
            self._status_bar.first_field().setFocus()
