# parts_structure.py
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class PartStructureInfo:
    part_id: str = ""
    name: str = "Classical Guitar"
    gmidi_program: int = 25
    staves_clefs: Dict[int, str] = field(default_factory=dict)
    staves_voices: Dict[int, List[int]] = field(default_factory=dict)