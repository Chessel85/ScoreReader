# tests/test_main_window_persistence.py
"""UK/US terminology toggle, Ref 27 per-file persistence / window title / Edit menu, and File > Recent Files. Split from test_main_window.py (S10).
"""
from PySide6.QtCore import QLocale, Qt

from main_window import MainWindow, detect_default_uk_terms
from tests.support.main_window_helpers import _focus, _show, load_and_wait, _load_ug_import


# --- F4/D-6: UK/US terminology toggle -------------------------------------

def test_detect_default_uk_terms_true_for_a_non_us_locale():
    assert detect_default_uk_terms(QLocale(QLocale.Language.English, QLocale.Country.UnitedKingdom)) is True
    assert detect_default_uk_terms(QLocale(QLocale.Language.German, QLocale.Country.Germany)) is True


def test_detect_default_uk_terms_false_only_for_a_us_locale():
    assert detect_default_uk_terms(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)) is False


def test_set_uk_terms_updates_music_data_menu_and_status_bar(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    assert window.uk_language_action.isChecked() is False
    assert window.us_language_action.isChecked() is True
    assert window.status_bar._fields[0].text().startswith("Measure ")

    window.set_uk_terms(True)

    assert window._music_data.uk_terms is True
    assert window.uk_language_action.isChecked() is True
    assert window.us_language_action.isChecked() is False
    assert window.status_bar._fields[0].text().startswith("Bar ")
    assert window.goto_measure_action.text() == "&Go to Bar..."

    window.set_uk_terms(False)

    assert window._music_data.uk_terms is False
    assert window.uk_language_action.isChecked() is False
    assert window.us_language_action.isChecked() is True
    assert window.status_bar._fields[0].text().startswith("Measure ")
    assert window.goto_measure_action.text() == "&Go to Measure..."


def test_terminology_language_actions_fire_set_uk_terms(window, qtbot, minimal_score):
    """Live-tested feedback: a submenu of two mutually exclusive, checkable
    items (QActionGroup) rather than one toggle, so "at least one ticked" is
    always visibly true."""
    load_and_wait(window, qtbot, minimal_score)

    window.uk_language_action.trigger()
    assert window._music_data.uk_terms is True
    assert window.uk_language_action.isChecked() is True
    assert window.us_language_action.isChecked() is False

    window.us_language_action.trigger()
    assert window._music_data.uk_terms is False
    assert window.uk_language_action.isChecked() is False
    assert window.us_language_action.isChecked() is True


def test_set_uk_terms_works_with_no_score_loaded(qtbot, null_synth):
    """A session preference, not a per-score one - must still set the
    preference and update the menu even before any file is opened (unlike
    toggle_metronome, which is a no-op with no score)."""
    w = MainWindow(synth=null_synth, uk_terms=False)
    qtbot.addWidget(w)
    assert w.uk_language_action.isChecked() is False

    w.set_uk_terms(True)

    assert w._uk_terms is True
    assert w.uk_language_action.isChecked() is True
    assert w.us_language_action.isChecked() is False


def test_uk_terms_preference_survives_loading_a_new_score(window, qtbot, minimal_score):
    """MusicData is wholly replaced on every file load - the preference
    must be reapplied, or it would silently reset to MusicData's own
    bare-construction default (US) on every open."""
    load_and_wait(window, qtbot, minimal_score)
    window.set_uk_terms(True)
    assert window._music_data.uk_terms is True

    load_and_wait(window, qtbot, minimal_score)

    assert window._music_data.uk_terms is True
    assert window.uk_language_action.isChecked() is True


# --- Ref 27: app naming, window title, Edit menu, per-file persistence ------

def test_window_title_before_any_file_is_loaded(window):
    assert window.windowTitle() == "Recall Score"


def test_window_title_shows_loaded_filename(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)

    assert window.windowTitle() == "Recall Score - minimal_4_4.musicxml"


def test_clear_preferences_action_disabled_with_no_file_loaded(window):
    assert window.clear_preferences_action.isEnabled() is False
    assert window.clear_preferences_action.text() == "&Clear Preferences"


def test_clear_preferences_action_enabled_and_labelled_after_load(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)

    assert window.clear_preferences_action.isEnabled() is True
    assert window.clear_preferences_action.text() == "&Clear Preferences for minimal_4_4.musicxml"


def test_open_local_folder_action_opens_the_config_directory(window, monkeypatch):
    from pathlib import Path

    from persistence import score_config

    opened = []
    monkeypatch.setattr(
        "main_window.QDesktopServices.openUrl",
        lambda url: opened.append(url.toLocalFile()),
    )

    window._open_score_config_folder()

    assert len(opened) == 1
    assert Path(opened[0]) == score_config.config_dir()


def test_clear_preferences_deletes_the_saved_config(window, qtbot, minimal_score):
    from persistence import score_config

    load_and_wait(window, qtbot, minimal_score)
    window.toggle_metronome()
    window._save_current_score_config()
    assert score_config.load_for(minimal_score) is not None

    window._clear_current_score_preferences()

    assert score_config.load_for(minimal_score) is None
    qtbot.waitUntil(lambda: window._load_thread is None, timeout=5000)


def test_clear_preferences_also_resets_the_live_session(window, qtbot, minimal_score):
    """Reported bug: clearing used to only delete the on-disk .rsc, leaving
    the already-loaded MusicData/Region 2 untouched - a solo toggled before
    clearing stayed soloed even though the saved config was gone. Fixed by
    reloading the same file straight after deleting (see
    MainWindow._clear_current_score_preferences), the same fresh-defaults
    path a normal open takes."""
    load_and_wait(window, qtbot, minimal_score)
    window.toggle_metronome()
    window.region_2.model_manager.toggle_solo("voice_P1_1_1")
    window._save_current_score_config()
    assert window._music_data.metronome_enabled is True
    assert window.region_2.model_manager.node("voice_P1_1_1").soloed is True

    window._clear_current_score_preferences()
    qtbot.waitUntil(lambda: window._load_thread is None, timeout=5000)

    assert window._music_data.metronome_enabled is False
    assert window.region_2.model_manager.node("voice_P1_1_1").soloed is False


def test_closing_the_window_saves_the_current_score_config(window, qtbot, minimal_score):
    from persistence import score_config

    load_and_wait(window, qtbot, minimal_score)
    window.toggle_metronome()

    window.close()

    saved = score_config.load_for(minimal_score)
    assert saved is not None
    assert saved.metronome_enabled is True


def test_voice_filter_persists_across_reload_of_same_file(
    window, qtbot, flute_crotchets_viola_semibreves_score
):
    """Live-tested regression: _update_ui_regions rebuilds Region 2 from
    scratch via load_score_structure, which resets every node to its
    default muted=False and - through the very same filter_changed signal
    a live toggle uses - silently overwrote the active_voice_filter
    MusicData.apply_config had just restored, so a saved mute toggle came
    back unmuted after every reload. _on_score_loaded must hand the saved
    per-node toggles to Region 2 (apply_muted_node_keys) after that
    rebuild, not rely on apply_config's write to MusicData surviving it."""
    load_and_wait(window, qtbot, flute_crotchets_viola_semibreves_score)

    _show(window, qtbot)
    _focus(window.region_2)
    window.region_2.select_node("part_P2")
    qtbot.keyClick(window.region_2, Qt.Key.Key_F8)
    assert window._music_data.active_voice_filter == {("P1", 1, 1)}

    load_and_wait(window, qtbot, flute_crotchets_viola_semibreves_score)

    assert window._music_data.active_voice_filter == {("P1", 1, 1)}
    assert window.region_2.model_manager.node("part_P2").muted is True


def test_cursor_position_persists_across_reload_of_same_file(
    window, qtbot, flute_crotchets_viola_semibreves_score
):
    load_and_wait(window, qtbot, flute_crotchets_viola_semibreves_score)

    window._music_data.active_event_index = 4
    window._save_current_score_config()

    load_and_wait(window, qtbot, flute_crotchets_viola_semibreves_score)

    assert window._music_data.active_event_index == 4


def test_initial_audition_on_reload_respects_the_restored_voice_filter(
    window, qtbot, null_synth, flute_crotchets_viola_semibreves_score
):
    """Live-tested regression, found right after the filter-persistence fix
    above: the filter itself was restored correctly (Region 2 showed viola
    off, subsequent navigation excluded it), but _update_ui_regions's own
    initial audition (play_all=True) fired BEFORE the restored filter was
    handed to Region 2, so the very first sound on load still included the
    voice that was supposed to be off. _on_score_loaded now suppresses that
    first audition when there's a filter to restore and fires it itself once
    Region 2's restored state is actually in effect."""
    load_and_wait(window, qtbot, flute_crotchets_viola_semibreves_score)
    _show(window, qtbot)
    _focus(window.region_2)
    window.region_2.select_node("part_P2")
    qtbot.keyClick(window.region_2, Qt.Key.Key_F8)  # viola muted

    null_synth.played.clear()
    load_and_wait(window, qtbot, flute_crotchets_viola_semibreves_score)

    assert len(null_synth.played) == 1, "must not audition twice (once wrong, once corrected)"
    assert null_synth.played[0]["midi_notes"] == [72]  # flute's C5 only, not the viola too


def test_a_sub_staffs_own_toggle_survives_reload_under_an_off_part(
    window, qtbot, dynamics_articulation_fingering_score
):
    """Reported bug, live-tested: muting a part with a sub-element still
    individually unmuted, closing, then reopening the score showed the
    part correctly muted - but unmuting the part again revealed its
    sub-elements had also silently gone muted, losing their original state.
    dynamics_articulation_fingering_score's Piano (P1) has two staves;
    mute staff 2 individually, then the whole Piano part (staff 1 stays
    individually unmuted underneath), reload, and unmute Piano again -
    staff 1 must come back unmuted and staff 2 must still be muted, exactly
    as they were before the part was toggled."""
    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    _show(window, qtbot)
    _focus(window.region_2)

    window.region_2.select_node("staff_P1_2")
    qtbot.keyClick(window.region_2, Qt.Key.Key_F8)  # staff 2 muted, staff 1 stays unmuted

    window.region_2.select_node("part_P1")
    qtbot.keyClick(window.region_2, Qt.Key.Key_F8)  # whole Piano part muted

    load_and_wait(window, qtbot, dynamics_articulation_fingering_score)
    _focus(window.region_2)

    assert window.region_2.model_manager.node("part_P1").muted is True

    window.region_2.select_node("part_P1")
    qtbot.keyClick(window.region_2, Qt.Key.Key_F8)  # Piano unmuted again

    assert window.region_2.model_manager.node("staff_P1_1").muted is False, (
        "staff 1 was individually unmuted before the part was muted - must come back unmuted"
    )
    assert window.region_2.model_manager.node("staff_P1_2").muted is True, (
        "staff 2 was individually muted before the part was muted - must stay muted"
    )


# --- File > Close -----------------------------------------------------

def test_close_action_disabled_until_a_score_is_loaded(window, qtbot, minimal_score):
    assert window.close_action.isEnabled() is False

    load_and_wait(window, qtbot, minimal_score)
    assert window.close_action.isEnabled() is True

    window.close_score()
    assert window.close_action.isEnabled() is False


def test_close_score_commits_the_current_config(window, qtbot, minimal_score):
    from persistence import score_config

    load_and_wait(window, qtbot, minimal_score)
    window.toggle_metronome()

    window.close_score()

    saved = score_config.load_for(minimal_score)
    assert saved is not None
    assert saved.metronome_enabled is True


def test_close_score_reverts_to_first_run_state(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    assert window.region_1.count() > 0
    assert window.region_3.count() > 0

    window.close_score()

    assert window._music_data is None
    assert window.sequencer is None
    assert window.windowTitle() == "Recall Score"
    assert window.region_1.count() == 0
    assert window.region_2.model_manager.roots == []
    assert window.region_3.count() == 0
    assert window.region_4.count() == 0
    assert window.status_bar._fields[0].text() == "Measure - beat -"
    assert window.clear_preferences_action.isEnabled() is False
    assert window.clear_preferences_action.text() == "&Clear Preferences"
    assert window.metronome_action.isChecked() is False
    assert window.position_announcer_action.isChecked() is False


def test_close_score_is_a_noop_with_nothing_loaded(window):
    window.close_score()  # must not raise

    assert window._music_data is None
    assert window.windowTitle() == "Recall Score"


def test_a_score_can_be_opened_again_after_being_closed(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)
    window.close_score()

    load_and_wait(window, qtbot, minimal_score)

    assert window._music_data is not None
    assert window.windowTitle() == "Recall Score - minimal_4_4.musicxml"
    assert window.region_3.count() > 0
    assert window.close_action.isEnabled() is True


def test_closing_the_window_after_close_score_still_works(window, qtbot, minimal_score):
    """closeEvent calls _save_current_score_config and stops the sequencer -
    both must tolerate there being no loaded score / no sequencer."""
    load_and_wait(window, qtbot, minimal_score)
    window.close_score()

    window.close()  # must not raise


# --- File > Recent Files -----------------------------------------------

def test_recent_files_menu_shows_a_placeholder_when_empty(window):
    actions = [a.text() for a in window.recent_files_menu.actions()]
    assert actions == ["No recent files"]
    assert window.recent_files_menu.actions()[0].isEnabled() is False


def test_opening_a_file_adds_it_to_recent_files_menu(window, qtbot, minimal_score):
    load_and_wait(window, qtbot, minimal_score)

    actions = window.recent_files_menu.actions()
    assert len(actions) == 1
    assert actions[0].text() == minimal_score


def test_triggering_a_recent_file_action_reopens_it(window, qtbot, minimal_score):
    import os

    load_and_wait(window, qtbot, minimal_score)
    window.setWindowTitle("something else")  # prove the reload actually ran

    action = window.recent_files_menu.actions()[0]
    action.trigger()
    qtbot.waitUntil(lambda: window._load_thread is None, timeout=5000)

    assert window.windowTitle() == f"Recall Score - {os.path.basename(minimal_score)}"


def test_a_ug_import_from_a_url_is_not_added_to_recent_files(window, qtbot, monkeypatch):
    """A live URL import's file_path is a synthetic slug with nothing on
    disk - os.path.exists must exclude it, or clicking it later would just
    fail to open a path that was never real."""
    content = "[Verse 1]\n\n[tab][ch]C[/ch]     [ch]G[/ch]\nHello world[/tab]\n"
    _load_ug_import(window, qtbot, monkeypatch, content)

    actions = [a.text() for a in window.recent_files_menu.actions()]
    assert actions == ["No recent files"]


def test_saving_a_ug_import_adds_the_real_path_to_recent_files(
    window, qtbot, monkeypatch, tmp_path
):
    content = "[Verse 1]\n\n[tab][ch]C[/ch]     [ch]G[/ch]\nHello world[/tab]\n"
    _load_ug_import(window, qtbot, monkeypatch, content)

    save_path = str(tmp_path / "Test Song.ug")
    monkeypatch.setattr(
        "main_window.QFileDialog.getSaveFileName", lambda *a, **k: (save_path, "")
    )
    window.save_ultimate_guitar_import_as()

    actions = [a.text() for a in window.recent_files_menu.actions()]
    assert actions == [save_path]
