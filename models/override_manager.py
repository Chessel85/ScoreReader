# models/override_manager.py
"""S1 extraction: every user-set override that mutates already-parsed notes
and parts in place - part name/instrument (S5), percussion item name/sound
(wishlist #8), and the whole-piece key signature (S6).

What these have in common, and why they belong together: each is applied
from two places (the relevant dialog's OK, and apply_config() restoring a
saved .rsc), each mutates _real_timeline_slices/parts_info rather than
re-parsing, and each is re-derivable from an immutable original the parser
recorded (percussion_source_key, file_key_fifths) so clearing an override
is lossless with no reload.

Holds a reference back to its MusicData and owns no state - the override
dicts themselves stay fields on MusicData, since export_config() persists
them and callers mutate them directly. MusicData keeps a delegator for
every method here.
"""
from typing import Dict, List, Optional, Tuple

from models.gm_percussion_map import detect_percussion_key_shift
from models.pitch_spelling import spell_pitch


class OverrideManager:
    def __init__(self, data):
        self.data = data

    # --- part name / instrument (S5) ----------------------------------

    def apply_part_overrides(
        self, name_overrides: Dict[str, str], program_overrides: Dict[str, int]
    ) -> None:
        """S5: the instrument dialog's OK, and apply_config() restoring a
        saved score. Mutates PartStructureInfo in place - every other
        reader (get_score_structure, mixer_rows, get_gmidi_program_for_part,
        get_playback_events_for_indices) already reads parts_info live, so
        this is enough to make a renamed/reprogrammed part show and sound
        correctly everywhere with no further wiring.

        NoteData.part_name is kept in sync explicitly: TimelineBuilder/
        MidiTimelineBuilder bake it in at parse time from parts_info's name
        at THAT moment, and get_performance_report_lines joins the two by
        matching text - the exact "two independent copies of a name have to
        agree verbatim" bug class R5 fixed for the reader's own two XML
        passes (see CLAUDE.md). Renaming only parts_info and not the
        already-built notes would silently reopen it.
        """
        data = self.data
        data.part_name_overrides.update(name_overrides)
        data.part_program_overrides.update(program_overrides)
        for p in data.parts_info:
            if p.part_id in name_overrides:
                p.name = name_overrides[p.part_id]
            if p.part_id in program_overrides:
                p.gmidi_program = program_overrides[p.part_id]
        if name_overrides:
            for n in self._all_notes():
                if n.part_id in name_overrides:
                    n.part_name = name_overrides[n.part_id]

    # --- percussion items (wishlist #8) -------------------------------

    def set_percussion_voice_names(self) -> None:
        """Wishlist #8 follow-up: a percussion voice's label is its one
        item's display name ("Closed Hi-Hat") instead of the generic
        "Voice N" - the same voice_names override slot Guitar Pro's
        synthetic Chords voice already uses to show "Chords" instead of
        "Voice 1" (parsers/gp_reader.py). Each voice holds exactly one
        item by construction (TimelineBuilder/MidiTimelineBuilder set
        NoteData.voice to the item's own declared key - see there - so two
        different items can never share one voice number), which is also
        why both readers already set this same label directly at parse
        time; this exists as (a) a safety net and (b) the refresh path
        after an Instruments-dialog rename, called again at the end of
        apply_percussion_overrides so a rename is picked up.
        """
        data = self.data
        names_by_voice: Dict[Tuple[str, int, int], str] = {}
        for n in self._percussion_notes():
            names_by_voice[(n.part_id, n.staff, n.voice)] = n.step_name
        for part in data.parts_info:
            for staff, voices in part.staves_voices.items():
                for voice in voices:
                    name = names_by_voice.get((part.part_id, staff, voice))
                    if name:
                        part.voice_names[(staff, voice)] = name

    def get_percussion_items_for_part(
        self, part_id: str
    ) -> List[Tuple[Tuple[str, int], str, int]]:
        """(item_key, current display name, current effective sounding key)
        for every distinct percussion item in this part, in first-seen
        order - the row list widgets/instrument_dialog.py builds for a
        percussion part. item_key is exactly what
        percussion_item_overrides/percussion_item_name_overrides are keyed
        by, so a row's edits can be written straight back without any
        further lookup."""
        seen: Dict[Tuple[str, int], Tuple[str, int]] = {}
        for n in self._percussion_notes():
            if n.part_id != part_id:
                continue
            item_key = (n.part_id, n.percussion_source_key)
            if item_key not in seen:
                seen[item_key] = (n.step_name, n.midi_pitch)
        return [(key, name, sounding_key) for key, (name, sounding_key) in seen.items()]

    def apply_percussion_overrides(self) -> None:
        """Wishlist #8 follow-up: (re)applies percussion_item_overrides/
        percussion_item_name_overrides/percussion_auto_correct_enabled to
        every percussion note - called from apply_config() (restoring a
        saved score) and after the Instruments dialog's OK.

        Priority per item, highest first: an explicit
        percussion_item_overrides entry > auto-correct (only when
        percussion_auto_correct_enabled, and only for a MusicXML-sourced
        note - a MIDI note's name is already derived FROM its key, so it can
        never disagree with it) > the file's own original
        percussion_source_key. Always re-derived from percussion_source_key,
        never from the note's own possibly-already-overridden midi_pitch -
        so toggling the checkbox off, or clearing an item override, is
        lossless with no re-parse (the same role file_key_fifths plays for
        apply_key_signature_override).

        Auto-correct applies ONE shift per PART (models.gm_percussion_map.
        detect_percussion_key_shift), not a per-item name guess - see that
        function's docstring for why a short name like "Snare" can't be
        reliably matched to a GM name on its own. Two passes: names first
        (so a user rename is what shift-detection and any later re-open of
        the dialog both see), then the shift is detected per part from the
        now-current names, then sounds are resolved.
        """
        data = self.data

        for n in self._percussion_notes():
            item_key = (n.part_id, n.percussion_source_key)
            if item_key in data.percussion_item_name_overrides:
                n.step_name = data.percussion_item_name_overrides[item_key]

        shift_by_part = self._detected_shifts()

        for n in self._percussion_notes():
            item_key = (n.part_id, n.percussion_source_key)
            if item_key in data.percussion_item_overrides:
                n.midi_pitch = data.percussion_item_overrides[item_key]
                continue
            shift = shift_by_part.get(n.part_id)
            if shift is not None:
                n.midi_pitch = n.percussion_source_key - shift
            else:
                n.midi_pitch = n.percussion_source_key

        self.set_percussion_voice_names()

    def _detected_shifts(self) -> Dict[str, Optional[int]]:
        """The auto-correct shift per part, or an empty mapping when
        auto-correct is off or the score is MIDI (where a percussion note's
        name is derived FROM its key and so can never disagree with it -
        see the class docstring and apply_percussion_overrides above)."""
        data = self.data
        if not data.percussion_auto_correct_enabled or data.is_midi:
            return {}
        items_by_part: Dict[str, List[Tuple[str, int]]] = {}
        for n in self._percussion_notes():
            items_by_part.setdefault(n.part_id, []).append(
                (n.step_name, n.percussion_source_key)
            )
        return {
            part_id: detect_percussion_key_shift(items)
            for part_id, items in items_by_part.items()
        }

    # --- key signature (S6) -------------------------------------------

    def apply_key_signature_override(
        self, fifths: Optional[int], mode: Optional[str]
    ) -> None:
        """S6: the Instruments & Key dialog's OK, and apply_config()
        restoring a saved score. fifths=None clears the override, back to
        the file's own key(s).

        For a MIDI-loaded score, also re-spells every note against the new
        fifths - MIDI has no real notation to derive spelling from
        (models/pitch_spelling.py's spell_pitch is a bare pitch-class
        table), so a wrong or missing file key produces wrong
        enharmonic spelling until corrected here. Symmetric by design:
        clearing the override re-derives each note's spelling from its own
        file_key_fifths (the fifths MidiTimelineBuilder actually spelled it
        against at parse time) rather than a separate cached "original text"
        - so this needs no distinct restore path.

        MusicXML notes are never touched - their spelling comes straight
        from the file's own <step>/<alter> and never depended on key in the
        first place. This only ever changes what key is DISPLAYED for an
        XML score (get_region_1_data/get_status_bar_fields)."""
        data = self.data
        data.key_signature_override_fifths = fifths
        data.key_signature_override_mode = mode if fifths is not None else None
        if not data.is_midi:
            return
        for n in self._all_notes():
            if n.midi_pitch is None or n.file_key_fifths is None:
                continue
            effective = fifths if fifths is not None else n.file_key_fifths
            n.step_name, _ = spell_pitch(n.midi_pitch, effective)

    # --- shared note walks ---------------------------------------------

    def _all_notes(self):
        """Every note in the real (marker-free) timeline.

        _real_timeline_slices doesn't exist yet during the
        set_percussion_voice_names() call __post_init__ makes (it's
        assigned just after) - timeline_slices is exactly it at that
        moment too, since metronome markers are only ever spliced in later
        via set_metronome_enabled."""
        data = self.data
        slices = getattr(data, "_real_timeline_slices", data.timeline_slices)
        for s in slices:
            for n in s.notes:
                yield n

    def _percussion_notes(self):
        """_all_notes() restricted to notes carrying a percussion item
        identity. Every percussion pass below walked the full timeline with
        its own inline `if n.percussion_source_key is None: continue` -
        five copies of the same skip."""
        for n in self._all_notes():
            if n.percussion_source_key is not None:
                yield n
