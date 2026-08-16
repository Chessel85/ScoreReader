# tests/widgets/test_region2_manager.py
"""Region2HierarchyModel is pure state with no Qt dependency, so it needs
no qapp fixture and runs instantly."""
import pytest

from widgets.region2_manager import (
    Region2HierarchyModel,
    node_breadcrumb,
    node_status_label,
    voice_tuples_for_node,
)

PARTS_DATA = [
    {
        "id": "P1",
        "name": "Piano",
        "staves": [
            {"id": 1, "name": "Treble Clef", "voices": [1]},
            {"id": 2, "name": "Bass Clef", "voices": [5, 6]},
        ],
    },
    {
        "id": "P2",
        "name": "Classical Guitar",
        "staves": [{"id": 1, "name": "Treble Clef", "voices": [1, 2]}],
    },
]


@pytest.fixture
def model() -> Region2HierarchyModel:
    m = Region2HierarchyModel()
    m.build_from_score(PARTS_DATA)
    return m


def test_builds_full_hierarchy(model):
    names = [n.display_name for n in model.get_visible_nodes()]

    assert names == [
        "Piano",
        "Treble Clef",
        "Voice 1",
        "Bass Clef",
        "Voice 5",
        "Voice 6",
        "Classical Guitar",
        "Treble Clef",
        "Voice 1",
        "Voice 2",
    ]


def test_muting_a_staff_does_not_hide_its_voices(model):
    """Region 2 is a real tree now - mute state no longer hides rows, only
    expand/collapse does (a pure widget-level concern with nothing to test
    here). A voice under a muted stave must stay reachable so it can still
    be individually soloed."""
    model.toggle_mute("staff_P1_2")
    names = [n.display_name for n in model.get_visible_nodes()]

    assert "Voice 5" in names
    assert "Bass Clef" in names


def test_collapse_to_parts_shows_only_part_rows():
    """Ref 25/S2: a MIDI-loaded score's Region 2 shows track rows only -
    no staff/voice rows, which for MIDI are either fake (staff) or, in every
    real file tested, always trivially 1 (voice)."""
    model = Region2HierarchyModel()
    model.build_from_score(PARTS_DATA, collapse_to_parts=True)

    names = [n.display_name for n in model.get_visible_nodes()]
    assert names == ["Piano", "Classical Guitar"]


def test_collapse_to_parts_still_computes_full_active_voice_tuples():
    """The tree underneath a collapsed part row must stay fully intact -
    only the RENDERED rows change. Collapsing must not make every note in
    a MIDI part invisible (get_active_voice_tuples only finds a voice by
    walking down to a real 'voice' tree node)."""
    model = Region2HierarchyModel()
    model.build_from_score(PARTS_DATA, collapse_to_parts=True)

    assert model.get_active_voice_tuples() == {
        ("P1", 1, 1), ("P1", 2, 5), ("P1", 2, 6),
        ("P2", 1, 1), ("P2", 1, 2),
    }


def test_collapse_to_parts_toggle_still_mutes_the_whole_part(model):
    collapsed = Region2HierarchyModel()
    collapsed.build_from_score(PARTS_DATA, collapse_to_parts=True)

    collapsed.toggle_mute("part_P1")

    assert ("P1", 1, 1) not in collapsed.get_active_voice_tuples()
    assert ("P2", 1, 1) in collapsed.get_active_voice_tuples()


def test_collapse_to_parts_accepts_a_set_to_collapse_only_specific_parts():
    """A MusicXML score mixing a real notated part with synthetic
    Chords/Lyrics parts (parsers/timeline_builder.py) must keep the real
    part's own staff/voice tree while flattening only the synthetic ones -
    reported: showing "Chord chart"/"Voice 1" as a fake 3-level tree read as
    redundant, made-up navigation."""
    model = Region2HierarchyModel()
    model.build_from_score(PARTS_DATA, collapse_to_parts={"P2"})

    names = [n.display_name for n in model.get_visible_nodes()]
    assert names == ["Piano", "Treble Clef", "Voice 1", "Bass Clef", "Voice 5", "Voice 6", "Classical Guitar"]


def test_collapse_to_parts_set_still_computes_full_active_voice_tuples():
    model = Region2HierarchyModel()
    model.build_from_score(PARTS_DATA, collapse_to_parts={"P2"})

    assert model.get_active_voice_tuples() == {
        ("P1", 1, 1), ("P1", 2, 5), ("P1", 2, 6),
        ("P2", 1, 1), ("P2", 1, 2),
    }


