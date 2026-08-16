# parts_structure.py
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class PartStructureInfo:
    part_id: str = ""
    name: str = "Classical Guitar"
    gmidi_program: int = 25
    staves_clefs: Dict[int, str] = field(default_factory=dict)
    staves_voices: Dict[int, List[int]] = field(default_factory=dict)
    # (staff_id, voice_id) -> display name override for Region 2's voice
    # row, e.g. Guitar Pro's synthetic chord/strum voice showing as
    # "Chords" instead of the default "Voice N". Absent entries keep
    # today's f"Voice {v}" default - no behaviour change for MusicXML/MIDI.
    voice_names: Dict[Tuple[int, int], str] = field(default_factory=dict)