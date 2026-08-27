# controllers/score_edit_controller.py
"""S5: applying a user's edits to the loaded score.

The counterpart of PlaybackController for score DATA rather than transport:
the Instruments dialog's name/instrument/percussion overrides (S5), the Key
Signature dialog's whole-piece override (S6), and Reorder Parts. Each of
these arrived as a block of merging-and-refreshing logic inside
MainWindow's own _show_*_dialog method, which contradicted the shell's
stated job (build widgets, own controllers, wire them together).

The split this keeps: MainWindow still CONSTRUCTS each dialog and calls
exec() - tests monkeypatch main_window.<DialogClass>, and dialog lifetime
is a view concern - then hands the result here. Controllers own the logic
behind a dialog, not its lifecycle.

Touches no widgets itself. Region 2's labels and row order are updated
through RegionPresenter, which stays the only controller that talks to
them; that is also why every method here ends by asking the presenter to
refresh rather than poking regions 3/4/5 directly.

Reads session.music_data per call and never caches it - MusicData is
replaced wholesale on every load (see ScoreSession).
"""
from typing import Dict, List, Optional, Tuple


class ScoreEditController:
    def __init__(self, session, presenter):
        self.session = session
        self.presenter = presenter

    @property
    def music_data(self):
        return self.session.music_data

    # --- Instruments dialog (S5, wishlist #8) --------------------------

    def instrument_rows(self) -> List[Tuple[str, str, int]]:
        """(part_id, current name, current GM program) per part - the
        dialog's main row list."""
        return [(p.part_id, p.name, p.gmidi_program) for p in self.music_data.parts_info]

    def percussion_part_ids(self) -> List[str]:
        return [p.part_id for p in self.music_data.parts_info if p.is_percussion]

    def percussion_rows(self) -> Dict[str, list]:
        """Per-item rows for each percussion part, keyed by part_id - a
        percussion part contributes one row per distinct drum/cymbal on top
        of its own part row (see MusicData.get_percussion_items_for_part)."""
        return {
            part_id: self.music_data.get_percussion_items_for_part(part_id)
            for part_id in self.percussion_part_ids()
        }

    def apply_instrument_overrides(
        self,
        name_overrides: Dict[str, str],
        program_overrides: Dict[str, int],
        item_name_overrides: Dict[Tuple[str, int], str],
        item_sound_overrides: Dict[Tuple[str, int], int],
        auto_correct_enabled: bool,
    ) -> bool:
        """Apply the Instruments dialog's five results. Returns whether
        anything actually changed, so a dialog dismissed with no edits
        doesn't trigger a pointless rebuild.

        Region 2's part and voice labels are updated IN PLACE
        (rename_part/rename_voice), never via load_score_structure - that
        resets every node back to enabled, discarding whatever mute/solo
        toggles and expand state the user had set.
        """
        music_data = self.music_data
        percussion_changed = bool(
            item_name_overrides
            or item_sound_overrides
            or auto_correct_enabled != music_data.percussion_auto_correct_enabled
        )
        parts_changed = bool(name_overrides or program_overrides)
        if not (parts_changed or percussion_changed):
            return False

        if parts_changed:
            music_data.apply_part_overrides(name_overrides, program_overrides)
            for part_id, name in name_overrides.items():
                self.presenter.rename_part(part_id, name)

        if percussion_changed:
            music_data.percussion_item_name_overrides.update(item_name_overrides)
            music_data.percussion_item_overrides.update(item_sound_overrides)
            music_data.percussion_auto_correct_enabled = auto_correct_enabled
            # Recomputes every percussion item's effective sound AND its
            # voice label (apply_percussion_overrides ends by re-running
            # _set_percussion_voice_names), so the labels read back below
            # are already current.
            music_data.apply_percussion_overrides()
            for part in music_data.parts_info:
                if not part.is_percussion:
                    continue
                for (staff_id, voice_id), label in part.voice_names.items():
                    self.presenter.rename_voice(part.part_id, staff_id, voice_id, label)

        self.presenter.update_timeline_views(play_all=False)
        return True

    # --- Key Signature dialog (S6) -------------------------------------

    def current_key_override(self) -> Tuple[Optional[int], Optional[str]]:
        """(fifths, mode) currently overridden, or (None, None) for "use the
        file's own key" - what the dialog opens on and compares against."""
        return (
            self.music_data.key_signature_override_fifths,
            self.music_data.key_signature_override_mode,
        )

    def apply_key_signature_override(
        self, fifths: Optional[int], mode: Optional[str]
    ) -> bool:
        """Set or clear the whole-piece key override. Returns whether it
        changed.

        Region 1 and the status bar need their own explicit refresh: the
        displayed key isn't part of update_timeline_views' normal scope, and
        for a MIDI score the override also re-spells every note (see
        OverrideManager.apply_key_signature_override).
        """
        if (fifths, mode) == self.current_key_override():
            return False
        self.music_data.apply_key_signature_override(fifths, mode)
        self.presenter.update_timeline_views(play_all=False)
        self.presenter.refresh_region_1()
        self.presenter.update_status_bar()
        return True

    # --- Reorder Parts dialog ------------------------------------------

    def part_rows(self) -> List[Tuple[str, str]]:
        """(part_id, name) per part, in current order - the dialog's list."""
        return [(p.part_id, p.name) for p in self.music_data.parts_info]

    def current_part_order(self) -> List[str]:
        return [p.part_id for p in self.music_data.parts_info]

    def reorder_parts(self, new_order: List[str]) -> bool:
        """Apply a new part order. Returns whether it changed.

        Two halves, both in-place: MusicData.reorder_parts re-sorts every
        slice's notes, and Region 2's rows are moved rather than rebuilt -
        same "never load_score_structure" reasoning as rename_part above.
        """
        if new_order == self.current_part_order():
            return False
        self.music_data.reorder_parts(new_order)
        self.presenter.reorder_parts(new_order)
        self.presenter.update_timeline_views(play_all=False)
        return True