def test_node_ids_stay_unique_across_parts(model):
    """Both parts have a staff 1 with a voice 1. They must not collide -
    the flat dict in MusicData.get_region_2_data() does exactly that."""
    ids = [n.node_id for n in model.get_visible_nodes()]

    assert len(ids) == len(set(ids))
    assert "voice_P1_1_1" in ids
    assert "voice_P2_1_1" in ids


def test_active_voice_tuples_track_part_staff_and_voice(model):
    assert model.get_active_voice_tuples() == {
        ("P1", 1, 1),
        ("P1", 2, 5),
        ("P1", 2, 6),
        ("P2", 1, 1),
        ("P2", 1, 2),
    }

    model.toggle_mute("part_P2")

    assert model.get_active_voice_tuples() == {
        ("P1", 1, 1),
        ("P1", 2, 5),
        ("P1", 2, 6),
    }


# F2/Ref 15 AC4: scope helpers for the attribute-order dialog - node-tree
# lookups, not the mute-state filtering get_active_voice_tuples does.

def test_voice_tuples_for_node_voice_scope(model):
    node = model._node_lookup["voice_P1_2_5"]

    assert voice_tuples_for_node(node) == {("P1", 2, 5)}


def test_voice_tuples_for_node_staff_scope_covers_every_voice_on_that_staff(model):
    node = model._node_lookup["staff_P1_2"]

    assert voice_tuples_for_node(node) == {("P1", 2, 5), ("P1", 2, 6)}


def test_voice_tuples_for_node_part_scope_covers_every_staff_and_voice(model):
    node = model._node_lookup["part_P2"]

    assert voice_tuples_for_node(node) == {("P2", 1, 1), ("P2", 1, 2)}


def test_voice_tuples_for_node_ignores_mute_state(model):
    """Unlike get_active_voice_tuples (Ref 7's playback filter), scope for
    the attribute-order dialog does not depend on Region 2's mute toggle."""
    model.toggle_mute("voice_P1_2_5")
    node = model._node_lookup["staff_P1_2"]

    assert voice_tuples_for_node(node) == {("P1", 2, 5), ("P1", 2, 6)}


def test_node_breadcrumb_joins_the_full_path(model):
    node = model._node_lookup["voice_P1_2_5"]

    assert node_breadcrumb(node) == "Piano > Bass Clef > Voice 5"


def test_unmuting_a_parent_restores_each_childs_previous_state(model):
    """Toggling a staff's mute must not reset its voices - each voice keeps
    whatever mute state it had before the staff was muted and unmuted
    again."""
    model.toggle_mute("voice_P1_1_1")  # Voice 1 muted

    model.toggle_mute("staff_P1_1")  # mute staff 1
    model.toggle_mute("staff_P1_1")  # unmute it again

    assert model.get_active_voice_tuples() == {
        ("P1", 2, 5),
        ("P1", 2, 6),
        ("P2", 1, 1),
        ("P2", 1, 2),
    }, "voice 1 must still be muted after its staff round-trips through muted/unmuted"


# --- Ref 27: get_muted_node_keys/apply_muted_node_keys (per-node persistence)

def test_get_muted_node_keys_reads_each_nodes_own_state_not_the_gated_one(model):
    """A part switched to muted must not report its still-individually-
    unmuted sub-voices as muted too - get_muted_node_keys is the ungated
    read get_active_voice_tuples deliberately isn't."""
    model.toggle_mute("part_P2")  # P2 muted - its voices are still individually unmuted

    parts_muted, staves_muted, voices_muted = model.get_muted_node_keys()

    assert parts_muted == {"P2"}
    assert staves_muted == set()
    assert voices_muted == set(), "P2's voices are still individually unmuted underneath the muted part"


def test_muted_node_keys_round_trip_preserves_a_sub_voices_state_under_a_muted_part(model):
    """Reported bug, live-tested (for the old on/off toggle this replaced):
    toggling a part off with a sub-voice still individually on, then
    reloading, used to bring that sub-voice back off too, because only the
    ancestor-gated active set was ever persisted. get_muted_node_keys/
    apply_muted_node_keys must round-trip losslessly."""
    model.toggle_mute("part_P2")  # P2 muted; P2's voices remain individually unmuted underneath

    parts_muted, staves_muted, voices_muted = model.get_muted_node_keys()

    fresh = Region2HierarchyModel()
    fresh.build_from_score(PARTS_DATA)
    fresh.apply_muted_node_keys(parts_muted, staves_muted, voices_muted)

    p2 = fresh._node_lookup["part_P2"]
    p2_voice_1 = fresh._node_lookup["voice_P2_1_1"]
    assert p2.muted is True, "the part itself is muted, as toggled"
    assert p2_voice_1.muted is False, (
        "the sub-voice's own individual unmuted state must survive the round trip"
    )

    # Unmuting the part again must reveal the sub-voice still unmuted, not
    # collapsed to muted along with everything else under it.
    fresh.toggle_mute("part_P2")
    assert fresh.get_active_voice_tuples() == {
        ("P1", 1, 1),
        ("P1", 2, 5),
        ("P1", 2, 6),
        ("P2", 1, 1),
        ("P2", 1, 2),
    }


