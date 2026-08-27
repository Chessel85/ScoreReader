# tests/test_main_window_ug_import.py
"""File > Import from Ultimate Guitar and the .ug save/open round trip. Split from test_main_window.py (S10). The _fake_ug_import_dialog / _fake_ug_source / _load_ug_import helpers moved to tests/support/main_window_helpers.py (Recent Files and Reorder Parts tests need them too).
"""

from tests.support.main_window_helpers import load_and_wait, _fake_ug_import_dialog, _fake_ug_source, _load_ug_import


# --- Experimental (feature/ug-import): File > Import from Ultimate Guitar --

def test_ultimate_guitar_import_populates_two_flat_region_2_parts_and_region_3(
    window, qtbot, monkeypatch, null_synth
):
    """End-to-end: File > Import from Ultimate Guitar... (dialog -> a fake,
    offline UgReader.load() so no real network call happens in tests) shows
    the Chords/Lyrics parts as flat, childless Region 2 rows (collapse_to_parts
    via MusicData.is_ug) and Region 3 shows the chord plus its lyric
    fragment together; auditioning the Chords voice sounds a real chord and
    never the Lyrics voice, which carries no midi_pitch at all."""
    content = "[Verse 1]\n\n[tab][ch]C[/ch]     [ch]G[/ch]\nHello world[/tab]\n"
    monkeypatch.setattr("parsers.ug_reader.read_ug_source", lambda url: _fake_ug_source(content))

    _fake_ug_import_dialog(
        monkeypatch, window, url="https://tabs.ultimate-guitar.com/tab/test/test-chords-1"
    )
    window.open_ultimate_guitar_import_dialog()
    qtbot.waitUntil(lambda: window._load_thread is None, timeout=5000)

    assert window._music_data.is_ug
    nodes = window.region_2.model_manager.get_visible_nodes()
    assert [n.node_type for n in nodes] == ["part", "part"]
    assert {n.display_name for n in nodes} == {"Chords", "Lyrics"}

    # Move onto the second chord ("G", paired with the "world" lyric
    # fragment) and confirm Region 3 shows both together.
    window._music_data.active_event_index = 1
    window._update_timeline_views()
    assert window.region_3.count() == 2
    row_texts = [window.region_3.item(i).text() for i in range(window.region_3.count())]
    assert row_texts == ["G", "world"]

    null_synth.played.clear()
    window._audition_current_selection()
    assert null_synth.played, "the Chords voice must audition a real chord"
    sounded_pitches = {p for group in null_synth.played for p in group["midi_notes"]}
    from music21 import harmony
    expected = {p.midi for p in harmony.ChordSymbol("G").pitches}
    assert sounded_pitches == expected


def test_ultimate_guitar_import_dialog_does_nothing_on_cancel(window, qtbot, monkeypatch):
    _fake_ug_import_dialog(
        monkeypatch, window, url="https://tabs.ultimate-guitar.com/tab/test/test-chords-1",
        accept=False,
    )
    window.open_ultimate_guitar_import_dialog()
    assert window._music_data is None


def test_save_ultimate_guitar_import_writes_a_file_and_updates_file_path(
    window, qtbot, monkeypatch, tmp_path
):
    """File > Save Ultimate Guitar Import As... - the app's first-ever save
    capability. After saving, the score must behave exactly like a file
    that was opened normally: file_path becomes the real saved path, so
    .rsc persistence/the window title key off it the same way every other
    format already does."""
    content = "[Verse 1]\n\n[tab][ch]C[/ch]     [ch]G[/ch]\nHello world[/tab]\n"
    _load_ug_import(window, qtbot, monkeypatch, content)

    save_path = str(tmp_path / "Test Song.ug")
    monkeypatch.setattr(
        "main_window.QFileDialog.getSaveFileName", lambda *a, **k: (save_path, "")
    )
    window.save_ultimate_guitar_import_as()

    import os
    assert os.path.exists(save_path)
    assert window._music_data.file_path == save_path
    assert window.windowTitle() == "Recall Score - Test Song.ug"


