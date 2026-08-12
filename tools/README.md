# tools/

Standalone utilities, independent of the main Recall Score application -
each one is self-contained (stdlib only, no dependency on `models/`,
`parsers/`, `audio/`, etc.) so it can be run and maintained on its own.

## wav_to_sf2.py

Builds a `.sf2` soundfont from WAV samples, driven by a plain-text `.ini`
config file - no GUI soundfont editor needed. Built for un-pitched
one-shot sounds (spoken words, click sounds): every sample plays back at
its own recorded pitch/speed regardless of which MIDI note triggers it,
the same way a drum kit or GM percussion works, not a normal instrument
that gets pitch-shifted across a keyboard range.

```
python tools/wav_to_sf2.py my_config.ini
```

Produces a single `.sf2` file - no sidecar. An earlier version also wrote
a `.sf2.json` listing each sample's own natural duration, so the consuming
code (`audio/synth_engine.py`) could hold a one-shot sample's MIDI note on
for at least that long before releasing it - a one-shot sample only plays
to its natural end if held that long, and there's no score to read a
duration from for these. That turned out to be unnecessary: FluidSynth
deactivates a one-shot (non-looping) voice on its own once the sample's
data is exhausted, regardless of whether a note-off was ever sent, so the
consuming code just avoids releasing the note early instead - see
`audio/synth_engine.py`'s `play_click()` for how this was verified.

See the full config file format, including the MIDI note number/note name
conventions, in the script's own module docstring (`python
tools/wav_to_sf2.py --help`), and `example_config.ini` for a ready-to-copy
starting template - it already uses the note layout `audio/
position_announcer.py` (Ref 28) expects for the talking metronome's ten
words and the click metronome's two sounds, so pointing its WAV paths at
real recordings is enough to get a working sound pack with no code
changes.

Multiple sound packs can coexist in one `.sf2`/config - add more
`[preset:...]` sections, each its own bank/program, for alternative
voices or click sounds; the app switches between them via MIDI program
select, same as it already does for a score's own GM instruments.

Verified against real FluidSynth (not just "the bytes parse") while
building it: loaded a generated test `.sf2` through `fluidsynth.Synth`,
triggered several notes across two presets, and measured the actual
rendered audio to confirm both correct sample selection per
note/bank/program and that nothing gets pitch-shifted.
