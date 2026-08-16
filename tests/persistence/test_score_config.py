# tests/persistence/test_score_config.py
"""config_dir() is redirected into a per-test tmp_path by conftest's
autouse _isolate_persistence fixture, so these never touch the real
developer machine's %LOCALAPPDATA%."""
from persistence import score_config
from persistence.score_config import ScoreConfig


def test_path_for_is_keyed_by_basename_and_extension_only():
    """Ref 27: no path/location component - the same music file found again
    under a different folder (the user moved it) must resolve to the same
    .rsc, and the outer filename (not any internal member name) is what's
    used - BluePeter.mid and BluePeter.mxl get separate configs."""
    assert score_config.path_for(r"C:\scores\Chessel Duet.mxl").name == "Chessel Duet.mxl.rsc"
    assert (
        score_config.path_for(r"C:\scores\Chessel Duet.mxl")
        == score_config.path_for(r"D:\backup\Chessel Duet.mxl")
    )
    assert (
        score_config.path_for("BluePeter.mid").name
        != score_config.path_for("BluePeter.mxl").name
    )


def test_load_for_with_no_saved_file_returns_none():
    assert score_config.load_for("nothing_saved_for_this.mxl") is None


def test_save_then_load_round_trips_all_fields():
    config = ScoreConfig(
        parts_muted={"P3"},
        staves_muted={("P1", 2)},
        voices_muted={("P2", 1, 1)},
        parts_soloed={"P2"},
        staves_soloed={("P1", 1)},
        voices_soloed={("P3", 1, 1)},
        metronome_enabled=True,
        position_announcer_enabled=True,
        voice_display_attributes={("P1", 1, 1): {"step", "string", "fret"}},
        attribute_order=["step", "string", "fret", "octave"],
    )
    score_config.save("Chessel Duet.mxl", config)

    loaded = score_config.load_for("Chessel Duet.mxl")
    assert loaded.parts_muted == {"P3"}
    assert loaded.staves_muted == {("P1", 2)}
    assert loaded.voices_muted == {("P2", 1, 1)}
    assert loaded.parts_soloed == {"P2"}
    assert loaded.staves_soloed == {("P1", 1)}
    assert loaded.voices_soloed == {("P3", 1, 1)}
    assert loaded.metronome_enabled is True
    assert loaded.position_announcer_enabled is True
    assert loaded.voice_display_attributes == {("P1", 1, 1): {"step", "string", "fret"}}
    assert loaded.attribute_order == ["step", "string", "fret", "octave"]


def test_load_for_a_file_missing_parts_muted_staves_muted_keys():
    """Backward compatibility: an .rsc missing "parts_muted"/"staves_muted"
    keys entirely (an older build, or a hand-edited file) must default those
    to empty sets rather than erroring."""
    path = score_config.path_for("Chessel Duet.mxl")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"schema_version": 2, "voices_muted": ["P2|1|1"], "metronome_enabled": false, '
        '"voice_display_attributes": {}, "attribute_order": []}',
        encoding="utf-8",
    )

    loaded = score_config.load_for("Chessel Duet.mxl")

    assert loaded.parts_muted == set()
    assert loaded.staves_muted == set()
    assert loaded.voices_muted == {("P2", 1, 1)}


def test_load_for_a_file_saved_before_solo_existed():
    """An .rsc written before mute/solo were split apart has no
    "parts_soloed"/"staves_soloed"/"voices_soloed" keys at all - loading it
    must default those to empty sets rather than erroring."""
    path = score_config.path_for("Chessel Duet.mxl")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"schema_version": 2, "parts_muted": ["P3"], "metronome_enabled": false, '
        '"voice_display_attributes": {}, "attribute_order": []}',
        encoding="utf-8",
    )

    loaded = score_config.load_for("Chessel Duet.mxl")

    assert loaded.parts_muted == {"P3"}
    assert loaded.parts_soloed == set()
    assert loaded.staves_soloed == set()
    assert loaded.voices_soloed == set()


def test_load_for_a_file_saved_before_position_announcer_existed():
    """Same backward-compatibility guarantee (Ref 28 added this key after
    metronome_enabled already existed): missing "position_announcer_enabled"
    defaults to False rather than erroring."""
    path = score_config.path_for("Chessel Duet.mxl")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"schema_version": 1, "voices_muted": [], "metronome_enabled": true, '
        '"voice_display_attributes": {}, "attribute_order": []}',
        encoding="utf-8",
    )

    loaded = score_config.load_for("Chessel Duet.mxl")

    assert loaded.metronome_enabled is True
    assert loaded.position_announcer_enabled is False


def test_delete_for_removes_the_file_and_is_safe_when_missing():
    score_config.save("Chessel Duet.mxl", ScoreConfig())
    assert score_config.load_for("Chessel Duet.mxl") is not None

    score_config.delete_for("Chessel Duet.mxl")
    assert score_config.load_for("Chessel Duet.mxl") is None

    score_config.delete_for("Chessel Duet.mxl")  # no error on a second delete


def test_load_for_with_corrupt_file_returns_none():
    path = score_config.path_for("Chessel Duet.mxl")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not valid json{{{", encoding="utf-8")

    assert score_config.load_for("Chessel Duet.mxl") is None
