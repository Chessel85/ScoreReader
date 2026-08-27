# controllers/region_presenter.py
from typing import List, Optional

from PySide6.QtCore import QItemSelectionModel, QObject, Signal
from PySide6.QtWidgets import QListWidgetItem

from audio.performance_cue import performance_cue_event
from models.vocabulary import bar_word
from widgets import accessible_announcer


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

    def clear_all(self) -> None:
        """File > Close: blank every region and the status bar back to the
        way they look before any score is opened. The one method here that
        must run with self.music_data already None - it is the inverse of a
        load's refresh, not part of one."""
        self.region_1.clear()
        self.region_2.load_score_structure([])
        self.region_3.clear()
        self.region_4.clear()
        self.region_5.clear()
        self.status_bar.reset()
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

    # --- Region 2 in-place edits (S5) ---------------------------------
    #
    # ScoreEditController drives these; they live here because this stays
    # the only controller that touches widgets. All three are deliberately
    # in-place mutations rather than a load_score_structure rebuild, which
    # would reset every node back to enabled and discard the user's own
    # mute/solo toggles and expand state.

    def rename_part(self, part_id: str, name: str) -> None:
        self.region_2.rename_part(part_id, name)

    def rename_voice(self, part_id: str, staff_id: int, voice_id: int, label: str) -> None:
        self.region_2.rename_voice(part_id, staff_id, voice_id, label)

    def reorder_parts(self, part_id_order) -> None:
        self.region_2.reorder_parts(part_id_order)

    # --- timeline / regions 3, 4, 5 -----------------------------------

    def update_timeline_views(self, play_all: bool = True, announce_measure: bool = False) -> None:
        if not self.music_data:
            return

        # Fired BEFORE the rebuild below, not after: live-tested regression -
        # row 0's own natural accessibility announcement (see the comment on
        # setCurrentRow below) turned out to be unsuppressible from here.
        # blockSignals(True) on region_3 only gates signals region_3 ITSELF
        # emits; whatever Qt's accessibility bridge actually listens to for
        # "current item changed" (its selection model, or the underlying
        # list model's own insert signals - either way, a different QObject)
        # fires regardless, during the clear()/addItem() rebuild itself, no
        # matter when or whether setCurrentRow is called. An attempt to
        # suppress it and post one hand-built "Measure N. <note text>"
        # replacement instead produced a doubled announcement live ("C fret
        # 2 bar 6 C fret 2" - the un-suppressed natural one, then ours).
        # Since the natural announcement cannot reliably be stopped, this
        # instead posts a short, TEXT-FREE "Measure N." announcement first,
        # so it is heard before the natural mechanism announces the note -
        # never repeating what the natural announcement will say next.
        if announce_measure:
            self._announce_measure_change()

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

    def _announce_measure_change(self) -> None:
        """Speaks just the new bar number - "Measure 6." - via Qt's
        accessibility Announcement event (QAccessibleAnnouncementEvent, Qt
        6.8+; surfaces to NVDA as a UI Automation notification on Windows),
        called BEFORE update_timeline_views rebuilds Region 3 so this is
        heard first, ahead of the note itself. Deliberately does NOT include
        the note text - Region 3's own natural per-row announcement already
        supplies that immediately afterward (see update_timeline_views'
        comment on why it can't be suppressed and folded into one message
        here instead). This is a one-shot spoken message: it never touches
        what's displayed or stored in Region 3, so arrowing off row 0 and
        back within the same chord doesn't re-read the bar number."""
        current = self.music_data.get_current_slice()
        if current is None:
            return
        label = bar_word(self.session.uk_terms).capitalize()
        message = f"{label} {current.measure}."
        accessible_announcer.announce(self.region_3, message)

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

    def announce_attribute_by_number(self, number: int) -> None:
        """Ctrl+<number> in the Note region (TimelineListWidget.
        keyPressEvent) and the "attribute <number>" voice command
        (VoiceControlController) both land here: speaks Region 4's Nth row
        - the attribute list exactly as currently displayed for whichever
        note(s) are selected in Region 3 - without moving focus off Region
        3. A quick attribute lookup mid-navigation, the same one-shot
        QAccessibleAnnouncementEvent mechanism _announce_measure_change
        uses. number is 1-based, matching the row's displayed position.
        Out of range (including no score loaded, or fewer attributes than
        requested) is a silent no-op, never an error - "the number relates
        to the attribute list as it is displayed" means there is simply
        nothing at that position to read."""
        if not self.music_data:
            return
        rows = self.music_data.get_region_4_rows_for_indices(self.selected_region_3_indices())
        if number < 1 or number > len(rows):
            return
        display_key, _attribute_key, value = rows[number - 1]
        message = f"{display_key}: {value}"
        accessible_announcer.announce(self.region_3, message)

    def announce_preview_length(self, bars: int) -> None:
        """Alt+PageUp/PageDown (main_window.increase_preview_bars/
        decrease_preview_bars) change Preview's length without moving focus
        off the Note region - previously the only trace of the new value
        was the status bar's own preview-length field, which a screen
        reader user isn't focused on and so never heard change (the status
        bar text is what's displayed, not what's spoken - see
        _announce_measure_change above for why persisted widget text and a
        one-off spoken announcement are handled separately). User-requested
        2026-08-26; wording follows the UK/US terminology setting exactly
        like every other bar/measure label in the app."""
        label = bar_word(self.session.uk_terms)
        plural = "" if bars == 1 else "s"
        message = f"Preview {bars} {label}{plural}."
        accessible_announcer.announce(self.region_3, message)

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
        region_4_rows = self.music_data.get_region_4_rows_for_indices(
            self.selected_region_3_indices()
        )
        self.region_4.refresh_list(region_4_rows)

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
