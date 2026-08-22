# controllers/region_presenter.py
from typing import List, Optional

from PySide6.QtCore import QItemSelectionModel, QObject, Signal
from PySide6.QtWidgets import QListWidgetItem

from audio.performance_cue import performance_cue_event
from models.vocabulary import bar_word


class RegionPresenter(QObject):
    """Everything that renders into the five regions and the status bar.

    The only controller that touches widgets. Reads MusicData through the
    session and never mutates the cursor - moving is NavigationController's
    job, drawing the result is this one's.

    audition_requested is emitted, rather than the synth being called
    directly, so this stays independent of playback while the ORDER of
    "sound the notes, then fire the performance cue" is still preserved -
    Qt delivers a direct-connected signal synchronously, so the emit lands
    exactly where the old inline call did (see update_timeline_views).
    """

    audition_requested = Signal()

    def __init__(self, session, region_1, region_2, region_3, region_4, region_5,
                 status_bar, playback_status_fields, parent=None):
        super().__init__(parent)
        self.session = session
        self.region_1 = region_1
        self.region_2 = region_2
        self.region_3 = region_3
        self.region_4 = region_4
        self.region_5 = region_5
        self.status_bar = status_bar
        # Callable returning the three playback status strings. Injected
        # rather than importing PlaybackController, so the dependency runs
        # one way only.
        self._playback_status_fields = playback_status_fields

        # Region 5's current labels, diffed by refresh_region_5 so only a
        # real change rebuilds the list and fires the cue. Must start as
        # None, not []: an opening position with no spans also has [] rows,
        # so [] would compare equal and skip the very first render, leaving
        # Region 5 empty instead of showing its "None" placeholder. Reset to
        # None per load so a new file isn't diffed against the old one's.
        self.last_performance_row_labels: Optional[List[str]] = None

    @property
    def music_data(self):
        return self.session.music_data

    def selected_region_3_indices(self) -> List[int]:
        return [item.row() for item in self.region_3.selectedIndexes()]

    # --- whole-score refresh -----------------------------------------

    def reset_performance_labels(self) -> None:
        """A new score's Region 5 must not be diffed against the old one's
        leftover labels."""
        self.last_performance_row_labels = None

    def refresh_all(self, play_all: bool = True) -> None:
        if not self.music_data:
            return
        self.region_1.refresh_list(self.music_data.get_region_1_data())
        self.region_2.load_score_structure(self.music_data.get_score_structure())
        self.update_timeline_views(play_all=play_all)

    def restore_mute_solo_node_keys(
        self, parts_muted, staves_muted, voices_muted,
        parts_soloed, staves_soloed, voices_soloed,
    ) -> None:
        self.region_2.apply_muted_node_keys(parts_muted, staves_muted, voices_muted)
        self.region_2.apply_soloed_node_keys(parts_soloed, staves_soloed, voices_soloed)

    # --- timeline / regions 3, 4, 5 -----------------------------------

    def update_timeline_views(self, play_all: bool = True) -> None:
        if not self.music_data:
            return

        self.region_3.blockSignals(True)
        self.region_3.clear()

        for item in self.music_data.get_region_3_data():
            self.region_3.addItem(QListWidgetItem(item))

        self.region_3.selectAll()
        self.region_3.blockSignals(False)

        # selectAll() marks rows selected but leaves the view's "current"
        # item untouched, and clear() reset it to none - so without this
        # NVDA has no definite item to announce. Must sit OUTSIDE the
        # blockSignals window so currentChanged actually fires and the
        # accessibility bridge posts the notification.
        #
        # The NoUpdate flag is required, not decorative: the one-arg
        # setCurrentRow(row) does NOT default to it in this PySide6 version.
        # It collapses the selection to just `row`, silently turning "moving
        # onto a chord sounds every note" into "only the first note sounds".
        if self.region_3.count() > 0:
            self.region_3.setCurrentRow(0, QItemSelectionModel.SelectionFlag.NoUpdate)

        self.on_region_3_selection_changed()
        self.update_status_bar()

        # Sound the notes BEFORE the performance cue, never after: the
        # cue is on its own channel, but play_chord's default
        # retrigger=True calls stop_all_notes(), which would cut a
        # just-started cue off. Playback never hits this (the Sequencer
        # sounds its own chord with retrigger=False), which is why the cue
        # appeared to work there but not during manual navigation.
        if play_all:
            self.audition_requested.emit()

        self.refresh_region_5()

    def refresh_region_3_labels(self) -> None:
        """Re-renders Region 3's row text in place after an attribute
        change. Deliberately NOT update_timeline_views, which would
        selectAll() (discarding a multi-selection) and re-audition notes
        that haven't moved - an attribute toggle changes neither the notes
        nor the row count."""
        if not self.music_data:
            return

        labels = self.music_data.get_region_3_data()
        self.region_3.blockSignals(True)
        for row, text in enumerate(labels):
            item = self.region_3.item(row)
            if item is not None:
                item.setText(text)
        self.region_3.blockSignals(False)

        self.on_region_3_selection_changed()

    def refresh_region_5(self) -> None:
        """Ref 29: recomputes Region 5's rows for the current position.

        Skips the rebuild entirely (not just the cue) when the label set is
        unchanged, so Region 5's focus and selection survive navigation
        within the same span, and the cue only fires on a real change -
        EXCEPT landing back on the first note of measure 1 when a repeat
        sends the piece back there (MusicData.is_at_beginning_repeat_target,
        user-requested): that always re-fires the cue, with no list rebuild,
        since arrowing back into an already-displayed repeat span (or
        starting playback from bar 1 without moving the cursor first) would
        otherwise stay silent under the ordinary dedup above."""
        if not self.music_data:
            return
        rows = self.music_data.get_performance_region_rows()
        labels = [r.label for r in rows]
        if labels != self.last_performance_row_labels:
            self.region_5.refresh_list(rows)
            self.session.synth.play_performance_cue(*performance_cue_event())
            self.last_performance_row_labels = labels
        elif self.music_data.is_at_beginning_repeat_target():
            self.session.synth.play_performance_cue(*performance_cue_event())

    def select_all_region_3(self) -> None:
        self.region_3.selectAll()
        self.audition_requested.emit()

    def on_region_3_selection_changed(self) -> None:
        if not self.music_data:
            return
        region_4_data = self.music_data.get_region_4_data_for_indices(
            self.selected_region_3_indices()
        )
        self.region_4.refresh_list(region_4_data)

    def on_region_2_filter_changed(self, active_voice_tuples: set) -> None:
        if self.music_data:
            self.music_data.set_active_voice_filter(active_voice_tuples)
            self.update_timeline_views(play_all=False)

    # --- status bar ---------------------------------------------------

    def update_status_bar(self) -> None:
        if not self.music_data:
            return
        fields = self.music_data.get_status_bar_fields()
        fields.extend(self._playback_status_fields())
        self.status_bar.set_fields(fields)

    def update_playback_status_field(self) -> None:
        """Updates only the playback field - phrase audition and pause/resume
        must not disturb the position fields a full refresh would."""
        self.status_bar.set_field(
            self.status_bar.PLAYBACK_FIELD, self._playback_status_fields()[0]
        )

    def show_pending_digits(self, digits: str) -> None:
        """While a bar number is being typed, show it in the status bar's
        position field; revert once the digits are cleared."""
        if not self.music_data:
            return
        if digits:
            fields = self.music_data.get_status_bar_fields()
            fields[0] = f"Go to {bar_word(self.session.uk_terms)}: {digits}"
            self.status_bar.set_fields(fields)
        else:
            self.update_status_bar()

    def refresh_region_1(self) -> None:
        if self.music_data:
            self.region_1.refresh_list(self.music_data.get_region_1_data())
