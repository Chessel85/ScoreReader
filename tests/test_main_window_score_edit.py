# tests/test_main_window_score_edit.py
"""ScoreEditController's dialogs: Mixer, Instruments, Key Signature, and Reorder Parts. Split from test_main_window.py (S10).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from models import mixer_settings
from widgets.instrument_dialog import InstrumentDialog
from widgets.key_signature_dialog import KeySignatureDialog
from widgets.mixer_dialog import MixerDialog
from widgets.part_order_dialog import PartOrderDialog
from tests.support.main_window_helpers import _focus, _show, load_and_wait, no_lead_in, _load_ug_import


# --- Wishlist #4: Mixer dialog ------------------------------------------

def _fake_mixer_dialog(monkeypatch, window, *, accept: bool, on_exec=None):
    """Builds a real MixerDialog from the window's own current rows, fakes
    exec() to optionally run on_exec(dialog) (e.g. emit a signal, matching
    the AttributeOrderDialog injection convention above) and then return
    Accepted/Rejected, and patches main_window.MixerDialog to hand it back
    regardless of constructor args."""
    dialog = MixerDialog(window, rows=window.playback.begin_mixer_edit())

    def fake_exec():
        if on_exec is not None:
            on_exec(dialog)
        return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected

    monkeypatch.setattr(dialog, "exec", fake_exec)
    monkeypatch.setattr("main_window.MixerDialog", lambda parent, rows: dialog)
    return dialog


def test_mixer_dialog_rows_cover_every_part_plus_click_announcer_and_cue(
    window, qtbot, score_duet
):
    load_and_wait(window, qtbot, score_duet)

    rows = window.playback.begin_mixer_edit()

    assert [label for _, label, _, _ in rows] == [
        "Piano", "Classical Guitar", "Metronome", "Position Announcer", "Performance Cue",
    ]
    # No saved mixer yet: every row shows the real engine default, not a
    # placeholder - parts/cue centred, click hard right, announcer hard left.
    assert [pan for _, _, _, pan in rows] == [0, 0, 100, -100, 0]


def test_mixer_dialog_ok_commits_and_persists_the_change(window, qtbot, minimal_score, monkeypatch):
    load_and_wait(window, qtbot, minimal_score)
    part_id = window._music_data.parts_info[0].part_id

    def edit(dialog):
        dialog.row_list.setCurrentRow(0)
        dialog.volume_spin.setValue(68)
        dialog.pan_spin.setValue(-100)

    dialog = _fake_mixer_dialog(monkeypatch, window, accept=True, on_exec=edit)
    window._show_mixer_dialog()

    # Volume is a perceived-loudness multiplier of the default (100 CC),
    # via a sqrt curve compensating FluidSynth's own audio-taper CC7
    # response - 68% -> round(100 * sqrt(0.68)) == 82.
    assert window._music_data.mixer.volume_for(part_id) == 82
    assert window._music_data.mixer.pan_for(part_id) == 0      # -100% -> full left CC 0
    assert (0, 82) in window.synth.volume_changes
    assert (0, 0) in window.synth.pan_changes

    # Ref 27-style persistence: reload the same file and the override
    # must still be there (load_score_from_file saves the outgoing file's
    # config before swapping, same mechanism attribute_order relies on).
    load_and_wait(window, qtbot, minimal_score)
    assert window._music_data.mixer.volume_for(part_id) == 82


def test_mixer_dialog_cancel_reverts_the_synth_and_leaves_the_mixer_untouched(
    window, qtbot, minimal_score, monkeypatch
):
    load_and_wait(window, qtbot, minimal_score)
    part_id = window._music_data.parts_info[0].part_id
    channel = window._music_data.get_channel_for_part(part_id)

    def edit(dialog):
        dialog.row_list.setCurrentRow(0)
        dialog.volume_spin.setValue(20)  # live-previewed, never committed

    dialog = _fake_mixer_dialog(monkeypatch, window, accept=False, on_exec=edit)
    window._show_mixer_dialog()

    assert window._music_data.mixer.is_empty()
    # The live preview did push a CC while the dialog was open - 20% via the
    # sqrt curve is round(100 * sqrt(0.2)) == 45.
    assert (channel, 45) in window.synth.volume_changes
    # ...and cancelling explicitly put the channel back to its true default -
    # cancel_mixer_edit resends every row, not just this one, so check the
    # revert batch (the calls made after the live-preview one) rather than
    # assuming this channel's revert is the very last entry overall.
    revert_calls = window.synth.volume_changes[window.synth.volume_changes.index((channel, 45)) + 1:]
    assert (channel, 100) in revert_calls


def test_switching_files_does_not_leak_a_mixer_override_onto_the_new_score(
    window, qtbot, minimal_score, score_duet, monkeypatch
):
    """Reported bug, live-tested: the synth is a long-lived singleton across
    file loads, so a channel's volume CC value from the PREVIOUS score used
    to survive untouched into a new one with no override of its own -
    apply_mixer only sent CC for parts with an explicit override. The
    user's repro was a cello set to 0% in one score's Mixer staying silent
    after switching to an unrelated score whose part happened to land on
    the same channel. Both fixtures' first part lands on channel 0
    (get_channel_for_part assigns sequentially from the low end)."""
    load_and_wait(window, qtbot, minimal_score)
    part_id = window._music_data.parts_info[0].part_id
    channel = window._music_data.get_channel_for_part(part_id)

    def edit(dialog):
        dialog.row_list.setCurrentRow(0)
        dialog.volume_spin.setValue(0)

    dialog = _fake_mixer_dialog(monkeypatch, window, accept=True, on_exec=edit)
    window._show_mixer_dialog()
    assert (channel, 0) in window.synth.volume_changes

    load_and_wait(window, qtbot, score_duet)
    new_channel = window._music_data.get_channel_for_part(window._music_data.parts_info[0].part_id)
    assert new_channel == channel
    assert window._music_data.mixer.is_empty()
    assert (channel, mixer_settings.DEFAULT_VOLUME) in window.synth.volume_changes


def test_mixer_dialog_preview_plays_without_moving_the_main_cursor(
    window, qtbot, minimal_score, monkeypatch
):
    """Alt+P / the Preview button reuses PlaybackController.audition_phrase
    (Ref 11) - update_cursor=False, so the main timeline cursor and Region 3
    selection are untouched by opening the Mixer and previewing from it."""
    load_and_wait(window, qtbot, minimal_score)
    no_lead_in(window)
    cursor_before = window._music_data.active_event_index
    window.synth.played.clear()

    dialog = _fake_mixer_dialog(
        monkeypatch, window, accept=True, on_exec=lambda d: d.preview_requested.emit()
    )
    window._show_mixer_dialog()

    assert window.synth.played != []
    assert window._music_data.active_event_index == cursor_before


def test_mixer_dialog_does_nothing_with_no_score_loaded(window, qtbot):
    """Guards the same way _show_performance_report_dialog does - opening
    the Mixer before any file is loaded must not crash."""
    window._show_mixer_dialog()


# --- S5: Instrument dialog -------------------------------------------------

def _fake_instrument_dialog(monkeypatch, window, *, accept: bool, on_exec=None):
    """Same convention as _fake_mixer_dialog: build a real InstrumentDialog
    from the window's own current parts, fake exec() to run on_exec(dialog)
    and return Accepted/Rejected, and patch main_window.InstrumentDialog to
    hand it back regardless of constructor args. Mirrors
    MainWindow._show_instrument_dialog's own row-building exactly (wishlist
    #8 follow-up: percussion_part_ids/percussion_rows too), so a percussion
    score's fake dialog behaves like the real one would."""
    rows = [(p.part_id, p.name, p.gmidi_program) for p in window._music_data.parts_info]
    percussion_part_ids = [p.part_id for p in window._music_data.parts_info if p.is_percussion]
    percussion_rows = {
        part_id: window._music_data.get_percussion_items_for_part(part_id)
        for part_id in percussion_part_ids
    }
    dialog = InstrumentDialog(
        window,
        rows=rows,
        percussion_part_ids=percussion_part_ids,
        percussion_rows=percussion_rows,
        auto_correct_enabled=window._music_data.percussion_auto_correct_enabled,
    )

    def fake_exec():
        if on_exec is not None:
            on_exec(dialog)
        return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected

    monkeypatch.setattr(dialog, "exec", fake_exec)
    monkeypatch.setattr("main_window.InstrumentDialog", lambda parent, rows, **kwargs: dialog)
    return dialog


