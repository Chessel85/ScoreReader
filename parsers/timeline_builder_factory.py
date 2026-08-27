# parsers/timeline_builder_factory.py
"""S2: picks the right timeline builder for a score's file format and runs it.

This dispatch used to sit inside MusicData.__post_init__, which meant
models/music_data.py imported all four builders at module scope - a
models -> parsers dependency, and an expensive one: TimelineBuilder and
UgTimelineBuilder both import music21, so merely importing the data model
pulled in ~460ms and ~700 modules of parsing machinery whether or not
anything was ever parsed.

MusicData still supports the documented `MusicData(file_path=...)` shortcut
(the ~1ms ElementTree path timeline tests rely on - see CLAUDE.md); it now
reaches this module through a FUNCTION-LOCAL import, so the dependency is
deferred to the moment a file is actually parsed rather than paid at import
time. That local import is deliberate, not an oversight.

Each builder takes its already-parsed source object when the matching
reader has one (xml_root/midi_source/gp_source/ug_source), so a file is
never walked twice - the shared-source rule described in CLAUDE.md. UG is
the exception with no fallback: a UG import's file_path is a synthetic slug
with nothing fetchable at it, so ug_source must always be supplied.
"""
from models.timeline_build import TimelineBuild
from parsers.gp_timeline_builder import GpTimelineBuilder
from parsers.midi_timeline_builder import MidiTimelineBuilder
from parsers.timeline_builder import TimelineBuilder
from parsers.ug_timeline_builder import UgTimelineBuilder


def builder_for(music_data):
    """The timeline builder matching this score's format, unrun.

    Dispatches on MusicData's own is_midi/is_gp/is_ug extension properties
    so the format test lives in exactly one place - MusicXML is the default,
    not a fourth explicit check, because it is the only format identified by
    more than one extension (.xml/.musicxml/.mxl)."""
    if music_data.is_midi:
        return MidiTimelineBuilder(
            music_data.file_path, music_data.parts_info, source=music_data.midi_source
        )
    if music_data.is_gp:
        return GpTimelineBuilder(
            music_data.file_path, music_data.parts_info, source=music_data.gp_source
        )
    if music_data.is_ug:
        return UgTimelineBuilder(
            music_data.file_path, music_data.parts_info, source=music_data.ug_source
        )
    return TimelineBuilder(
        music_data.file_path, music_data.parts_info, root=music_data.xml_root
    )


def build_timeline(music_data) -> TimelineBuild:
    """Run the matching builder and return everything it produced."""
    return TimelineBuild.from_builder(builder_for(music_data))
