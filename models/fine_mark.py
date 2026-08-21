# models/fine_mark.py
from dataclasses import dataclass


@dataclass
class FineMark:
    """A "Fine" direction (<direction>/<direction-type>/<words>"Fine"</words>,
    or a <sound fine="yes"> attribute), in measure numbers. MuseScore writes
    this at the END of its measure. Per the MusicXML spec, a fine mark only
    takes effect "the second time through" - i.e. only after a NavigationJump
    has already fired once this playback run (see MusicData.next_playback_index),
    at which point reaching it ends the run the same way running off the end
    of the piece does. Populated by TimelineBuilder._scan_first_part as a
    side effect of build(), the same pattern as TempoChange/tempo_changes."""

    measure: int
