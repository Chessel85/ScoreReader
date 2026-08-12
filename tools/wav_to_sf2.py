#!/usr/bin/env python
"""wav_to_sf2.py - build a minimal SoundFont (.sf2) from WAV samples,
driven by a plain-text config file.

Standalone by design: no dependency on the rest of the Recall Score
codebase, no third-party packages (stdlib only), and the config file is
authored as plain text so it's usable without a GUI soundfont editor.

Built for UN-PITCHED one-shot sounds (spoken words, click sounds) rather
than musical instruments: every sample plays back at its own recorded
pitch/speed regardless of which MIDI note triggers it - it is never
transposed. Each MIDI note in a preset maps to exactly one sample, the
same way GM percussion or a drum kit works (as opposed to a normal pitched
instrument, where one recorded sample gets pitch-shifted to cover a range
of notes).

CONFIG FILE FORMAT (INI, read with the stdlib configparser - plain
"key = value" lines, no nesting, no special quoting - chosen over
TOML/JSON/YAML specifically to be easy to read and author with a screen
reader):

    [sf2]
    name = Recall Score Sounds
    output = position_announcer.sf2

    [preset:talking_metronome_default]
    bank = 0
    program = 0
    60 = samples/words/one.wav | one
    61 = samples/words/two.wav | two
    62 = samples/words/three.wav | three

    [preset:click_default]
    bank = 0
    program = 1
    60 = samples/clicks/click.wav | click
    61 = samples/clicks/accent.wav | accent

- [sf2] is one required section: `name` (embedded in the file's INFO
  chunk, cosmetic) and `output` (where to write the .sf2 - relative to
  the config file's own directory; overridable with --output).
- Every other section must be named [preset:SOMENAME] and becomes one
  SF2 preset, selectable at runtime via MIDI bank+program select. `bank`
  and `program` are required. Every remaining key in the section is a
  MIDI note - either a plain number 0-127, or a note name like C4/F#3/Bb2
  using the same C4=60 ("middle C") convention this project's own
  MusicXML parser uses (parsers/timeline_builder.py) - mapped to a WAV
  file path. Multiple presets (e.g. several different click sounds, or
  several different talking-metronome voices) can live in one .sf2 file
  and one config, distinguished by bank/program.
- A WAV path may optionally be followed by `| a label` - purely
  documentation, carried through into the sidecar .json (see below), not
  written into the .sf2 itself. Not required.
- WAV files must be 16-bit PCM mono (e.g. exported that way from
  Audacity). Anything else is rejected with an explanation rather than
  silently down-mixed/converted.

OUTPUT: a single <output>.sf2 file - no sidecar metadata file. An earlier
version also wrote a <output>.sf2.json listing each sample's own natural
duration, for a consumer (audio/synth_engine.py) to hold a MIDI note on for
at least that long before releasing it - since a one-shot, non-looping
sample only plays to its natural end if held that long. That turned out to
be unnecessary: FluidSynth deactivates a one-shot (SampleModes=0) voice on
its own once the sample's data is exhausted, regardless of whether a
note-off was ever sent, so the consumer no longer needs to know each
sample's length up front - it just avoids releasing the note early. See
audio/synth_engine.py's play_click() for how this was verified.

USAGE:
    python wav_to_sf2.py path/to/config.ini [--output out.sf2]
"""
from __future__ import annotations

import argparse
import configparser
import re
import struct
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SF2_SAMPLE_PADDING = 46  # required silent samples after each sample's data
SF2_TERMINAL_PADDING = 46  # required silent samples at the very end of smpl

NOTE_LETTER_SEMITONES = {
    "C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11,
}
_NOTE_NAME_RE = re.compile(r"^([A-Ga-g])([#Bb]?)(-?\d+)$")


