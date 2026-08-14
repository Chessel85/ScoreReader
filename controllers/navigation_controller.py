# controllers/navigation_controller.py
from PySide6.QtCore import QObject, Signal


class NavigationController(QObject):
    """Moving the timeline cursor: Left/Right, Ctrl+Left/Right, Home/End,
    a typed bar number, and Region 5's span jumps.

    Every method either moves and emits position_changed(play_all), or fails
    to move and emits boundary_hit. Deciding what a move sounds like and
    what it redraws is deliberately NOT this class's job - MainWindow wires
    those two signals - which is what keeps navigation free of both widgets
    and the synth.
    """

    position_changed = Signal(bool)  # play_all
    boundary_hit = Signal()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

    @property
    def music_data(self):
        return self.session.music_data

    def _moved(self, ok: bool) -> None:
        if ok:
            self.position_changed.emit(True)
        else:
            self.boundary_hit.emit()

    def timeline_left(self) -> None:
        if not self.music_data:
            return
        self._moved(self.music_data.move_timeline_left())

    def timeline_right(self) -> None:
        if not self.music_data:
            return
        self._moved(self.music_data.move_timeline_right())

    def measure_left(self) -> None:
        if not self.music_data:
            return
        self._moved(self.music_data.move_timeline_left_by_measure())

    def measure_right(self) -> None:
        if not self.music_data:
            return
        self._moved(self.music_data.move_timeline_right_by_measure())

    def timeline_home(self) -> None:
        """Home (Ref 5). Unlike Left/Right this jumps to a known limit, so it
        never represents crossing a boundary and never cues one."""
        if not self.music_data:
            return
        self.music_data.move_timeline_home()
        self.position_changed.emit(True)

    def timeline_end(self) -> None:
        """End (Ref 5) - see timeline_home."""
        if not self.music_data:
            return
        self.music_data.move_timeline_end()
        self.position_changed.emit(True)

    def to_typed_measure(self, digits: str) -> None:
        """Ref 6: Enter with pending digits jumps to that bar's first active
        event; an unknown bar sounds the boundary cue and doesn't move."""
        if not self.music_data:
            return
        self._moved(self.music_data.jump_to_measure(int(digits)))

    def jump_to_span(self, row, is_start: bool) -> None:
        """Region 5's Ctrl+Home/Ctrl+End (Ref 29). `row` is the focused
        PerformanceRegionRow, passed in rather than read off the widget.

        A hairpin row carries jump_target_quarters, because a wedge can
        start or stop mid-measure; a repeat/ending row has None and resolves
        by measure, barlines falling only at measure boundaries. Ctrl+End on
        one of those lands on the LAST sounding note of the end bar (the
        user's decision) - the app's only "last event in a measure" target.
        """
        if not self.music_data or row is None:
            return

        if row.jump_target_quarters is not None:
            index = self.music_data.slice_index_at_or_after_quarters(row.jump_target_quarters)
        elif is_start:
            index = self.music_data.first_visible_event_index_of_measure(row.jump_target_measure)
        else:
            index = self.music_data.last_visible_event_index_of_measure(row.jump_target_measure)

        if index is None:
            self.boundary_hit.emit()
            return

        self.music_data.active_event_index = index
        self.position_changed.emit(True)