def test_instrument_dialog_ok_renames_the_part_and_reprograms_it(
    window, qtbot, minimal_score, monkeypatch
):
    load_and_wait(window, qtbot, minimal_score)
    part_id = window._music_data.parts_info[0].part_id

    def edit(dialog):
        dialog.row_list.setCurrentRow(0)
        dialog.name_edit.setText("Renamed Part")
        dialog.instrument_combo.setCurrentText("Clarinet")

    _fake_instrument_dialog(monkeypatch, window, accept=True, on_exec=edit)
    window._show_instrument_dialog()

    assert window._music_data.parts_info[0].name == "Renamed Part"
    assert window._music_data.parts_info[0].gmidi_program == 72

    # NoteData.part_name kept in sync (R5's invariant) - Region 3/the
    # Performance Report both key off it.
    matching = [
        n for s in window._music_data.timeline_slices for n in s.notes if n.part_id == part_id
    ]
    assert matching and all(n.part_name == "Renamed Part" for n in matching)

    # Region 2's part row reflects the rename in place.
    assert window.region_2.visible_item_texts()[0].startswith("Renamed Part")

    # Ref 27-style persistence: reload the same file and the override must
    # still be there.
    load_and_wait(window, qtbot, minimal_score)
    assert window._music_data.parts_info[0].name == "Renamed Part"
    assert window._music_data.parts_info[0].gmidi_program == 72