def parse_note(token: str) -> int:
    """A MIDI note number (0-127), from either a plain integer string or
    a note name like "C4"/"F#3"/"Bb2" - C4 = 60 ("middle C"), matching
    parsers/timeline_builder.py's own (octave + 1) * 12 + step + alter
    formula, so a config file reads naturally to anyone who already knows
    this project's own note-naming convention."""
    token = token.strip()
    if token.lstrip("-").isdigit():
        note = int(token)
    else:
        m = _NOTE_NAME_RE.match(token)
        if not m:
            raise ValueError(
                f"Cannot parse '{token}' as a MIDI note number or a note name "
                "(e.g. 60 or C4)"
            )
        letter, accidental, octave_str = m.groups()
        semitone = NOTE_LETTER_SEMITONES[letter.upper()]
        if accidental == "#":
            semitone += 1
        elif accidental.upper() == "B":
            semitone -= 1
        note = (int(octave_str) + 1) * 12 + semitone
    if not (0 <= note <= 127):
        raise ValueError(f"MIDI note {note} (from '{token}') is out of range 0-127")
    return note


@dataclass
class SampleZone:
    note: int
    wav_path: Path
    label: Optional[str]
    pcm: bytes = field(repr=False)
    frame_count: int = 0
    sample_rate: int = 0

    @property
    def sf2_sample_name(self) -> str:
        base = self.label or self.wav_path.stem
        return base[:20]  # shdr name field is 20 bytes, truncate rather than fail


@dataclass
class Preset:
    name: str
    bank: int
    program: int
    zones: List[SampleZone]


def _read_wav_pcm16_mono(path: Path) -> Tuple[bytes, int, int]:
    """(pcm_bytes, frame_count, sample_rate). Raises ValueError with a
    clear message for anything not already 16-bit PCM mono - this tool
    deliberately does not resample/downmix/convert, since silently
    changing a user-recorded word's audio is more likely to surprise them
    than a clear upfront error asking them to re-export it correctly."""
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        pcm = wf.readframes(nframes)
    if channels != 1:
        raise ValueError(
            f"{path}: has {channels} channels - must be mono. "
            "Re-export as mono (e.g. Audacity: Tracks > Mix > Mix Stereo Down to Mono)."
        )
    if sampwidth != 2:
        raise ValueError(
            f"{path}: is {sampwidth * 8}-bit - must be 16-bit PCM. "
            "Re-export as 16-bit PCM WAV."
        )
    return pcm, nframes, framerate


def load_config(config_path: Path) -> Tuple[str, Optional[str], List[Preset]]:
    """(sf2_name, output_path_or_None, presets) - reads and validates the
    INI config, and loads/validates every referenced WAV file up front so
    a mistake in ANY sample is reported before any bytes are written."""
    parser = configparser.ConfigParser()
    parser.optionxform = str  # preserve case; our real keys are numeric/lowercase anyway
    read_files = parser.read(config_path)
    if not read_files:
        raise FileNotFoundError(f"Config file not found: {config_path}")

    if "sf2" not in parser:
        raise ValueError("Config is missing the required [sf2] section")
    sf2_section = parser["sf2"]
    sf2_name = sf2_section.get("name", "Recall Score Sounds")
    output = sf2_section.get("output")

    base_dir = config_path.parent
    presets: List[Preset] = []
    used_note_ids = set()
    used_bank_programs: Dict[Tuple[int, int], str] = {}

    for section_name in parser.sections():
        if section_name == "sf2":
            continue
        if not section_name.startswith("preset:"):
            raise ValueError(
                f"Unrecognised section [{section_name}] - expected [sf2] or [preset:NAME]"
            )
        preset_name = section_name[len("preset:"):].strip()
        if not preset_name:
            raise ValueError(f"Section [{section_name}] needs a name after 'preset:'")
        section = parser[section_name]
        if "bank" not in section or "program" not in section:
            raise ValueError(f"[{section_name}] needs both 'bank' and 'program'")
        bank = int(section["bank"])
        program = int(section["program"])
        if (bank, program) in used_bank_programs:
            other = used_bank_programs[(bank, program)]
            raise ValueError(
                f"[{section_name}]: bank {bank} program {program} is already used by "
                f"[preset:{other}] - each preset needs its own bank/program combination"
            )
        used_bank_programs[(bank, program)] = preset_name

        zones: List[SampleZone] = []
        for key, value in section.items():
            if key in ("bank", "program"):
                continue
            note = parse_note(key)
            if (bank, program, note) in used_note_ids:
                raise ValueError(
                    f"[{section_name}]: note {note} (from key '{key}') is mapped twice"
                )
            used_note_ids.add((bank, program, note))

            raw = value.split("|", 1)
            wav_rel = raw[0].strip()
            label = raw[1].strip() if len(raw) > 1 else None
            wav_path = (base_dir / wav_rel).resolve()
            if not wav_path.exists():
                raise FileNotFoundError(
                    f"[{section_name}] note {note}: WAV file not found: {wav_path}"
                )
            pcm, nframes, framerate = _read_wav_pcm16_mono(wav_path)
            zones.append(SampleZone(
                note=note, wav_path=wav_path, label=label,
                pcm=pcm, frame_count=nframes, sample_rate=framerate,
            ))

        if not zones:
            raise ValueError(f"[{section_name}] has no note-to-WAV mappings")
        zones.sort(key=lambda z: z.note)
        presets.append(Preset(name=preset_name, bank=bank, program=program, zones=zones))

    if not presets:
        raise ValueError("Config has no [preset:...] sections")
    return sf2_name, output, presets


