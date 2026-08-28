# models/timeline_build.py
"""S2: the shape a timeline builder hands back to MusicData.

Every one of the four builders (MusicXML, MIDI, Guitar Pro, Ultimate
Guitar) already published this same set of attributes; MusicData read all
twelve off whichever builder it had just constructed. Naming the shape here,
in models/, is what lets the DISPATCH live in parsers/ (where knowing which
file format needs which builder belongs) while models/ still owns the
contract - the direction of the dependency is then parsers -> models, like
every other module pair.

`apply_to(music_data)` rather than a caller-side unpack: the twelve fields
must all land, and a field added to a builder but forgotten here would
silently read as its dataclass default. One assignment site keeps that
honest.
"""
from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class TimelineBuild:
    """A parsed score's timeline plus the sparse side-channel markers that
    accompany it (tempo changes, repeat/ending/hairpin spans, Segno/Coda/
    D.C./D.S./Fine marks). MIDI/GP/UG leave most of the marker lists empty -
    there is nothing in those formats that encodes them."""

    timeline_slices: List[Any] = field(default_factory=list)
    tempo_changes: List[Any] = field(default_factory=list)
    # Whole-beat placeholder slices the metronome splices in (Ref 14 AC4).
    # Kept off timeline_slices until set_metronome_enabled asks for them.
    beat_markers: List[Any] = field(default_factory=list)
    repeat_spans: List[Any] = field(default_factory=list)
    ending_spans: List[Any] = field(default_factory=list)
    hairpin_spans: List[Any] = field(default_factory=list)
    # P3: <direction>/<direction-type> spans (pedal, octave shift, dashed/
    # bracketed lines) and points (rehearsal, pedal change, D6 catch-all).
    # Collected per part, not first-part-only (D5).
    direction_spans: List[Any] = field(default_factory=list)
    direction_marks: List[Any] = field(default_factory=list)
    segno_marks: List[Any] = field(default_factory=list)
    coda_marks: List[Any] = field(default_factory=list)
    to_coda_marks: List[Any] = field(default_factory=list)
    fine_marks: List[Any] = field(default_factory=list)
    navigation_jumps: List[Any] = field(default_factory=list)
    # The whole-score bar count - deliberately NOT derived from
    # timeline_slices, which would undercount a trailing all-rest measure
    # (rests never get a slice of their own).
    total_measures: int = 0

    @classmethod
    def from_builder(cls, builder) -> "TimelineBuild":
        """Run `builder` and collect everything it publishes. build() must
        be called first - the marker/span lists are populated as a side
        effect of the walk, not at construction."""
        slices = builder.build()
        return cls(
            timeline_slices=slices,
            tempo_changes=builder.tempo_changes,
            beat_markers=builder.beat_markers,
            repeat_spans=builder.repeat_spans,
            ending_spans=builder.ending_spans,
            hairpin_spans=builder.hairpin_spans,
            direction_spans=builder.direction_spans,
            direction_marks=builder.direction_marks,
            segno_marks=builder.segno_marks,
            coda_marks=builder.coda_marks,
            to_coda_marks=builder.to_coda_marks,
            fine_marks=builder.fine_marks,
            navigation_jumps=builder.navigation_jumps,
            total_measures=builder.total_measures,
        )

    def apply_to(self, music_data) -> None:
        """Write every field onto the MusicData being constructed."""
        music_data.timeline_slices = self.timeline_slices
        music_data.tempo_changes = self.tempo_changes
        music_data._beat_markers = self.beat_markers
        music_data.repeat_spans = self.repeat_spans
        music_data.ending_spans = self.ending_spans
        music_data.hairpin_spans = self.hairpin_spans
        music_data.direction_spans = self.direction_spans
        music_data.direction_marks = self.direction_marks
        music_data.segno_marks = self.segno_marks
        music_data.coda_marks = self.coda_marks
        music_data.to_coda_marks = self.to_coda_marks
        music_data.fine_marks = self.fine_marks
        music_data.navigation_jumps = self.navigation_jumps
        music_data.total_measures = self.total_measures