def test_instrument_dialog_cancel_leaves_the_part_untouched(
    window, qtbot, minimal_score, monkeypatch
):
    load_and_wait(window, qtbot, minimal_score)
    original_name = window._music_data.parts_info[0].name
    original_program = window._music_data.parts_info[0].gmidi_program

    def edit(dialog):
        dialog.row_list.setCurrentRow(0)
        dialog.name_edit.setText("Should Not Stick")
        dialog.instrument_combo.setCurrentText("Clarinet")

    _fake_instrument_dialog(monkeypatch, window, accept=False, on_exec=edit)
    window._show_instrument_dialog()

    assert window._music_data.parts_info[0].name == original_name
    assert window._music_data.parts_info[0].gmidi_program == original_program


def test_instrument_dialog_rename_does_not_reset_region_2_toggle_state(
    window, qtbot, score_duet, monkeypatch
):
    """The rename must go through Region2ListWidget.rename_part (an
    in-place label edit), never a load_score_structure rebuild - that would
    silently unmute every part/staff/voice again, discarding whatever the
    user had already muted."""
    load_and_wait(window, qtbot, score_duet)
    _show(window, qtbot)
    _focus(window.region_2)
    window.region_2.select_node(window.region_2.model_manager.roots[0].node_id)
    qtbot.keyClick(window.region_2, Qt.Key.Key_F8)  # mute the first part
    assert window.region_2.model_manager.roots[0].muted is True

    def edit(dialog):
        dialog.row_list.setCurrentRow(0)
        dialog.name_edit.setText("Renamed")

    _fake_instrument_dialog(monkeypatch, window, accept=True, on_exec=edit)
    window._show_instrument_dialog()

    assert window.region_2.model_manager.roots[0].muted is True
    assert window.region_2.model_manager.roots[0].display_name == "Renamed"


