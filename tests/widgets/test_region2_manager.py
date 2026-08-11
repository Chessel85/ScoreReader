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
