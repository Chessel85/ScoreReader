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
        voices_off={("P2", 1, 1)},
        metronome_enabled=True,
        voice_display_attributes={("P1", 1, 1): {"step", "string", "fret"}},
        attribute_order=["step", "string", "fret", "octave"],
    )
    score_config.save("Chessel Duet.mxl", config)

    loaded = score_config.load_for("Chessel Duet.mxl")
    assert loaded.voices_off == {("P2", 1, 1)}
    assert loaded.metronome_enabled is True
    assert loaded.voice_display_attributes == {("P1", 1, 1): {"step", "string", "fret"}}
    assert loaded.attribute_order == ["step", "string", "fret", "octave"]


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