# --- RIFF/SF2 binary construction ------------------------------------------

def _chunk(cktype: bytes, data: bytes) -> bytes:
    if len(data) % 2 == 1:
        data += b"\x00"
    return cktype + struct.pack("<I", len(data)) + data


def _list_chunk(listtype: bytes, subchunks: bytes) -> bytes:
    return _chunk(b"LIST", listtype + subchunks)


def _cstr20(name: str) -> bytes:
    encoded = name.encode("ascii", errors="replace")[:20]
    return encoded + b"\x00" * (20 - len(encoded))


def build_sf2(sf2_name: str, presets: List[Preset]) -> bytes:
    """Assembles a complete, minimal-but-valid SF2 v2.01 file: every
    preset has one global-instrument link; every instrument has one zone
    per note, each zone a single sample with its keyRange pinned to
    exactly that one note and no loop (SampleModes=0) - see the module
    docstring for why the caller still needs each zone's own duration to
    know how long to hold the note."""
    # --- sdta: concatenate every sample's PCM, each followed by the
    # required silent padding, plus the mandatory final silent block.
    smpl_parts: List[bytes] = []
    sample_offsets: Dict[int, Tuple[int, int]] = {}  # id(zone) -> (start, end), in sample points
    cursor = 0
    all_zones: List[SampleZone] = [z for p in presets for z in p.zones]
    for zone in all_zones:
        n_points = len(zone.pcm) // 2
        start = cursor
        end = start + n_points
        smpl_parts.append(zone.pcm)
        smpl_parts.append(b"\x00\x00" * SF2_SAMPLE_PADDING)
        cursor = end + SF2_SAMPLE_PADDING
        sample_offsets[id(zone)] = (start, end)
    smpl_parts.append(b"\x00\x00" * SF2_TERMINAL_PADDING)
    smpl_data = b"".join(smpl_parts)
    sdta = _list_chunk(b"sdta", _chunk(b"smpl", smpl_data))

    # --- pdta hydra ---------------------------------------------------
    phdr_records = bytearray()
    pbag_records = bytearray()
    pgen_records = bytearray()
    inst_records = bytearray()
    ibag_records = bytearray()
    igen_records = bytearray()
    shdr_records = bytearray()

    def pgen_scalar(oper: int, amount: int) -> bytes:
        return struct.pack("<Hh", oper, amount)

    def pgen_range(oper: int, lo: int, hi: int) -> bytes:
        return struct.pack("<HBB", oper, lo, hi)

    GEN_INSTRUMENT = 41
    GEN_KEY_RANGE = 43
    GEN_SAMPLE_MODES = 54
    GEN_SAMPLE_ID = 53

    sample_index_of = {}  # id(zone) -> index into shdr

    for zone in all_zones:
        sample_index_of[id(zone)] = len(shdr_records) // 46
        start, end = sample_offsets[id(zone)]
        shdr_records += struct.pack(
            "<20sIIIIIBbHH",
            _cstr20(zone.sf2_sample_name),
            start, end,
            start, start + 1,  # loop points unused (no-loop sample), kept in-range
            zone.sample_rate,
            zone.note,  # byOriginalPitch = the note it's mapped to: no pitch-shift
            0,          # chPitchCorrection
            0,          # wSampleLink
            1,          # sfSampleType = monoSample
        )

    inst_index_of_preset = {}
    for preset in presets:
        inst_index_of_preset[preset.name] = len(inst_records) // 22
        inst_records += struct.pack("<20sH", _cstr20(preset.name), len(ibag_records) // 4)
        for zone in preset.zones:
            ibag_records += struct.pack("<HH", len(igen_records) // 4, 0)
            igen_records += pgen_range(GEN_KEY_RANGE, zone.note, zone.note)
            igen_records += pgen_scalar(GEN_SAMPLE_MODES, 0)
            igen_records += pgen_scalar(GEN_SAMPLE_ID, sample_index_of[id(zone)])
    # terminal instrument + its terminal ibag zone
    inst_records += struct.pack("<20sH", _cstr20("EOI"), len(ibag_records) // 4)
    ibag_records += struct.pack("<HH", len(igen_records) // 4, 0)

    for preset in presets:
        phdr_records += struct.pack(
            "<20sHHHIII",
            _cstr20(preset.name), preset.program, preset.bank,
            len(pbag_records) // 4,
            0, 0, 0,
        )
        pbag_records += struct.pack("<HH", len(pgen_records) // 4, 0)
        pgen_records += pgen_scalar(GEN_INSTRUMENT, inst_index_of_preset[preset.name])
    # terminal preset + its terminal pbag zone
    phdr_records += struct.pack("<20sHHHIII", _cstr20("EOP"), 0, 0, len(pbag_records) // 4, 0, 0, 0)
    pbag_records += struct.pack("<HH", len(pgen_records) // 4, 0)

    # terminal sentinel records (all-zero) for the two unused modulator lists
    pmod_records = struct.pack("<HHhHH", 0, 0, 0, 0, 0)
    imod_records = struct.pack("<HHhHH", 0, 0, 0, 0, 0)
    # terminal sentinel sample header
    shdr_records += struct.pack("<20sIIIIIBbHH", _cstr20("EOS"), 0, 0, 0, 0, 0, 0, 0, 0, 0)

    pdta = _list_chunk(
        b"pdta",
        _chunk(b"phdr", bytes(phdr_records))
        + _chunk(b"pbag", bytes(pbag_records))
        + _chunk(b"pmod", pmod_records)
        + _chunk(b"pgen", bytes(pgen_records))
        + _chunk(b"inst", bytes(inst_records))
        + _chunk(b"ibag", bytes(ibag_records))
        + _chunk(b"imod", imod_records)
        + _chunk(b"igen", bytes(igen_records))
        + _chunk(b"shdr", bytes(shdr_records)),
    )

    info = _list_chunk(
        b"INFO",
        _chunk(b"ifil", struct.pack("<HH", 2, 1))
        + _chunk(b"isng", b"EMU8000\x00")
        + _chunk(b"INAM", sf2_name.encode("ascii", errors="replace") + b"\x00"),
    )

    return _chunk(b"RIFF", b"sfbk" + info + sdta + pdta)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", type=Path, help="Path to the .ini config file")
    ap.add_argument("--output", type=Path, default=None, help="Override the config's [sf2] output path")
    args = ap.parse_args()

    try:
        sf2_name, configured_output, presets = load_config(args.config)

        output = args.output or (Path(configured_output) if configured_output else None)
        if output is None:
            raise ValueError("No output path: set [sf2] output = ... in the config, or pass --output")
        if not output.is_absolute():
            output = args.config.parent / output

        sf2_bytes = build_sf2(sf2_name, presets)
        output.write_bytes(sf2_bytes)
    except (FileNotFoundError, ValueError) as e:
        # Expected, explained errors (bad config, missing/wrong-format WAV,
        # duplicate note...) - a plain one-line message is much easier to
        # read with a screen reader than a full Python traceback, so those
        # are the only exception types caught here; anything else is a real
        # bug in this script and should still show its full traceback.
        raise SystemExit(f"Error: {e}") from None

    total_zones = sum(len(p.zones) for p in presets)
    print(f"Wrote {output} ({len(sf2_bytes)} bytes, {len(presets)} preset(s), {total_zones} sample(s))")


if __name__ == "__main__":
    main()
