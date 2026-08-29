# audio/lead_in.py
"""The lead-in count-in before playback starts: which beats click, and when.

A pure function (no Qt, no timers), deliberately split out from
controllers/playback_controller.py for the same reason as
audio/strum_schedule.py - the timing maths is then directly unit-testable
without a real event loop, and the controller only has to walk the schedule
it hands back.

Reported from real practice use: playback used to sound the instant it was
pressed, leaving no time to get hands back onto the guitar. See
models/play_settings.py for the settings this reads.
"""
import math
from typing import List, Tuple

# (offset_ms from the start of the count-in, ts-relative beat position)
LeadInClick = Tuple[int, float]


def build_lead_in_schedule(
    bars: int,
    beats: int,
    ts_num: int,
    ts_den: int,
    bpm: float,
    start_beat_position: float = 1.0,
) -> Tuple[List[LeadInClick], int]:
    """(clicks, total_ms) for a count-in of `bars` bars plus `beats` extra
    beats, ending one beat before the preview's first note.

    bpm is quarter notes per minute - the same units
    MusicData.effective_tempo_bpm returns and Sequencer._delay_ms_to
    consumes - while a BEAT is the time signature's own denominator unit
    (Ref 18), so 4/4 counts quarters and 6/8 counts eighths.

    Beat positions are counted BACKWARDS from the beat the preview starts
    on, so beat 1 of the count-in lands where a real downbeat would: with
    the accent sample on it (audio/metronome.py's click_event_for_beat
    accents beat 1) and the spoken announcer saying the right numbers.
    A count-in of 1 bar + 2 beats in 4/4 ahead of a bar line therefore
    counts "3 4 1 2 3 4", not "1 2 3 4 1 2".

    total_ms includes the final beat, i.e. it is when the preview itself
    should start, not when the last click sounds.
    """
    total_beats = max(0, int(bars)) * max(1, int(ts_num)) + max(0, int(beats))
    if total_beats <= 0 or bpm <= 0:
        return [], 0

    # 4.0 / ts_den quarters per beat: a quarter in 4/4, an eighth in 6/8.
    beat_ms = (4.0 / float(ts_den)) * 60000.0 / float(bpm)

    # Whole beat the preview starts on. Fractional positions can't click
    # (click_event_for_beat only fires on whole beats), so the count-in
    # anchors to the beat containing the start rather than being silent.
    anchor = int(math.floor(start_beat_position)) if start_beat_position >= 1 else 1

    clicks: List[LeadInClick] = []
    for i in range(total_beats):
        beats_before_start = total_beats - i
        position = ((anchor - beats_before_start - 1) % max(1, int(ts_num))) + 1
        clicks.append((int(round(i * beat_ms)), float(position)))

    return clicks, int(round(total_beats * beat_ms))
