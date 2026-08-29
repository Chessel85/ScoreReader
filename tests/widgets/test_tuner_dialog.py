# tests/widgets/test_tuner_dialog.py
"""Pure widget-state tests for TunerDialog - it never touches
TunerController/TunerCapture itself, only emits signals (or, for announce(),
calls Qt's own accessibility API), so it can be driven directly with no
MainWindow involved - same reasoning tests/widgets/test_mixer_dialog.py
already documents for MixerDialog.

No Instrument/String/Offset/A4/Threshold/Device controls live on this
dialog any more (see controllers/tuner_controller.py's module docstring for
the chromatic-tuner redesign that moved them out) - those now belong to
widgets/tuner_settings_dialog.py, covered in
tests/widgets/test_tuner_settings_dialog.py."""
from widgets import accessible_announcer
from widgets.tuner_dialog import TunerDialog


def test_reading_edit_is_read_only_and_starts_with_a_placeholder(qtbot):
    dialog = TunerDialog()
    qtbot.addWidget(dialog)
    assert dialog.reading_edit.isReadOnly()
    assert dialog.reading_edit.text() == "no signal - waiting"


def test_update_pitch_display_sets_text_verbatim(qtbot):
    dialog = TunerDialog()
    qtbot.addWidget(dialog)

    dialog.update_pitch_display("signal 50 percent - A: in tune")

    assert dialog.reading_edit.text() == "signal 50 percent - A: in tune"


def test_settings_button_emits_settings_requested(qtbot):
    dialog = TunerDialog()
    qtbot.addWidget(dialog)
    fired = []
    dialog.settings_requested.connect(lambda: fired.append(True))

    dialog.settings_button.click()

    assert fired == [True]


def test_show_emits_listening_requested_with_no_payload(qtbot):
    dialog = TunerDialog()
    qtbot.addWidget(dialog)
    fired = []
    dialog.listening_requested.connect(lambda: fired.append(True))

    dialog.show()
    qtbot.wait(10)  # showEvent defers the emission by a 0ms singleShot

    assert fired == [True]


def test_closing_emits_listening_stopped_exactly_once(qtbot):
    dialog = TunerDialog()
    qtbot.addWidget(dialog)
    fired = []
    dialog.listening_stopped.connect(lambda: fired.append(True))

    dialog.accept()

    assert fired == [True]


def test_announce_dispatches_through_the_dialog_itself_as_a_real_widget(qtbot, monkeypatch):
    """The regression test for the actual live-tested bug: an earlier cut
    of this feature had the CONTROLLER call QAccessible.updateAccessibility
    targeting itself (a plain QObject, not a widget) - Qt's accessibility
    bridge had nothing to resolve and silently dropped every announcement.
    announce() must target THIS DIALOG (event.object() is dialog), the real
    widget behind the fix."""
    events = []
    monkeypatch.setattr(
        accessible_announcer.QAccessible, "updateAccessibility", events.append
    )
    dialog = TunerDialog()
    qtbot.addWidget(dialog)

    dialog.announce("signal 50 percent. A. in tune")

    assert len(events) == 1
    assert events[0].object() is dialog
    assert events[0].message() == "signal 50 percent. A. in tune"
