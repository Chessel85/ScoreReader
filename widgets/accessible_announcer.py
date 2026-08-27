# widgets/accessible_announcer.py
from PySide6.QtGui import QAccessible, QAccessibleAnnouncementEvent
from PySide6.QtWidgets import QWidget


def announce(widget: QWidget, message: str) -> None:
    """Post a one-shot screen-reader announcement - the app's single most
    load-bearing accessibility mechanism, in one place.

    Surfaces to NVDA as a UI Automation notification on Windows
    (QAccessibleAnnouncementEvent, Qt 6.8+; confirmed present in this
    project's PySide6 6.11). It's a side channel: it never touches what a
    widget displays or stores, so it can't be re-read when the user
    navigates back over the same row.

    The event target MUST be a real QWidget, never a plain QObject: Qt's
    accessibility bridge resolves the announcement against the target's
    accessibility interface, and a bare QObject has none - the platform
    bridge then silently drops every event (live-tested bug, see
    controllers/tuner_controller.py's module docstring). That's why a
    QObject controller can't call this directly - it routes the message to
    a real widget it owns (RegionPresenter -> region_3; TunerController ->
    the dialog itself). The assert keeps that invariant structural rather
    than something four call sites have to remember.
    """
    assert isinstance(widget, QWidget), "announcement target must be a real QWidget"
    event = QAccessibleAnnouncementEvent(widget, message)
    event.setPoliteness(QAccessible.AnnouncementPoliteness.Assertive)
    QAccessible.updateAccessibility(event)
