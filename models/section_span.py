# models/section_span.py
from dataclasses import dataclass


@dataclass
class SectionSpan:
    """A named song section ([Intro], [Verse 1], [Chorus], [Bridge], ...),
    as a span of measures. A section is a span, not a point - the user is
    inside one for many bars, and a span is what makes Region 5's
    Ctrl+Home/Ctrl+End and the change cue meaningful.

    Populated by UgTimelineBuilder from the [Section] labels it walks;
    the label is passed through verbatim (no normalising, no title-casing,
    homoglyphs included). end_measure is the bar before the next section
    starts, or the last bar of the score for the final section.

    Written against this generic shape so populating section_spans from
    Guitar Pro section text or MusicXML rehearsal marks later needs no
    navigation or Region 5 changes.
    """

    label: str
    start_measure: int
    end_measure: int
