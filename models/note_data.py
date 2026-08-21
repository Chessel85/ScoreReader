# note_data.py
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class GraceNote:
    """One grace note attached to the NoteData it leads into (see
    NoteData.grace_notes) - never bucketed into its own EventSlice, since a
    grace note has no <duration> of its own and would otherwise land at the
    exact same (measure, offset) as the note it decorates, rendering as a
    phantom chord tone (reported bug, MusicXML <grace> support).

    slash=True is an acciaccatura (MusicXML <grace slash="yes"/>, a
    "crushed" grace note played just before the beat); slash=False is an
    appoggiatura (<grace/> with no slash, traditionally a longer grace note
    that takes real time from the following main note). Both are realized
    identically for now - a brief pre-note before the main note - see
    audio/grace_note_schedule.py.
    """

    step_name: str
    midi_pitch: Optional[int]
    slash: bool


@dataclass
class NoteData:
    step_name: str
    measure: int
    beat_position: float
    ts_duration: float
    quarter_length: float
    part_id: str
    part_name: str
    staff: int
    voice: int
    octave: Optional[int] = None
    midi_pitch: Optional[int] = None
    fret: Optional[int] = None
    string: Optional[int] = None
    dynamic: Optional[str] = None
    articulation: Optional[str] = None
    fingering: Optional[str] = None
    pluck: Optional[str] = None
    duration_name_us: Optional[str] = None
    # Guitar Pro import: strum direction ("down stroke"/"up stroke"), set
    # only on the rare beat where GP records one explicitly - never
    # inferred (see CLAUDE.md / the GP import plan's "leave unstated"
    # decision).
    strum: Optional[str] = None
    # Guitar Pro import: the full set of MIDI pitches sounding at this
    # event, populated only on the synthetic Chords voice's one-note-per-
    # strum events (see parsers/gp_timeline_builder.py). midi_pitch above
    # still holds a single representative pitch (for sort order); this
    # field is what get_playback_events_for_indices/get_midi_notes_for_indices
    # use to sound the whole chord instead of just one note. Never
    # displayed as an attribute.
    chord_pitches: Optional[List[int]] = None
    # S6: the fifths value MidiTimelineBuilder actually spelled this note
    # against (None for MusicXML, whose spelling never depends on key at
    # all). Lets MusicData.apply_key_signature_override re-derive a MIDI
    # note's own original spelling when the override is cleared, with no
    # re-parse and no separate cached "original text" field.
    file_key_fifths: Optional[int] = None
    # Wishlist #8 follow-up: a percussion note's ORIGINAL, file-declared
    # sounding key (MusicXML's <midi-unpitched>, or the raw MIDI note
    # number) - None for every non-percussion note. midi_pitch itself stays
    # mutable (the EFFECTIVE playback key, changed by
    # MusicData.apply_percussion_overrides), so this is what lets an
    # override/auto-correction be losslessly reverted - the same role
    # file_key_fifths plays for a MIDI note's spelling.
    percussion_source_key: Optional[int] = None
    # One or more grace notes performed immediately before this note (Ref
    # MusicXML <grace> support). Attached here rather than given their own
    # NoteData/EventSlice entry - see GraceNote's own docstring. None for
    # every ordinary note; never set on a grace note itself (a grace note
    # doesn't get a NoteData of its own at all).
    grace_notes: Optional[List[GraceNote]] = None
