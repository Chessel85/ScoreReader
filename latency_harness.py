# latency_harness.py
"""E10/Ref 9 AC3/NFR-04: manual latency benchmark against real audio
hardware - NOT a pytest test. tests/conftest.py's autouse _forbid_real_audio
fixture deliberately blocks constructing a real SynthEngine in every test
(D-7), and pytest.ini scopes discovery to testpaths = tests anyway, so this
lives at the repo root and is run by hand:

    .venv\\Scripts\\python.exe latency_harness.py

Replaces the version recovered from git history (git show
520f743:test_midi_latency.py), which sent a MIDI message through `mido` to
an external port - mido is gone since the switch to in-process FluidSynth
(CLAUDE.md). Same measurement philosophy as that original: Python-side
dispatch time from deciding to play a note to the underlying synth call
returning. True acoustic latency past that point isn't measurable without a
mic/loopback rig, so this reports dispatch overhead against the 25ms budget
(Ref 9 AC3) - a human runs it and reads the numbers, same as the original,
there is no hardware-backed CI to assert against.

Two measurements:
1. Per-note dispatch latency (Ref 9 AC3) - SynthEngine.play_notes/play_click.
2. Sequencer scheduling jitter (NFR-04 AC-04.2) - the first time this class
   of measurement exists in the repo; E4-E7's own tests only prove
   scheduling *correctness* (right delays computed) using a FakeTimer, not
   real-world timing accuracy under Qt's actual event loop.
"""
import os
import statistics
import time

os.environ.setdefault("QT_QPA_PLATFORM", "windows")

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from audio.metronome import (
    METRONOME_ACCENT_VELOCITY,
    METRONOME_CHANNEL,
    METRONOME_CLAVES_PITCH,
    METRONOME_GM_PROGRAM,
)
from audio.sequencer import Sequencer
from audio.synth_engine import SynthEngine
from models.music_data import MusicData

FIXTURE = os.path.join("tests", "fixtures", "minimal_4_4.musicxml")  # C D E F, one 4/4 bar
LATENCY_BUDGET_MS = 25.0
ITERATIONS = 50


def _ms(seconds: float) -> float:
    return seconds * 1000.0


def measure_dispatch_latency(synth: SynthEngine) -> None:
    print(f"\n--- Per-note dispatch latency ({ITERATIONS} iterations) ---")

    note_times = []
    for _ in range(ITERATIONS):
        t0 = time.perf_counter()
        synth.play_notes(midi_notes=[60], duration_ms=50, channel=0, program=0)
        note_times.append(_ms(time.perf_counter() - t0))
        synth.stop_all_notes()

    click_times = []
    for _ in range(ITERATIONS):
        t0 = time.perf_counter()
        synth.play_click(METRONOME_CHANNEL, METRONOME_GM_PROGRAM, METRONOME_CLAVES_PITCH, METRONOME_ACCENT_VELOCITY, 40)
        click_times.append(_ms(time.perf_counter() - t0))

    for label, times in (("play_notes", note_times), ("play_click", click_times)):
        print(
            f"  {label}: min={min(times):.3f}ms  max={max(times):.3f}ms  "
            f"mean={statistics.mean(times):.3f}ms  budget={LATENCY_BUDGET_MS}ms"
        )
        if max(times) > LATENCY_BUDGET_MS:
            print(f"  WARNING: {label} exceeded the {LATENCY_BUDGET_MS}ms budget (Ref 9 AC3)")


def measure_sequencer_jitter(synth: SynthEngine) -> None:
    print("\n--- Sequencer scheduling jitter (real QTimer, real wall clock) ---")

    md = MusicData(file_path=FIXTURE, tempo_bpm=240)  # fast, so the harness finishes quickly
    seq = Sequencer(md, synth)

    step_times = []
    requested_delays = []

    def _on_step(_index):
        step_times.append(time.perf_counter())

    original_start = Sequencer._delay_ms_to

    def _tracking_delay_ms_to(self, next_index):
        delay = original_start(self, next_index)
        requested_delays.append(delay)
        return delay

    Sequencer._delay_ms_to = _tracking_delay_ms_to
    seq.step_played.connect(_on_step)

    loop = QEventLoop()
    seq.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)  # safety timeout

    seq.play_from(0)
    loop.exec()

    Sequencer._delay_ms_to = original_start
    synth.stop_all_notes()

    if len(step_times) < 2:
        print("  Not enough steps recorded - fixture too short or playback didn't complete.")
        return

    actual_deltas_ms = [_ms(b - a) for a, b in zip(step_times, step_times[1:])]
    jitter_ms = [actual - requested for actual, requested in zip(actual_deltas_ms, requested_delays)]

    print(f"  steps={len(step_times)}  requested_delays_ms={[round(d, 1) for d in requested_delays]}")
    print(f"  actual_deltas_ms={[round(d, 1) for d in actual_deltas_ms]}")
    print(
        f"  jitter: min={min(jitter_ms):.3f}ms  max={max(jitter_ms):.3f}ms  "
        f"mean={statistics.mean(jitter_ms):.3f}ms (NFR-04 AC-04.2, low jitter expected)"
    )


def main():
    app = QCoreApplication([])

    synth = SynthEngine()
    if synth._fs is None:
        print(
            "[WARN] Real FluidSynth engine did not start (missing bin/ DLLs or "
            "soundfonts/FluidR3_GM.sf2 - see CLAUDE.md's 'Local binaries' section). "
            "Numbers below only measure the no-op fallback path, not real dispatch "
            "latency - they are meaningless for Ref 9/NFR-04."
        )

    measure_dispatch_latency(synth)
    measure_sequencer_jitter(synth)

    synth.close()


if __name__ == "__main__":
    main()
