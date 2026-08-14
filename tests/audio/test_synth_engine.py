# tests/audio/test_synth_engine.py
"""SynthEngine note bookkeeping, exercised without a real engine.

Instances are built with object.__new__ and their state set by hand, rather
than constructed normally: SynthEngine.__init__ opens WASAPI, which the
autouse guard in conftest deliberately blocks (D-7). What's under test here
is the pure bookkeeping around _active_notes, so a recording stand-in for
self._fs is all the engine that's needed.
"""
from audio.synth_engine import SynthEngine


class _RecordingFluidSynth:
    def __init__(self):
        self.note_offs = []

    def noteoff(self, channel, note):
        self.note_offs.append((channel, note))


def _engine():
    engine = object.__new__(SynthEngine)
    engine._fs = _RecordingFluidSynth()
    engine._active_notes = []
    engine._group_off_timers = []
    return engine


def test_expiring_group_does_not_silence_another_group_holding_the_same_note():
    """R16: two voices of one part sounding a unison land on that part's
    single channel at the same pitch, so (channel, note) legitimately appears
    in _active_notes twice - once per group, each with its own duration and
    its own timer.

    _stop_group used to release the first matching entry, so the shorter
    voice's expiry sent noteoff for a pitch the longer voice was still
    holding: the note stopped early and a stale entry was left behind for
    stop_all_notes to release a second time. This is the same class of bug
    play_chord already carries two scars from (one group's timing clobbering
    another's), one level further down.
    """
    engine = _engine()
    short_group = [(0, 60)]
    long_group = [(0, 60)]
    engine._active_notes.extend(short_group + long_group)

    engine._stop_group(short_group, timer=None)

    assert engine._fs.note_offs == [], "the other group is still holding this note"
    assert engine._active_notes == [(0, 60)], "only this group's claim is released"

    engine._stop_group(long_group, timer=None)

    assert engine._fs.note_offs == [(0, 60)], "last claim released -> note actually stops"
    assert engine._active_notes == []


def test_expiring_group_releases_notes_no_other_group_holds():
    """The ordinary case: distinct pitches stop as soon as their own group
    expires, with no reference counting getting in the way."""
    engine = _engine()
    group = [(0, 60), (0, 64)]
    engine._active_notes.extend(group)

    engine._stop_group(group, timer=None)

    assert sorted(engine._fs.note_offs) == [(0, 60), (0, 64)]
    assert engine._active_notes == []


def test_stopping_a_group_is_safe_with_no_engine():
    """A build with no FluidSynth available (missing DLLs/soundfont) still
    runs every playback call as a no-op - the timer bookkeeping must be
    cleaned up regardless."""
    engine = _engine()
    engine._fs = None
    timer = object()
    engine._group_off_timers.append(timer)

    engine._stop_group([(0, 60)], timer=timer)

    assert engine._group_off_timers == []
