# widgets/region2_manager.py
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple


@dataclass
class Region2Node:
    """Represents a row node in the Region 2 tree hierarchy."""
    node_id: str                   # Unique identifier (e.g., 'part_P1', 'staff_P1_1', 'voice_P1_1_1')
    node_type: str                 # 'part', 'staff', or 'voice'
    display_name: str              # Label for Column 0 (e.g., "Classical Guitar", "Treble Clef", "Voice 1")
    enabled: bool = True           # User toggle state ('on'/'off')
    part_id: str = ""
    staff_id: Optional[int] = None
    voice_id: Optional[int] = None
    children: List['Region2Node'] = field(default_factory=list)
    parent: Optional['Region2Node'] = None


class Region2HierarchyModel:
    """Manages hierarchical state, row visibility collapsing, and active voice tracking."""

    def __init__(self):
        self.roots: List[Region2Node] = []
        self._node_lookup: Dict[str, Region2Node] = {}

    def clear(self):
        self.roots.clear()
        self._node_lookup.clear()

    def build_from_score(self, parts_data: list):
        """
        Builds the tree structure from parsed score metadata.
        Expected parts_data structure:
        [
            {
                'id': 'P1',
                'name': 'Classical Guitar',
                'staves': [
                    {
                        'id': 1,
                        'name': 'Treble Clef',
                        'voices': [1, 2]
                    },
                    {
                        'id': 2,
                        'name': 'Guitar TAB Standard Tuning',
                        'voices': [5, 6]
                    }
                ]
            }
        ]
        """
        self.clear()

        for p_data in parts_data:
            p_id = str(p_data.get('id', 'P1'))
            p_name = p_data.get('name', f"Part {p_id}")
            part_node = Region2Node(
                node_id=f"part_{p_id}",
                node_type="part",
                display_name=p_name,
                part_id=p_id
            )
            self.roots.append(part_node)
            self._node_lookup[part_node.node_id] = part_node

            for s_data in p_data.get('staves', []):
                s_id = int(s_data.get('id', 1))
                s_name = s_data.get('name', f"Staff {s_id}")
                staff_node = Region2Node(
                    node_id=f"staff_{p_id}_{s_id}",
                    node_type="staff",
                    display_name=f"  {s_name}",
                    part_id=p_id,
                    staff_id=s_id,
                    parent=part_node
                )
                part_node.children.append(staff_node)
                self._node_lookup[staff_node.node_id] = staff_node

                for v_id in s_data.get('voices', []):
                    v_int = int(v_id)
                    voice_node = Region2Node(
                        node_id=f"voice_{p_id}_{s_id}_{v_int}",
                        node_type="voice",
                        display_name=f"    Voice {v_int}",
                        part_id=p_id,
                        staff_id=s_id,
                        voice_id=v_int,
                        parent=staff_node
                    )
                    staff_node.children.append(voice_node)
                    self._node_lookup[voice_node.node_id] = voice_node

    def toggle_node(self, node_id: str) -> bool:
        """Toggles enabled status ('on'/'off') of a node. Returns new state."""
        node = self._node_lookup.get(node_id)
        if not node:
            return False

        node.enabled = not node.enabled
        return node.enabled

    def get_visible_nodes(self) -> List[Region2Node]:
        """
        Returns a flat list of nodes that should currently be displayed.
        If a parent node is 'off', its child rows are omitted/hidden from the list.
        """
        visible: List[Region2Node] = []

        def traverse(node: Region2Node):
            visible.append(node)
            # Only traverse children if parent is enabled ('on')
            if node.enabled:
                for child in node.children:
                    traverse(child)

        for root in self.roots:
            traverse(root)

        return visible

    def get_off_node_keys(
        self,
    ) -> Tuple[Set[str], Set[Tuple[str, int]], Set[Tuple[str, int, int]]]:
        """Every node's OWN enabled state (Ref 27 AC1: part, stave and voice
        toggles are each independently persistent), as three OFF-sets -
        (parts_off, staves_off, voices_off) - for ScoreConfig. Deliberately
        NOT gated by ancestors (unlike get_active_voice_tuples, which is
        Ref 7's playback/display filter): a voice that's individually on
        but merely hidden because its part is off must still come back as
        on once the part is switched on again, and only this ungated read
        can tell that apart from a voice that was individually switched off
        (reported bug, live-tested: the old save path only had the gated
        set, so it couldn't)."""
        parts_off: Set[str] = set()
        staves_off: Set[Tuple[str, int]] = set()
        voices_off: Set[Tuple[str, int, int]] = set()
        for part in self.roots:
            if not part.enabled:
                parts_off.add(part.part_id)
            for staff in part.children:
                if not staff.enabled:
                    staves_off.add((staff.part_id, staff.staff_id))
                for voice in staff.children:
                    if not voice.enabled:
                        voices_off.add((voice.part_id, voice.staff_id, voice.voice_id))
        return parts_off, staves_off, voices_off

    def apply_off_node_keys(
        self,
        parts_off: Set[str],
        staves_off: Set[Tuple[str, int]],
        voices_off: Set[Tuple[str, int, int]],
    ) -> None:
        """Restores every node's OWN enabled state from a saved ScoreConfig
        (the counterpart to get_off_node_keys) - e.g. after build_from_score
        has reset every node back to its default enabled=True. A lossless
        round trip: unlike the old set_active_voice_tuples inference, a part
        being off and a sub-voice being individually on are stored (and
        restored) as the independent facts they are, not collapsed into
        one. Best-effort against a changed score: a saved key with no
        matching node here (in either set) simply has no node to apply to
        and is silently skipped."""
        for part in self.roots:
            part.enabled = part.part_id not in parts_off
            for staff in part.children:
                staff.enabled = (staff.part_id, staff.staff_id) not in staves_off
                for voice in staff.children:
                    voice.enabled = (
                        voice.part_id, voice.staff_id, voice.voice_id
                    ) not in voices_off

    def get_active_voice_tuples(self) -> Set[Tuple[str, int, int]]:
        """
        Returns a set of (part_id, staff_id, voice_id) tuples that are currently active
        for filtering Region 3 note lists.
        """
        active_set: Set[Tuple[str, int, int]] = set()

        for root in self.roots:
            if not root.enabled:
                continue
            for staff in root.children:
                if not staff.enabled:
                    continue
                for voice in staff.children:
                    if voice.enabled:
                        if voice.part_id and voice.staff_id is not None and voice.voice_id is not None:
                            active_set.add((voice.part_id, voice.staff_id, voice.voice_id))

        return active_set


def voice_tuples_for_node(node: Region2Node) -> Set[Tuple[str, int, int]]:
    """Every (part_id, staff_id, voice_id) tuple reachable below `node`,
    regardless of enabled state - deliberately distinct from
    get_active_voice_tuples (Ref 7's playback/display filter), since F2's
    attribute-order dialog scopes by tree position, not by what's currently
    toggled on/off."""
    if node.node_type == "voice":
        return {(node.part_id, node.staff_id, node.voice_id)}
    if node.node_type == "staff":
        return {(node.part_id, node.staff_id, voice.voice_id) for voice in node.children}
    return {
        (node.part_id, staff.staff_id, voice.voice_id)
        for staff in node.children
        for voice in staff.children
    }


def node_breadcrumb(node: Region2Node) -> str:
    """"Piano > Bass Clef > Voice 5"-style path from the root down to
    `node`, for the F2 attribute-order dialog's title - display_name is
    indented with leading spaces for the flat-list rendering
    (Region2ListWidget.refresh_list), which strip() removes here."""
    parts = []
    current: Optional[Region2Node] = node
    while current is not None:
        parts.append(current.display_name.strip())
        current = current.parent
    return " > ".join(reversed(parts))