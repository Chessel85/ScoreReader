# widgets/region2_manager.py
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple, Union


@dataclass
class Region2Node:
    """Represents a row node in the Region 2 tree hierarchy."""
    node_id: str                   # Unique identifier (e.g., 'part_P1', 'staff_P1_1', 'voice_P1_1_1')
    node_type: str                 # 'part', 'staff', or 'voice'
    display_name: str              # Label for Column 0 (e.g., "Classical Guitar", "Treble Clef", "Voice 1")
    muted: bool = False            # User mute toggle - independent of soloed, see get_active_voice_tuples
    soloed: bool = False           # See get_active_voice_tuples
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
        # Ref 25/S2: MIDI has no real staff concept (always faked as 1) and,
        # in every real file tested, exactly one voice per track too - the
        # tree still needs the full part/staff/voice structure underneath
        # (get_active_voice_tuples only finds a voice by walking down to a
        # real "voice" node - collapsing the TREE itself would silently make
        # every MIDI part invisible), but there is nothing for the user to
        # usefully navigate/toggle below the part level, so get_visible_nodes
        # stops there when this is set. Deliberately part of the model, not
        # just the list widget, so any other future view over this model
        # inherits the same behaviour for free.
        #
        # True collapses every part (MIDI, a pure Ultimate Guitar import); a
        # Set[str] of part_ids collapses only those - a MusicXML/GP score
        # with real notated parts alongside synthetic Chords/Lyrics parts
        # (see parsers/timeline_builder.py) needs the real parts' own
        # staff/voice structure kept, with only the synthetic ones flattened
        # ("chord chart"/"Voice 1" are made-up labels with nothing real
        # underneath, the same reasoning that already collapsed a pure UG
        # import's Chords/Lyrics parts, per-part rather than whole-tree here
        # since a mixed score keeps its real parts' real structure).
        self.collapse_to_parts: Union[bool, Set[str]] = False

    def clear(self):
        self.roots.clear()
        self._node_lookup.clear()

    def part_is_collapsed(self, part_id: str) -> bool:
        """True for a part with no real staff/voice concept underneath it
        (Ref 25/S2: MIDI, a pure Ultimate Guitar import, or one of the
        synthetic Chords/Lyrics parts) - such a part's row is never
        expandable, regardless of Region 2's own collapse/expand state."""
        if self.collapse_to_parts is True:
            return True
        if self.collapse_to_parts is False:
            return False
        return part_id in self.collapse_to_parts

    def build_from_score(self, parts_data: list, collapse_to_parts: Union[bool, Set[str]] = False):
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
        self.collapse_to_parts = collapse_to_parts

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
                    display_name=s_name,
                    part_id=p_id,
                    staff_id=s_id,
                    parent=part_node
                )
                part_node.children.append(staff_node)
                self._node_lookup[staff_node.node_id] = staff_node

                voice_names = s_data.get('voice_names', {})
                for v_id in s_data.get('voices', []):
                    v_int = int(v_id)
                    voice_label = voice_names.get(v_int) or f"Voice {v_int}"
                    voice_node = Region2Node(
                        node_id=f"voice_{p_id}_{s_id}_{v_int}",
                        node_type="voice",
                        display_name=voice_label,
                        part_id=p_id,
                        staff_id=s_id,
                        voice_id=v_int,
                        parent=staff_node
                    )
                    staff_node.children.append(voice_node)
                    self._node_lookup[voice_node.node_id] = voice_node

    def rename_part(self, part_id: str, new_name: str) -> None:
        """S5: reflects an instrument-dialog rename onto the already-built
        tree. Deliberately not a call into build_from_score, which resets
        every node's mute/solo state - this only ever touches display_name,
        so mute/solo toggles the user already set survive untouched."""
        for part in self.roots:
            if part.part_id == part_id:
                part.display_name = new_name
                return

    def rename_voice(self, part_id: str, staff_id: int, voice_id: int, new_label: str) -> None:
        """Wishlist #8 follow-up: reflects a percussion item rename onto a
        voice row's label in place - the same "not a build_from_score
        rebuild" reasoning as rename_part above (a rebuild resets every
        mute/solo toggle and expand state)."""
        node_id = f"voice_{part_id}_{staff_id}_{voice_id}"
        node = self._node_lookup.get(node_id)
        if node is not None:
            node.display_name = new_label

    def reorder_roots(self, part_id_order: List[str]) -> None:
        """Options > Reorder Parts... - reorders self.roots (the part-level
        nodes) to match part_id_order, leaving every node's full subtree
        state (muted, soloed, children) untouched. Deliberately not a
        call into build_from_score, which resets every node back to
        muted=False - same "targeted mutation, not a rebuild" reasoning
        as rename_part above. An unknown part_id is ignored; a known one
        missing from part_id_order keeps its existing relative position,
        appended after every part that was explicitly ordered."""
        known_ids = [p.part_id for p in self.roots]
        ordered = [pid for pid in part_id_order if pid in known_ids]
        ordered += [pid for pid in known_ids if pid not in ordered]
        order_index = {pid: i for i, pid in enumerate(ordered)}
        self.roots.sort(key=lambda p: order_index[p.part_id])

    def toggle_mute(self, node_id: str) -> bool:
        """Toggles one node's mute state. Returns the new state."""
        node = self._node_lookup.get(node_id)
        if not node:
            return False

        node.muted = not node.muted
        return node.muted

    def clear_all_mute(self) -> None:
        """Unmute All: deliberately does not touch soloed state - un-muting
        restores whatever solo state was already set, rather than clearing
        it too."""
        for part in self.roots:
            part.muted = False
            for staff in part.children:
                staff.muted = False
                for voice in staff.children:
                    voice.muted = False

    def node(self, node_id: str) -> Optional[Region2Node]:
        return self._node_lookup.get(node_id)

    def get_visible_nodes(self) -> List[Region2Node]:
        """
        Returns a flat list of every node that should ever have a row -
        mute/solo state no longer hides a node's children (Region 2 is a
        real tree now; only expand/collapse, a pure UI concern with no
        model-level representation, hides a row, and that is never
        persisted).

        With collapse_to_parts set (Ref 25/S2), a part row's own staff/voice
        children are never appended here regardless of mute state - they
        still exist in the tree underneath (get_active_voice_tuples still
        walks down to them), just never rendered as their own rows.
        """
        visible: List[Region2Node] = []

        def traverse(node: Region2Node):
            visible.append(node)
            if node.node_type == "part" and self.part_is_collapsed(node.part_id):
                return
            for child in node.children:
                traverse(child)

        for root in self.roots:
            traverse(root)

        return visible

    def get_muted_node_keys(
        self,
    ) -> Tuple[Set[str], Set[Tuple[str, int]], Set[Tuple[str, int, int]]]:
        """Every node's OWN mute state, as three sets, for ScoreConfig
        (Ref 27 AC1: part, stave and voice toggles are independently
        persistent).

        Deliberately NOT ancestor-gated, unlike get_active_voice_tuples: a
        voice that is individually unmuted but silenced because its part is
        muted must come back when the part does, and only an ungated read
        can tell that from a voice that was individually muted."""
        parts_muted: Set[str] = set()
        staves_muted: Set[Tuple[str, int]] = set()
        voices_muted: Set[Tuple[str, int, int]] = set()
        for part in self.roots:
            if part.muted:
                parts_muted.add(part.part_id)
            for staff in part.children:
                if staff.muted:
                    staves_muted.add((staff.part_id, staff.staff_id))
                for voice in staff.children:
                    if voice.muted:
                        voices_muted.add((voice.part_id, voice.staff_id, voice.voice_id))
        return parts_muted, staves_muted, voices_muted

    def apply_muted_node_keys(
        self,
        parts_muted: Set[str],
        staves_muted: Set[Tuple[str, int]],
        voices_muted: Set[Tuple[str, int, int]],
    ) -> None:
        """Restores every node's OWN mute state (the counterpart to
        get_muted_node_keys), e.g. after build_from_score has reset
        everything to muted=False. A lossless round trip - a part being
        muted and a sub-voice being individually unmuted are independent
        facts, not collapsed into one. Best-effort: a saved key matching no
        node is skipped."""
        for part in self.roots:
            part.muted = part.part_id in parts_muted
            for staff in part.children:
                staff.muted = (staff.part_id, staff.staff_id) in staves_muted
                for voice in staff.children:
                    voice.muted = (
                        voice.part_id, voice.staff_id, voice.voice_id
                    ) in voices_muted

    def get_soloed_node_keys(
        self,
    ) -> Tuple[Set[str], Set[Tuple[str, int]], Set[Tuple[str, int, int]]]:
        """The soloed counterpart to get_muted_node_keys - every node's OWN
        solo state, ungated, for ScoreConfig."""
        parts_soloed: Set[str] = set()
        staves_soloed: Set[Tuple[str, int]] = set()
        voices_soloed: Set[Tuple[str, int, int]] = set()
        for part in self.roots:
            if part.soloed:
                parts_soloed.add(part.part_id)
            for staff in part.children:
                if staff.soloed:
                    staves_soloed.add((staff.part_id, staff.staff_id))
                for voice in staff.children:
                    if voice.soloed:
                        voices_soloed.add((voice.part_id, voice.staff_id, voice.voice_id))
        return parts_soloed, staves_soloed, voices_soloed

    def apply_soloed_node_keys(
        self,
        parts_soloed: Set[str],
        staves_soloed: Set[Tuple[str, int]],
        voices_soloed: Set[Tuple[str, int, int]],
    ) -> None:
        """The soloed counterpart to apply_muted_node_keys."""
        for part in self.roots:
            part.soloed = part.part_id in parts_soloed
            for staff in part.children:
                staff.soloed = (staff.part_id, staff.staff_id) in staves_soloed
                for voice in staff.children:
                    voice.soloed = (
                        voice.part_id, voice.staff_id, voice.voice_id
                    ) in voices_soloed

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
        """Unsolo All. Deliberately does not touch mute state - un-soloing
        restores whatever mute toggles were already set, rather than
        clearing them too."""
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

        When anything is soloed, only voices under a soloed node are active
        - solo overrides mute entirely (see _soloed_voice_tuples). With
        nothing soloed, this falls through to the ancestor-gated mute walk
        below: a muted part or stave silences everything beneath it, same
        as any other mixer's mute cascades down its hierarchy.
        """
        if self.any_soloed():
            return self._soloed_voice_tuples()

        active_set: Set[Tuple[str, int, int]] = set()

        for root in self.roots:
            if root.muted:
                continue
            for staff in root.children:
                if staff.muted:
                    continue
                for voice in staff.children:
                    if not voice.muted:
                        if voice.part_id and voice.staff_id is not None and voice.voice_id is not None:
                            active_set.add((voice.part_id, voice.staff_id, voice.voice_id))

        return active_set

    def _soloed_voice_tuples(self) -> Set[Tuple[str, int, int]]:
        """Every voice under a soloed part, stave or voice. Solo overrides
        mute rather than intersecting with it: soloing a part the user had
        muted should still be heard, which is the point of a solo
        control."""
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
    mute/solo state - distinct from get_active_voice_tuples, since the
    attribute-order dialog scopes by tree position, not by what currently
    sounds."""
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
    attribute-order dialog's title."""
    parts = []
    current: Optional[Region2Node] = node
    while current is not None:
        parts.append(current.display_name.strip())
        current = current.parent
    return " > ".join(reversed(parts))


def node_status_label(node: Region2Node) -> str:
    """A tree row's text: the bare name when neither muted nor soloed
    ("Piano"), else the name plus "muted"/"soloed" in that fixed order
    ("Piano muted", "Piano soloed", "Piano muted soloed"). Solo beats mute
    in what actually sounds (get_active_voice_tuples), but both states are
    independently real and both get named here."""
    suffix_words = []
    if node.muted:
        suffix_words.append("muted")
    if node.soloed:
        suffix_words.append("soloed")
    if not suffix_words:
        return node.display_name
    return f"{node.display_name} {' '.join(suffix_words)}"