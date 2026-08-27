# models/pitch_spelling.py
"""S2: turning a raw MIDI pitch number into a spoken-friendly note name and
octave.

Moved here from parsers/midi_timeline_builder.py, where it was the private
`_spell_pitch`. Two modules need it and they sit on opposite sides of the
parser boundary: MidiTimelineBuilder spells notes at parse time, and
OverrideManager re-spells them whenever the user sets or clears a key
signature override (S6). models/ importing a PRIVATE name out of parsers/
was the wrong direction twice over; this is pitch arithmetic over a fixed
table, not parsing, so models/ is where it belongs.

MusicXML/Guitar Pro notes never come through here - both formats carry their
own notated spelling, which is never re-derived (see
MusicData.apply_key_signature_override).
"""
from typing import Tuple

# Enharmonic spelling is a simplification, not full scale-degree spelling:
# a non-negative key signature (sharps or C major) spells every chromatic
# note with a sharp, a flat key signature spells with a flat - the same
# convention most quick MIDI-to-notation tools use. Good enough for a
# screen-reader note name; not degree-accurate for exotic modes.
PITCH_CLASS_SHARP = [
    "C", "C sharp", "D", "D sharp", "E", "F",
    "F sharp", "G", "G sharp", "A", "A sharp", "B",
]
PITCH_CLASS_FLAT = [
    "C", "D flat", "D", "E flat", "E", "F",
    "G flat", "G", "A flat", "A", "B flat", "B",
]


def spell_pitch(midi_pitch: int, fifths: int) -> Tuple[str, int]:
    """(spoken note name, octave) for a MIDI pitch under a key signature.

    NoteData.file_key_fifths records which `fifths` a note was actually
    spelled against, so clearing a key override can re-derive the original
    spelling losslessly with no re-parse.
    """
    pc = midi_pitch % 12
    octave = midi_pitch // 12 - 1
    names = PITCH_CLASS_FLAT if fifths < 0 else PITCH_CLASS_SHARP
    return names[pc], octave
