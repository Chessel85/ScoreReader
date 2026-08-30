# models/strum_pattern.py
"""One Ultimate Guitar strumming pattern - a named list of slot codes plus
the subdivision/tempo needed to place those slots in real time.

UG's `tab_view.strummings` is a LIST (6 of the 18 example tabs carry 2-3
entries), each `{part, denuminator, bpm, is_triplet, measures[]}` where
`measures` is really the flat list of slot codes (misnamed in the source).
`part` is free text naming where the pattern is used ("Verse", "Chorus",
"Intro + Verse", sometimes ""); there is no machine-readable link from a
pattern to specific bars, so it is only ever reported as written.

Pure data + arithmetic, no Qt, no parser imports - same category as
models/strum_codes.py. The strum-code -> spoken-word decode is in
models/strum_codes.slot_words; the beat-position vocabulary shared with the
talking metronome is models/beat_position_words.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from models.beat_position_words import FRACTIONAL_BEAT_WORDS
from models.strum_codes import slot_words

# 4/4 is assumed throughout - UG never states a time signature (see
# parsers/ug_timeline_builder.py's own note on fabricated bars).
_BEATS_PER_BAR = 4


@dataclass
class StrumPattern:
    name: str
    bpm: Optional[int]
    # UG's `denuminator`: the slot subdivision, 4 (quarter) / 8 (eighth) /
    # 16 (sixteenth). None for a v1 .ug file, which never stored it - the
    # dialog then degrades to "slot N" labels for that one file.
    denominator: Optional[int]
    is_triplet: bool
    codes: List[int] = field(default_factory=list)

    def slots_per_bar(self) -> int:
        """How many slots make up one 4/4 bar. Non-triplet: the denominator
        itself (16 sixteenths / 8 eighths / 4 quarters per bar) - confirmed
        against real data (a 32-slot denominator-16 pattern is 2 bars, an
        8-slot denominator-4 pattern is 2 bars). Triplet: 3 slots per beat,
        12 per bar - no real triplet example exists among the 18 tabs, so
        this is the musically-sensible default rather than a verified fit."""
        if not self.denominator:
            return max(1, len(self.codes))
        if self.is_triplet:
            return 3 * _BEATS_PER_BAR
        return self.denominator

    def bar_count(self) -> int:
        spb = self.slots_per_bar()
        if spb <= 0:
            return 1
        return max(1, round(len(self.codes) / spb))

    def slot_ms(self) -> float:
        """Real duration of one slot, from bpm (quarter-note BPM) and the
        subdivision. bpm falls back to 120 when absent."""
        return self.slot_ms_at_bpm(self.bpm or 120)

    def slot_ms_at_bpm(self, quarter_bpm: float) -> float:
        """slot_ms with an explicit quarter-note BPM - the Strumming Patterns
        dialog's demo plays at the user's chosen playback tempo, not the
        pattern's own imported bpm."""
        bpm = quarter_bpm or 120
        spb = self.slots_per_bar()
        bar_ms = _BEATS_PER_BAR * 60000.0 / bpm
        return bar_ms / spb if spb else bar_ms

    def subdivision_name(self) -> str:
        """Human phrase for the dialog's pattern combo."""
        if not self.denominator:
            return "unknown subdivision"
        base = {4: "quarter notes", 8: "eighth notes", 16: "sixteenth notes"}.get(
            self.denominator, f"1/{self.denominator} notes"
        )
        if self.is_triplet:
            base = base.replace(" notes", " note triplets")
        return base

    def slot_labels(self) -> List[str]:
        """The time-position label for each slot ("1", "1 e", "1 and",
        "1 a", "2", ...), consistent with the talking metronome's own
        vocabulary. "Bar N, " is prefixed only when the pattern spans more
        than one bar. A v1 file with no denominator falls back to
        "slot 1", "slot 2", ..."""
        n = len(self.codes)
        if not self.denominator:
            return [f"slot {i + 1}" for i in range(n)]

        spb = self.slots_per_bar()
        bars = self.bar_count()
        labels: List[str] = []
        for i in range(n):
            bar = i // spb + 1 if spb else 1
            within = i % spb if spb else i
            if self.is_triplet:
                beat = within // 3 + 1
                sub = within % 3
                pos = str(beat) if sub == 0 else f"{beat} {'and' if sub == 1 else 'a'}"
            else:
                slots_per_beat = spb / _BEATS_PER_BAR
                beat_position = within / slots_per_beat + 1 if slots_per_beat else 1.0
                pos = self._beat_position_label(beat_position)
            labels.append(f"Bar {bar}, {pos}" if bars > 1 else pos)
        return labels

    @staticmethod
    def _beat_position_label(beat_position: float) -> str:
        whole = int(round(beat_position)) if abs(beat_position - round(beat_position)) < 0.01 else int(beat_position)
        frac = round(beat_position - whole, 2)
        if frac == 0:
            return str(whole)
        word = FRACTIONAL_BEAT_WORDS.get(frac)
        return f"{whole} {word}" if word else str(round(beat_position, 2))

    def slot_rows(self) -> List[str]:
        """One combined row per slot for the dialog's list: the time
        position and the stroke, e.g. "Bar 1, 1: down", "Bar 1, 1 e:
        pause", "Bar 1, 1 and: up muted"."""
        return [
            f"{label}: {slot_words(code)}"
            for label, code in zip(self.slot_labels(), self.codes)
        ]
