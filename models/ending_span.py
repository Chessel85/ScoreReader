# models/ending_span.py
from dataclasses import dataclass


@dataclass
class EndingSpan:
    """Ref 29: one 1st/2nd-time (or higher) ending bracket
    (<barline>/<ending number type="start"|"stop"|"discontinue">), in
    measure numbers. Populated by TimelineBuilder._repeat_and_ending_spans
    as a side effect of build(), the same pattern as TempoChange/
    tempo_changes. Only a single pass number per <ending> is supported -
    the comma/space-list form (e.g. number="1,2") is valid MusicXML but
    doesn't occur in any file this app has been tested against."""

    number: int
    start_measure: int
    end_measure: int
