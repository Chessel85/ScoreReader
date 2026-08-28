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

    # P1 (find_feature_plan.md) - note-attached notations made findable.
    # All Optional[str], populated only by TimelineBuilder (MusicXML);
    # the MIDI/GP/UG builders never set them, so they stay None there.
    # Absence is the mechanism Region 3/4/Find use to know not to render
    # a row - same convention as string/fret/dynamic above.
    #
    # tie   - notations/tied type(s): "start" / "stop" / "start, stop"
    # slur  - notations/slur type(s): "start" / "stop"
    # tuplet- time-modification: "triplet" / "5 in the time of 4"
    # fermata - notations/fermata: "fermata" (+ shape when not normal)
    # arpeggio - notations/arpeggiate|non-arpeggiate, CHORD notes only
    #            (D7): "arpeggio up" / "arpeggio down" / "arpeggio" /
    #            "non-arpeggio"
    # accidental - a <accidental> child, ONLY when cautionary="yes" or
    #              editorial="yes" (D14): "cautionary sharp", ...
    # technique - notations/technical child(ren) beyond fret/string/
    #             fingering/pluck, comma-joined spoken names
    # glissando - notations/glissando|slide: "glissando start", ...
    # grace - a spoken summary of grace_notes ("acciaccatura" /
    #         "appoggiatura", comma-joined) - distinct from the list
    #         above, which drives the "A grace B" step rendering
    # other_notation - D6 catch-all: any unrecognised <notations> child
    #                  tag, hyphens as spaces
    #
    # P2 (find_feature_plan.md) - chord symbols/diagrams made findable.
    # chord_symbol - the chord label ("G7", "F/C") on a synthetic Chords
    #                part/voice note. Duplicates what `step` already holds,
    #                but `step` is a CORE_ATTRIBUTE_KEYS key Find never
    #                offers - a separate key is what makes it findable.
    #                Set by TimelineBuilder (<harmony>), UgTimelineBuilder
    #                ([ch] markup) and GpTimelineBuilder (chord diagram
    #                name) on their own synthetic chord entries.
    # chord_diagram - a spoken chord-shape summary from MusicXML
    #                 harmony/frame ("frets 3 2 0 0 0 1", "x" for a muted
    #                 string, "barre at fret N"/"from fret N" suffixes).
    tie: Optional[str] = None
    slur: Optional[str] = None
    tuplet: Optional[str] = None
    fermata: Optional[str] = None
    arpeggio: Optional[str] = None
    accidental: Optional[str] = None
    technique: Optional[str] = None
    glissando: Optional[str] = None
    grace: Optional[str] = None
    other_notation: Optional[str] = None
    chord_symbol: Optional[str] = None
    chord_diagram: Optional[str] = None