def test_instrument_dialog_percussion_auto_correct_updates_sound_and_voice_label(
    window, qtbot, score_hit_it, monkeypatch
):
    """Wishlist #8 follow-up, end to end: ticking "Apply MusicXML offset for
    percussion" on Hit It.mxl must (a) change what actually plays for a
    percussion note, and (b) update Region 2's voice label - without
    resetting any existing mute state (same load_score_structure-avoidance
    guarantee as a real part rename)."""
    load_and_wait(window, qtbot, score_hit_it)
    part_id = next(p.part_id for p in window._music_data.parts_info if p.name == "Drum Kit")

    _show(window, qtbot)
    _focus(window.region_2)
    window.region_2.select_node(window.region_2.model_manager.roots[0].node_id)
    qtbot.keyClick(window.region_2, Qt.Key.Key_F8)  # mute Drum Kit
    assert window.region_2.model_manager.roots[0].muted is True

    def edit(dialog):
        dialog.auto_correct_checkbox.setChecked(True)

    _fake_instrument_dialog(monkeypatch, window, accept=True, on_exec=edit)
    window._show_instrument_dialog()

    assert window._music_data.percussion_auto_correct_enabled is True
    items = window._music_data.get_percussion_items_for_part(part_id)
    hihat_key = next(key for key, name, _ in items if name == "Closed Hi-Hat")
    _, _, sounding_key = next(i for i in items if i[0] == hihat_key)
    assert sounding_key == 42, "Closed Hi-Hat now sounds like GM's real 42, not the file's declared 43"

    voice_node = next(
        n for n in window.region_2.model_manager._node_lookup.values()
        if n.part_id == part_id and n.node_type == "voice" and n.voice_id == hihat_key[1]
    )
    assert voice_node.display_name == "Closed Hi-Hat"

    assert window.region_2.model_manager.roots[0].muted is True, "the earlier mute must survive"


def test_instrument_dialog_percussion_item_rename_and_reload_persists(
    window, qtbot, score_hit_it, monkeypatch
):
    """Ref 27-style persistence: a percussion item rename/sound override
    must survive a reload, same guarantee every other override already
    has."""
    load_and_wait(window, qtbot, score_hit_it)
    part_id = next(p.part_id for p in window._music_data.parts_info if p.name == "Drum Kit")
    item_key = next(
        key for key, name, _ in window._music_data.get_percussion_items_for_part(part_id)
        if name == "Closed Hi-Hat"
    )

    def edit(dialog):
        dialog.row_list.setCurrentRow(
            next(
                i for i in range(dialog.row_list.count())
                if dialog.row_list.item(i).text() == "Closed Hi-Hat"
            )
        )
        dialog.name_edit.setText("Renamed Hat")

    _fake_instrument_dialog(monkeypatch, window, accept=True, on_exec=edit)
    window._show_instrument_dialog()

    assert window._music_data.percussion_item_name_overrides[item_key] == "Renamed Hat"

    load_and_wait(window, qtbot, score_hit_it)
    items = window._music_data.get_percussion_items_for_part(part_id)
    assert any(name == "Renamed Hat" for _, name, _ in items)


def _fake_key_signature_dialog(monkeypatch, window, *, accept: bool, on_exec=None):
    """Same convention as _fake_mixer_dialog/_fake_instrument_dialog."""
    current_key = (
        window._music_data.key_signature_override_fifths,
        window._music_data.key_signature_override_mode,
    )
    dialog = KeySignatureDialog(window, current_key=current_key)

    def fake_exec():
        if on_exec is not None:
            on_exec(dialog)
        return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected

    monkeypatch.setattr(dialog, "exec", fake_exec)
    monkeypatch.setattr(
        "main_window.KeySignatureDialog", lambda parent, current_key: dialog
    )
    return dialog


def test_key_signature_override_updates_region_1_and_status_bar_and_persists(
    window, qtbot, midi_test1, monkeypatch
):
    """midi_test1 has no key metadata at all (files/midi/readme.md.txt),
    so it opens as fifths=0/"C major / A minor" - a real case the override
    is meant for."""
    load_and_wait(window, qtbot, midi_test1)

    def edit(dialog):
        g_major_index = next(
            i for i in range(dialog.key_combo.count())
            if dialog.key_combo.itemText(i) == "G major"
        )
        dialog.key_combo.setCurrentIndex(g_major_index)

    _fake_key_signature_dialog(monkeypatch, window, accept=True, on_exec=edit)
    window._show_key_signature_dialog()

    assert window._music_data.key_signature_override_fifths == 1
    assert window._music_data.key_signature_override_mode == "major"
    assert window._music_data.get_region_1_data()["Key Signature"] == "G major"
    assert window._music_data.get_status_bar_fields()[1] == "Key: G major"

    # Ref 27-style persistence: reload the same file and the override must
    # still be there.
    load_and_wait(window, qtbot, midi_test1)
    assert window._music_data.key_signature_override_fifths == 1
    assert window._music_data.key_signature_override_mode == "major"


