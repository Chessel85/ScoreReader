# models/gm_instruments.py
"""The General MIDI Level 1 instrument list (128 program names), used by
S5's instrument-override dialog so the user picks a name ("Clarinet") rather
than a raw program number - and by parsers/midi_reader.py's untitled-track
fallback, which suggests a name from a track's own Program Change event
instead of a bare "Track N" (BluePeter.mid, reported: an internet-sourced
MIDI file whose tracks carry no name at all).

Stdlib-only, like every other models/ module - see
test_models_package_does_not_import_qt.

GM programs are 1-indexed everywhere else in this app (PartStructureInfo.
gmidi_program, MusicXML's own <midi-program>) - GM_INSTRUMENT_NAMES keeps
that convention: index 0 is program 1 (Acoustic Grand Piano)."""
from typing import Dict, List, Optional

GM_INSTRUMENT_NAMES: List[str] = [
    # Piano
    "Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano",
    "Honky-tonk Piano", "Electric Piano 1", "Electric Piano 2", "Harpsichord",
    "Clavinet",
    # Chromatic Percussion
    "Celesta", "Glockenspiel", "Music Box", "Vibraphone", "Marimba",
    "Xylophone", "Tubular Bells", "Dulcimer",
    # Organ
    "Drawbar Organ", "Percussive Organ", "Rock Organ", "Church Organ",
    "Reed Organ", "Accordion", "Harmonica", "Tango Accordion",
    # Guitar
    "Acoustic Guitar (nylon)", "Acoustic Guitar (steel)",
    "Electric Guitar (jazz)", "Electric Guitar (clean)",
    "Electric Guitar (muted)", "Overdriven Guitar", "Distortion Guitar",
    "Guitar Harmonics",
    # Bass
    "Acoustic Bass", "Electric Bass (finger)", "Electric Bass (pick)",
    "Fretless Bass", "Slap Bass 1", "Slap Bass 2", "Synth Bass 1",
    "Synth Bass 2",
    # Strings
    "Violin", "Viola", "Cello", "Contrabass", "Tremolo Strings",
    "Pizzicato Strings", "Orchestral Harp", "Timpani",
    # Ensemble
    "String Ensemble 1", "String Ensemble 2", "Synth Strings 1",
    "Synth Strings 2", "Choir Aahs", "Voice Oohs", "Synth Voice",
    "Orchestra Hit",
    # Brass
    "Trumpet", "Trombone", "Tuba", "Muted Trumpet", "French Horn",
    "Brass Section", "Synth Brass 1", "Synth Brass 2",
    # Reed
    "Soprano Sax", "Alto Sax", "Tenor Sax", "Baritone Sax", "Oboe",
    "English Horn", "Bassoon", "Clarinet",
    # Pipe
    "Piccolo", "Flute", "Recorder", "Pan Flute", "Blown Bottle",
    "Shakuhachi", "Whistle", "Ocarina",
    # Synth Lead
    "Lead 1 (square)", "Lead 2 (sawtooth)", "Lead 3 (calliope)",
    "Lead 4 (chiff)", "Lead 5 (charang)", "Lead 6 (voice)",
    "Lead 7 (fifths)", "Lead 8 (bass + lead)",
    # Synth Pad
    "Pad 1 (new age)", "Pad 2 (warm)", "Pad 3 (polysynth)",
    "Pad 4 (choir)", "Pad 5 (bowed)", "Pad 6 (metallic)", "Pad 7 (halo)",
    "Pad 8 (sweep)",
    # Synth Effects
    "FX 1 (rain)", "FX 2 (soundtrack)", "FX 3 (crystal)",
    "FX 4 (atmosphere)", "FX 5 (brightness)", "FX 6 (goblins)",
    "FX 7 (echoes)", "FX 8 (sci-fi)",
    # Ethnic
    "Sitar", "Banjo", "Shamisen", "Koto", "Kalimba", "Bag pipe", "Fiddle",
    "Shanai",
    # Percussive
    "Tinkle Bell", "Agogo", "Steel Drums", "Woodblock", "Taiko Drum",
    "Melodic Tom", "Synth Drum", "Reverse Cymbal",
    # Sound effects
    "Guitar Fret Noise", "Breath Noise", "Seashore", "Bird Tweet",
    "Telephone Ring", "Helicopter", "Applause", "Gunshot",
]

assert len(GM_INSTRUMENT_NAMES) == 128

# name -> 1-indexed program number, for the dialog's editable combo box to
# resolve whatever the user typed/selected back to a program.
GM_PROGRAM_BY_NAME: Dict[str, int] = {
    name: idx + 1 for idx, name in enumerate(GM_INSTRUMENT_NAMES)
}


def gm_instrument_name(program: int) -> str:
    """1-indexed program -> name, clamped to the valid 1-128 range rather
    than raising - a malformed or out-of-range file value should degrade to
    the nearest real instrument, not crash the loader."""
    index = max(1, min(128, program)) - 1
    return GM_INSTRUMENT_NAMES[index]


def gm_program_for_name(name: str) -> Optional[int]:
    """The reverse lookup, or None for anything not an exact GM name (free
    text the user typed but never selected from the combo)."""
    return GM_PROGRAM_BY_NAME.get(name)
