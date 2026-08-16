# tests/widgets/test_region2_solo.py
"""Region 2 solo (F9/Alt+F9 in the Playback menu, see main_window.py).

The load-bearing property is that with nothing soloed, get_active_voice_
tuples() falls through to the plain mute-based filter unchanged."""
from widgets.region2_manager import Region2HierarchyModel

PARTS = [
    {
        "id": "P1",
        "name": "Piano",
        "staves": [
            {"id": 1, "name": "Treble stave", "voices": [1, 2]},
            {"id": 2, "name": "Bass stave", "voices": [5]},
        ],
    },
    {
        "id": "P2",
        "name": "Classical Guitar",
        "staves": [{"id": 1, "name": "Treble stave", "voices": [1]}],
    },
]


def _model():
    model = Region2HierarchyModel()
    model.build_from_score(PARTS)
    return model


def test_nothing_is_soloed_by_default_and_the_filter_is_unchanged():
    model = _model()

    assert model.any_soloed() is False
    assert model.get_active_voice_tuples() == {
        ("P1", 1, 1), ("P1", 1, 2), ("P1", 2, 5), ("P2", 1, 1),
    }


def test_soloing_a_voice_narrows_the_filter_to_just_it():
    model = _model()

    model.toggle_solo("voice_P1_1_2")

    assert model.any_soloed() is True
    assert model.get_active_voice_tuples() == {("P1", 1, 2)}


def test_soloing_a_part_activates_every_voice_beneath_it():
    model = _model()

    model.toggle_solo("part_P1")

    assert model.get_active_voice_tuples() == {("P1", 1, 1), ("P1", 1, 2), ("P1", 2, 5)}


def test_solo_overrides_a_muted_ancestor():
    """The point of a solo control: soloing something the user had muted
    should still make it audible, rather than intersecting with the mute
    state and producing silence."""
    model = _model()
    model.toggle_mute("part_P1")  # mute the whole part
    assert ("P1", 1, 1) not in model.get_active_voice_tuples()

    model.toggle_solo("voice_P1_1_1")

    assert model.get_active_voice_tuples() == {("P1", 1, 1)}


def test_clear_all_solo_restores_the_previous_mute_state_exactly():
    """"Unsolo all" must not double as "unmute everything" - a part the
    user had muted before soloing stays muted afterwards."""
    model = _model()
    model.toggle_mute("staff_P1_2")  # mute the bass stave
    before = model.get_active_voice_tuples()

    model.toggle_solo("voice_P2_1_1")
    assert model.get_active_voice_tuples() == {("P2", 1, 1)}

    model.clear_all_solo()

    assert model.any_soloed() is False
    assert model.get_active_voice_tuples() == before


def test_solo_state_survives_a_toggle_round_trip():
    model = _model()

    assert model.toggle_solo("voice_P1_1_1") is True
    assert model.toggle_solo("voice_P1_1_1") is False
    assert model.any_soloed() is False
