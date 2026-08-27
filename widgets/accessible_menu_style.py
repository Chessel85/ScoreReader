# widgets/accessible_menu_style.py
from PySide6.QtWidgets import QProxyStyle, QStyle


class AccessibleMenuStyle(QProxyStyle):
    """App-wide style tweak so a screen reader announces disabled menu items.

    Qt draws its own menus rather than using the native Windows ones, and its
    built-in menu keyboard navigation skips disabled QActions entirely - the
    highlight never rests on them, so NVDA gets no focus event and stays silent
    (the user arrows past e.g. a disabled File > Close without hearing it).

    A disabled QAction is already exposed to the accessibility tree with a
    "disabled" state, which NVDA reads as "unavailable"/"dimmed" once focus
    lands on it. The only missing piece is letting the menu highlight land on
    it, which is what SH_Menu_AllowActiveAndDisabled controls (off on the
    Windows style, on for some others). Overriding just that one style hint
    keeps every other aspect of disabling unchanged - the item stays greyed,
    still can't be triggered, still flagged disabled for accessibility - and
    the spoken "unavailable" comes from NVDA reporting that state, not from any
    string here.

    Install once in main() with
        app.setStyle(AccessibleMenuStyle(app.style()))
    """

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_Menu_AllowActiveAndDisabled:
            return 1
        return super().styleHint(hint, option, widget, returnData)