def test_key_signature_dialog_cancel_leaves_the_override_untouched(
    window, qtbot, midi_test1, monkeypatch
):
    load_and_wait(window, qtbot, midi_test1)

    def edit(dialog):
        g_major_index = next(
            i for i in range(dialog.key_combo.count())
            if dialog.key_combo.itemText(i) == "G major"
        )
        dialog.key_combo.setCurrentIndex(g_major_index)

    _fake_key_signature_dialog(monkeypatch, window, accept=False, on_exec=edit)
    window._show_key_signature_dialog()

    assert window._music_data.key_signature_override_fifths is None
    assert window._music_data.key_signature_override_mode is None


def test_key_signature_dialog_does_nothing_with_no_score_loaded(window, qtbot):
    window._show_key_signature_dialog()


def test_instrument_dialog_does_nothing_with_no_score_loaded(window, qtbot):
    window._show_instrument_dialog()


# --- Options > Reorder Parts... -----------------------------------------

def _fake_part_order_dialog(monkeypatch, window, *, accept: bool, on_exec=None):
    """Same convention as _fake_instrument_dialog above."""
    parts = [(p.part_id, p.name) for p in window._music_data.parts_info]
    dialog = PartOrderDialog(window, parts=parts)

    def fake_exec():
        if on_exec is not None:
            on_exec(dialog)
        return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected

    monkeypatch.setattr(dialog, "exec", fake_exec)
    monkeypatch.setattr("main_window.PartOrderDialog", lambda parent, parts: dialog)
    return dialog


def test_reordering_parts_updates_region_2_and_region_3_order_without_resetting_toggles(
    window, qtbot, monkeypatch
):
    """End-to-end: the user's own stated reason for this feature - NVDA
    reads whichever part's row Region 3 lands on first, and this dialog
    lets them choose which part that is."""
    content = "[Verse 1]\n\n[tab][ch]C[/ch]     [ch]G[/ch]\nHello world[/tab]\n"
    _load_ug_import(window, qtbot, monkeypatch, content)

    assert [p.part_id for p in window._music_data.parts_info] == ["chords", "lyrics"]

    # Mute Lyrics first, to prove the reorder doesn't reset it.
    _show(window, qtbot)
    _focus(window.region_2)
    window.region_2.select_node("part_lyrics")
    qtbot.keyClick(window.region_2, Qt.Key.Key_F8)
    assert window.region_2.model_manager.roots[1].muted is True

    def move_lyrics_to_front(dialog):
        dialog.part_list.setCurrentRow(1)  # "Lyrics"
        dialog._move(-1)

    _fake_part_order_dialog(monkeypatch, window, accept=True, on_exec=move_lyrics_to_front)
    window._show_part_order_dialog()

    assert [p.part_id for p in window._music_data.parts_info] == ["lyrics", "chords"]
    assert [n.part_id for n in window.region_2.model_manager.roots] == ["lyrics", "chords"]
    lyrics_node = next(n for n in window.region_2.model_manager.roots if n.part_id == "lyrics")
    assert lyrics_node.muted is True, "reordering must not reset the mute toggle"

    window._music_data.active_event_index = 0
    window._update_timeline_views()
    row_texts = [window.region_3.item(i).text() for i in range(window.region_3.count())]
    # Lyrics is muted, so only the Chords row shows - but it's now the ONLY
    # part, proving reorder_parts touched the underlying note order too
    # (with Lyrics unmuted, its row would come first).
    assert row_texts == ["C"]


def test_part_order_dialog_does_nothing_on_cancel(window, qtbot, monkeypatch):
    content = "[Verse 1]\n\n[tab][ch]C[/ch]     [ch]G[/ch]\nHello world[/tab]\n"
    _load_ug_import(window, qtbot, monkeypatch, content)

    def move_lyrics_to_front(dialog):
        dialog.part_list.setCurrentRow(1)
        dialog._move(-1)

    _fake_part_order_dialog(monkeypatch, window, accept=False, on_exec=move_lyrics_to_front)
    window._show_part_order_dialog()

    assert [p.part_id for p in window._music_data.parts_info] == ["chords", "lyrics"]


def test_part_order_dialog_does_nothing_with_no_score_loaded(window, qtbot):
    window._show_part_order_dialog()  # must not crash