def test_save_ultimate_guitar_import_does_nothing_with_no_score_loaded(window, qtbot):
    window.save_ultimate_guitar_import_as()  # must not crash


def test_save_ultimate_guitar_import_does_nothing_for_a_non_ug_score(
    window, qtbot, monkeypatch, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)
    called = []
    monkeypatch.setattr(
        "main_window.QFileDialog.getSaveFileName", lambda *a, **k: called.append(True)
    )
    window.save_ultimate_guitar_import_as()
    assert called == []


def test_opening_a_saved_ug_file_reproduces_the_original_import(
    window, qtbot, monkeypatch, tmp_path
):
    """Full round trip through the real File > Open path (ScoreLoadThread's
    new .ug dispatch branch, no network involved since it's a local file) -
    a saved-and-reopened import must look identical to the live one it came
    from."""
    content = "[Verse 1]\n\n[tab][ch]C[/ch]     [ch]G[/ch]\nHello world[/tab]\n"
    _load_ug_import(window, qtbot, monkeypatch, content)

    save_path = str(tmp_path / "Test Song.ug")
    monkeypatch.setattr(
        "main_window.QFileDialog.getSaveFileName", lambda *a, **k: (save_path, "")
    )
    window.save_ultimate_guitar_import_as()

    load_and_wait(window, qtbot, save_path)

    assert window._music_data.is_ug
    assert window._music_data.file_path == save_path
    nodes = window.region_2.model_manager.get_visible_nodes()
    assert {n.display_name for n in nodes} == {"Chords", "Lyrics"}
    window._music_data.active_event_index = 1
    window._update_timeline_views()
    row_texts = [window.region_3.item(i).text() for i in range(window.region_3.count())]
    assert row_texts == ["G", "world"]


def test_auditioning_a_ug_bar_with_strumming_data_plays_a_strummed_bar(
    window, qtbot, monkeypatch, null_synth
):
    """End-to-end: a UG import that has real strummings data must audition
    through synth.play_strummed_bar (a real arpeggiated pattern), not the
    flat synth.play_chord every other format still uses."""
    content = "[Verse 1]\n\n[tab][ch]C[/ch]     [ch]G[/ch]\nHello world[/tab]\n"
    _load_ug_import(window, qtbot, monkeypatch, content, strum_codes=[1, 202, 101])

    null_synth.played.clear()
    null_synth.strummed_bars.clear()
    window._audition_current_selection()

    assert null_synth.strummed_bars, "must route through the strummed-bar path"
    assert null_synth.played == [], "must NOT also play a flat chord"
    call = null_synth.strummed_bars[-1]
    assert call["pattern"] == ["down", "mute", "up"]
    from music21 import harmony
    assert set(call["midi_pitches"]) == {p.midi for p in harmony.ChordSymbol("C").pitches}


def test_auditioning_a_ug_bar_with_no_strumming_data_still_plays_a_flat_chord(
    window, qtbot, monkeypatch, null_synth
):
    """A UG tab with no strummings block at all must fall straight through
    to the unchanged play_chord path - no regression for a tab lacking
    that data."""
    content = "[Verse 1]\n\n[tab][ch]C[/ch]     [ch]G[/ch]\nHello world[/tab]\n"
    _load_ug_import(window, qtbot, monkeypatch, content, strum_codes=[])

    null_synth.played.clear()
    null_synth.strummed_bars.clear()
    window._audition_current_selection()

    assert null_synth.played, "must use the ordinary flat-chord path"
    assert null_synth.strummed_bars == []


def test_auditioning_a_non_ug_score_never_uses_the_strummed_bar_path(
    window, qtbot, null_synth, minimal_score
):
    load_and_wait(window, qtbot, minimal_score)

    null_synth.played.clear()
    null_synth.strummed_bars.clear()
    window._audition_current_selection()

    assert null_synth.strummed_bars == []