def test_apply_muted_node_keys_ignores_keys_with_no_matching_node(model):
    """Best-effort against a changed score: a muted key for a part/staff/
    voice that no longer exists here has nothing to apply to and must not
    raise or otherwise disturb the nodes that do exist."""
    model.apply_muted_node_keys(
        parts_muted={"NoSuchPart"},
        staves_muted={("P1", 99)},
        voices_muted={("P1", 1, 99)},
    )

    assert model.get_active_voice_tuples() == {
        ("P1", 1, 1),
        ("P1", 2, 5),
        ("P1", 2, 6),
        ("P2", 1, 1),
        ("P2", 1, 2),
    }


def test_clear_all_mute_restores_every_node_and_leaves_solo_untouched(model):
    model.toggle_mute("part_P1")
    model.toggle_solo("voice_P2_1_1")

    model.clear_all_mute()

    parts_muted, staves_muted, voices_muted = model.get_muted_node_keys()
    assert (parts_muted, staves_muted, voices_muted) == (set(), set(), set())
    assert model.any_soloed() is True, "Unmute All must not also clear solo state"


# --- get_soloed_node_keys/apply_soloed_node_keys (per-node persistence) ----

def test_get_soloed_node_keys_reads_each_nodes_own_state(model):
    model.toggle_solo("voice_P1_2_5")
    model.toggle_solo("part_P2")

    parts_soloed, staves_soloed, voices_soloed = model.get_soloed_node_keys()

    assert parts_soloed == {"P2"}
    assert staves_soloed == set()
    assert voices_soloed == {("P1", 2, 5)}


def test_soloed_node_keys_round_trip(model):
    model.toggle_solo("voice_P1_2_5")
    model.toggle_solo("part_P2")

    parts_soloed, staves_soloed, voices_soloed = model.get_soloed_node_keys()

    fresh = Region2HierarchyModel()
    fresh.build_from_score(PARTS_DATA)
    fresh.apply_soloed_node_keys(parts_soloed, staves_soloed, voices_soloed)

    assert fresh._node_lookup["voice_P1_2_5"].soloed is True
    assert fresh._node_lookup["part_P2"].soloed is True
    assert fresh._node_lookup["part_P1"].soloed is False


def test_apply_soloed_node_keys_ignores_keys_with_no_matching_node(model):
    model.apply_soloed_node_keys(
        parts_soloed={"NoSuchPart"},
        staves_soloed={("P1", 99)},
        voices_soloed={("P1", 1, 99)},
    )

    assert model.any_soloed() is False


# --- node_status_label: the wording shown against each row -----------------

def test_node_status_label_wording():
    model = Region2HierarchyModel()
    model.build_from_score(PARTS_DATA)
    node = model._node_lookup["part_P1"]
    assert node_status_label(node) == "Piano"

    node.muted = True
    assert node_status_label(node) == "Piano muted"

    node.soloed = True
    assert node_status_label(node) == "Piano muted soloed", "muted must come before soloed"

    node.muted = False
    assert node_status_label(node) == "Piano soloed"


# --- Options > Reorder Parts... ---------------------------------------------

def test_reorder_roots_reorders_the_part_rows(model):
    assert [p.part_id for p in model.roots] == ["P1", "P2"]
    model.reorder_roots(["P2", "P1"])
    assert [p.part_id for p in model.roots] == ["P2", "P1"]


def test_reorder_roots_preserves_each_nodes_mute_state(model):
    """The whole point of NOT going through build_from_score again - mute
    toggles the user already set must survive a reorder."""
    model.roots[0].muted = True  # P1 muted
    model.roots[0].children[0].muted = True  # its treble staff also muted

    model.reorder_roots(["P2", "P1"])

    p1 = next(p for p in model.roots if p.part_id == "P1")
    assert p1.muted is True
    assert p1.children[0].muted is True


def test_reorder_roots_ignores_unknown_part_ids(model):
    model.reorder_roots(["P2", "Ghost", "P1"])
    assert [p.part_id for p in model.roots] == ["P2", "P1"]


def test_reorder_roots_appends_a_known_part_missing_from_the_order(model):
    model.reorder_roots(["P2"])  # P1 not mentioned
    assert [p.part_id for p in model.roots] == ["P2", "P1"]
