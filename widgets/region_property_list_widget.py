# widgets/region_property_list_widget.py
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from widgets.region_focus_cycle import RegionFocusCycleMixin


class RegionPropertyListWidget(RegionFocusCycleMixin, QListWidget):
    """
    Shared "label: value" property list behind Region 1 (score info) and
    Region 4 (note attributes) - the list-based replacement for
    RegionTableWidget/Region4TableWidget. A list, not a table, for the same
    "NVDA reads a whole row in one keystroke" reasoning as Region 2/5: the
    old table forced a second keystroke to hear the value half of
    "Title: Bourree".

    Unlike Region5ListWidget, refresh_list preserves the current row index
    (clamped) across a rebuild rather than resetting to row 0. Region 4 in
    particular rebuilds on every Region 3 selection change, and its rows are
    always emitted in the same MusicData.attribute_order sequence, so losing
    cursor position on every arrow move through Region 3 would be a
    regression from the old table's setCurrentCell-clamp behaviour.
    """

    def refresh_list(self, data: dict) -> None:
        current_row = self.currentRow()

        self.clear()
        for key, value in data.items():
            self.addItem(QListWidgetItem(f"{key}: {value}"))

        if self.count() > 0:
            self.setCurrentRow(min(max(current_row, 0), self.count() - 1))
