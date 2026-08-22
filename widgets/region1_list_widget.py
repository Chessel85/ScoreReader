# widgets/region1_list_widget.py
from widgets.region_property_list_widget import RegionPropertyListWidget


class Region1ListWidget(RegionPropertyListWidget):
    """
    Region 1 (score info) property list. No behaviour beyond the shared
    base - kept as its own file/class purely so Region 1 has the same
    one-file-per-region shape as Region2ListWidget/TimelineListWidget/
    Region5ListWidget.
    """
