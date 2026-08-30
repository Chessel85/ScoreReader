# tests/widgets/test_strumming_dialog.py
"""Pure widget-state tests for StrummingDialog - it never touches
MusicData/PlaybackController/SynthEngine itself, only emits signals, so it
can be driven directly with no MainWindow/score involved."""
from models.strum_pattern import StrumPattern
from widgets.strumming_dialog import StrummingDialog


def _pattern(name="", codes=None):
    return StrumPattern(
        name=name, bpm=115, denominator=16, is_triplet=False, codes=codes or [1, 202, 101, 1]
    )


def test_tempo_spin_opens_on_the_supplied_current_tempo(qtbot):
    dialog = StrummingDialog(
        patterns=[_pattern()], current_tempo_bpm=143.0, default_tempo_bpm=100.0
    )
    qtbot.addWidget(dialog)
    assert dialog.tempo_spin.value() == 143


def test_tempo_spin_emits_tempo_changed(qtbot):
    dialog = StrummingDialog(patterns=[_pattern()], current_tempo_bpm=120, default_tempo_bpm=120)
    qtbot.addWidget(dialog)
    with qtbot.waitSignal(dialog.tempo_changed) as blocker:
        dialog.tempo_spin.setValue(135)
    assert blocker.args == [135]


def test_s_f_d_keys_nudge_and_reset_the_tempo(qtbot):
    dialog = StrummingDialog(patterns=[_pattern()], current_tempo_bpm=120, default_tempo_bpm=90)
    qtbot.addWidget(dialog)

    dialog._nudge_tempo(10)   # F
    assert dialog.tempo_spin.value() == 130
    dialog._nudge_tempo(-10)  # S
    assert dialog.tempo_spin.value() == 120
    dialog.tempo_spin.setValue(dialog._default_tempo_bpm)  # D
    assert dialog.tempo_spin.value() == 90


def test_tempo_spin_is_clamped_to_the_allowed_range(qtbot):
    dialog = StrummingDialog(patterns=[_pattern()], current_tempo_bpm=9999, default_tempo_bpm=120)
    qtbot.addWidget(dialog)
    assert dialog.tempo_spin.value() == 300  # MusicData.MAX_TEMPO_BPM


def test_include_click_reflects_the_checkbox(qtbot):
    dialog = StrummingDialog(patterns=[_pattern()], current_tempo_bpm=120, default_tempo_bpm=120)
    qtbot.addWidget(dialog)
    assert dialog.include_click() is False
    dialog.click_checkbox.setChecked(True)
    assert dialog.include_click() is True
