# tests/widgets/test_region2_manager.py
"""Region2HierarchyModel is pure state with no Qt dependency, so it needs
no qapp fixture and runs instantly."""
import pytest

from widgets.region2_manager import Region2HierarchyModel, node_breadcrumb, voice_tuples_for_node

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
    names = [n.display_name.strip() for n in model.get_visible_nodes()]

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


def test_disabling_a_staff_hides_its_voices(model):
    model.toggle_node("staff_P1_2")
    names = [n.display_name.strip() for n in model.get_visible_nodes()]

    assert "Voice 5" not in names
    assert "Bass Clef" in names, "the staff row itself stays visible"


def test_collapse_to_parts_shows_only_part_rows():
    """Ref 25/S2: a MIDI-loaded score's Region 2 shows track on/off only -
    no staff/voice rows, which for MIDI are either fake (staff) or, in every
    real file tested, always trivially 1 (voice)."""
    model = Region2HierarchyModel()
    model.build_from_score(PARTS_DATA, collapse_to_parts=True)

    names = [n.display_name.strip() for n in model.get_visible_nodes()]
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


def test_collapse_to_parts_toggle_still_hides_the_whole_part(model):
    collapsed = Region2HierarchyModel()
    collapsed.build_from_score(PARTS_DATA, collapse_to_parts=True)

    collapsed.toggle_node("part_P1")

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

    names = [n.display_name.strip() for n in model.get_visible_nodes()]
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

    model.toggle_node("part_P2")

    assert model.get_active_voice_tuples() == {
        ("P1", 1, 1),
        ("P1", 2, 5),
        ("P1", 2, 6),
    }


# F2/Ref 15 AC4: scope helpers for the attribute-order dialog - node-tree
# lookups, not the enabled-state filtering get_active_voice_tuples does.

def test_voice_tuples_for_node_voice_scope(model):
    node = model._node_lookup["voice_P1_2_5"]

    assert voice_tuples_for_node(node) == {("P1", 2, 5)}


def test_voice_tuples_for_node_staff_scope_covers_every_voice_on_that_staff(model):
    node = model._node_lookup["staff_P1_2"]

    assert voice_tuples_for_node(node) == {("P1", 2, 5), ("P1", 2, 6)}


def test_voice_tuples_for_node_part_scope_covers_every_staff_and_voice(model):
    node = model._node_lookup["part_P2"]

    assert voice_tuples_for_node(node) == {("P2", 1, 1), ("P2", 1, 2)}


def test_voice_tuples_for_node_ignores_enabled_state(model):
    """Unlike get_active_voice_tuples (Ref 7's playback filter), scope for
    the attribute-order dialog does not depend on Region 2's on/off toggle."""
    model.toggle_node("voice_P1_2_5")  # off
    node = model._node_lookup["staff_P1_2"]

    assert voice_tuples_for_node(node) == {("P1", 2, 5), ("P1", 2, 6)}


def test_node_breadcrumb_joins_the_full_path(model):
    node = model._node_lookup["voice_P1_2_5"]

    assert node_breadcrumb(node) == "Piano > Bass Clef > Voice 5"


def test_reenabling_a_parent_restores_each_childs_previous_state(model):
    """Toggling a staff off and back on must not reset its voices - each
    voice keeps whatever on/off state it had before the staff was hidden."""
    model.toggle_node("voice_P1_1_1")  # Voice 1 off

    model.toggle_node("staff_P1_1")  # hide staff 1 and its voices
    model.toggle_node("staff_P1_1")  # show it again

    assert model.get_active_voice_tuples() == {
        ("P1", 2, 5),
        ("P1", 2, 6),
        ("P2", 1, 1),
        ("P2", 1, 2),
    }, "voice 1 must still be off after its staff round-trips through off/on"


# --- Ref 27: get_off_node_keys/apply_off_node_keys (per-node persistence) --

def test_get_off_node_keys_reads_each_nodes_own_state_not_the_gated_one(model):
    """A part switched off must not report its still-individually-on
    sub-voices as off too - get_off_node_keys is the ungated read
    get_active_voice_tuples deliberately isn't."""
    model.toggle_node("part_P2")  # P2 off - its voices are still individually on

    parts_off, staves_off, voices_off = model.get_off_node_keys()

    assert parts_off == {"P2"}
    assert staves_off == set()
    assert voices_off == set(), "P2's voices are still individually ON underneath the off part"


def test_off_node_keys_round_trip_preserves_a_sub_voices_state_under_an_off_part(model):
    """Reported bug, live-tested: toggling a part off with a sub-voice still
    individually on, then reloading, used to bring that sub-voice back off
    too, because only the ancestor-gated active set was ever persisted.
    get_off_node_keys/apply_off_node_keys must round-trip losslessly."""
    model.toggle_node("part_P2")  # P2 off; P2's voices remain individually on underneath

    parts_off, staves_off, voices_off = model.get_off_node_keys()

    fresh = Region2HierarchyModel()
    fresh.build_from_score(PARTS_DATA)
    fresh.apply_off_node_keys(parts_off, staves_off, voices_off)

    p2 = fresh._node_lookup["part_P2"]
    p2_voice_1 = fresh._node_lookup["voice_P2_1_1"]
    assert p2.enabled is False, "the part itself is off, as toggled"
    assert p2_voice_1.enabled is True, (
        "the sub-voice's own individual on-state must survive the round trip"
    )

    # Switching the part back on must reveal the sub-voice still on, not
    # collapsed to off along with everything else under it.
    fresh.toggle_node("part_P2")
    assert fresh.get_active_voice_tuples() == {
        ("P1", 1, 1),
        ("P1", 2, 5),
        ("P1", 2, 6),
        ("P2", 1, 1),
        ("P2", 1, 2),
    }


def test_apply_off_node_keys_ignores_keys_with_no_matching_node(model):
    """Best-effort against a changed score: an OFF key for a part/staff/
    voice that no longer exists here has nothing to apply to and must not
    raise or otherwise disturb the nodes that do exist."""
    model.apply_off_node_keys(
        parts_off={"NoSuchPart"},
        staves_off={("P1", 99)},
        voices_off={("P1", 1, 99)},
    )

    assert model.get_active_voice_tuples() == {
        ("P1", 1, 1),
        ("P1", 2, 5),
        ("P1", 2, 6),
        ("P2", 1, 1),
        ("P2", 1, 2),
    }


# --- Options > Reorder Parts... ---------------------------------------------

def test_reorder_roots_reorders_the_part_rows(model):
    assert [p.part_id for p in model.roots] == ["P1", "P2"]
    model.reorder_roots(["P2", "P1"])
    assert [p.part_id for p in model.roots] == ["P2", "P1"]


def test_reorder_roots_preserves_each_nodes_on_off_state(model):
    """The whole point of NOT going through build_from_score again -
    on/off toggles the user already set must survive a reorder."""
    model.roots[0].enabled = False  # P1 off
    model.roots[0].children[0].enabled = False  # its treble staff also off

    model.reorder_roots(["P2", "P1"])

    p1 = next(p for p in model.roots if p.part_id == "P1")
    assert p1.enabled is False
    assert p1.children[0].enabled is False


def test_reorder_roots_ignores_unknown_part_ids(model):
    model.reorder_roots(["P2", "Ghost", "P1"])
    assert [p.part_id for p in model.roots] == ["P2", "P1"]


def test_reorder_roots_appends_a_known_part_missing_from_the_order(model):
    model.reorder_roots(["P2"])  # P1 not mentioned
    assert [p.part_id for p in model.roots] == ["P2", "P1"]
