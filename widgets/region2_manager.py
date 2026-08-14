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
    soloed: bool = False           # Wishlist #8; see get_active_voice_tuples
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
        """Every node's OWN enabled state, as three OFF-sets, for ScoreConfig
        (Ref 27 AC1: part, stave and voice toggles are independently
        persistent).

        Deliberately NOT ancestor-gated, unlike get_active_voice_tuples: a
        voice that is individually on but hidden because its part is off must
        come back on when the part does, and only an ungated read can tell
        that from a voice that was individually switched off."""
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
        """Restores every node's OWN enabled state (the counterpart to
        get_off_node_keys), e.g. after build_from_score has reset everything
        to enabled=True. A lossless round trip - a part being off and a
        sub-voice being individually on are independent facts, not collapsed
        into one. Best-effort: a saved key matching no node is skipped."""
        for part in self.roots:
            part.enabled = part.part_id not in parts_off
            for staff in part.children:
                staff.enabled = (staff.part_id, staff.staff_id) not in staves_off
                for voice in staff.children:
                    voice.enabled = (
                        voice.part_id, voice.staff_id, voice.voice_id
                    ) not in voices_off

    def any_soloed(self) -> bool:
        """Wishlist #8: is anything soloed anywhere in the tree?"""
        return any(
            node.soloed
            for part in self.roots
            for node in (part, *part.children, *(v for s in part.children for v in s.children))
        )

    def toggle_solo(self, node_id: str) -> bool:
        """Flips one node's solo state. Returns the new state."""
        node = self._node_lookup.get(node_id)
        if not node:
            return False
        node.soloed = not node.soloed
        return node.soloed

    def clear_all_solo(self) -> None:
        """Wishlist #8's "unsolo all". Deliberately does not touch enabled
        state - un-soloing restores whatever on/off toggles were already
        set, rather than switching everything on."""
        for part in self.roots:
            part.soloed = False
            for staff in part.children:
                staff.soloed = False
                for voice in staff.children:
                    voice.soloed = False

    def get_active_voice_tuples(self) -> Set[Tuple[str, int, int]]:
        """
        Returns a set of (part_id, staff_id, voice_id) tuples that are currently active
        for filtering Region 3 note lists.

        Wishlist #8: when anything is soloed, only voices under a soloed
        node are active. With nothing soloed - which is every case today,
        since no UI sets it - this falls through to the ancestor-gated
        enabled walk below, unchanged.
        """
        if self.any_soloed():
            return self._soloed_voice_tuples()

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

    def _soloed_voice_tuples(self) -> Set[Tuple[str, int, int]]:
        """Every voice under a soloed part, stave or voice. Solo overrides
        the on/off toggles rather than intersecting with them: soloing a
        part the user had switched off should still be heard, which is the
        point of a solo control."""
        active_set: Set[Tuple[str, int, int]] = set()
        for part in self.roots:
            for staff in part.children:
                for voice in staff.children:
                    if part.soloed or staff.soloed or voice.soloed:
                        if (
                            voice.part_id
                            and voice.staff_id is not None
                            and voice.voice_id is not None
                        ):
                            active_set.add((voice.part_id, voice.staff_id, voice.voice_id))
        return active_set


def voice_tuples_for_node(node: Region2Node) -> Set[Tuple[str, int, int]]:
    """Every (part_id, staff_id, voice_id) below `node`, regardless of
    enabled state - distinct from get_active_voice_tuples, since the
    attribute-order dialog scopes by tree position, not by what is toggled
    on."""
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
    """"Piano > Bass Clef > Voice 5" path from the root to `node`, for the
    attribute-order dialog's title. display_name carries leading spaces for
    the flat-list rendering, which strip() removes here."""
    parts = []
    current: Optional[Region2Node] = node
    while current is not None:
        parts.append(current.display_name.strip())
        current = current.parent
    return " > ".join(reversed(parts))