# models/navigation_jump.py
from dataclasses import dataclass
from typing import Optional


@dataclass
class NavigationJump:
    """A Da Capo or Dal Segno direction (<direction>/<direction-type>/<words>
    "D.C."/"D.S."</words>, or a <sound dacapo="yes"|dalsegno="..."> attribute),
    in measure numbers. MuseScore writes this at the END of its measure.

    kind is "dacapo" (jump to the piece's true first measure - MusicData.
    _dacapo_target_measure, which is measure 0 rather than 1 when the piece
    opens with a pickup bar, Ref 17) or "dalsegno" (jump to the SegnoMark
    whose label matches target_label). target_label is None for a dacapo
    jump (its target needs no label - there is only ever one "start of the
    piece") and the segno's label (defaulting to "1") for a dalsegno jump.

    Fires at most once per playback run (MusicData.next_playback_index /
    PlaybackJumpState.jump_taken) - inner repeats are not retaken, and
    ToCodaMark/FineMark only take effect, after this fires once, per the
    MusicXML spec's own "second time through" wording. Populated by
    TimelineBuilder._scan_first_part as a side effect of build(), the same
    pattern as TempoChange/tempo_changes."""

    measure: int
    kind: str  # "dacapo" or "dalsegno"
    target_label: Optional[str]
