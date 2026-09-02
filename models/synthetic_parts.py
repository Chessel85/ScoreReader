# models/synthetic_parts.py
"""S2: the identifiers for parts and voices this app FABRICATES rather than
reading from a file - one definition each, in models/ where both the
parsers that create them and the model code that recognises them can import
from the same source.

These were previously spread across three parser modules with the same
literals repeated: `"chords"`/`"lyrics"` in both parsers/timeline_builder.py
and parsers/ug_timeline_builder.py, and the display names `"Chords"`/
`"Lyrics"` a third time in parsers/ug_reader.py (plus GP's own
CHORD_VOICE_NAME in parsers/gp_reader.py). Every one of those pairs has to
agree verbatim - MusicData.collapsed_part_ids matches part_ids by string,
and get_performance_report_lines joins parts_info.name against
NoteData.part_name by exact text - which is precisely the "two independent
copies of a name must agree" bug class R5 fixed for the reader's own two XML
passes (see CLAUDE.md). One source here means they cannot drift.

Each parser module still re-exports the names it already published, so
existing import sites (including tests that import them from the parser
they were declared in) keep working.
"""

# Chords/Lyrics: real top-level synthetic PARTS. Created by
# parsers/ug_timeline_builder.py for an Ultimate Guitar import (where they
# are the whole score), and by parsers/timeline_builder.py for a MusicXML
# file carrying its own <harmony>/<lyric> markup (where they sit alongside
# the real notated parts, in the same slices). MusicXMLReader/UgReader add
# the matching parts_info entries so Region 2, the mixer and channel
# assignment see them.
CHORDS_PART_ID = "chords"
CHORDS_PART_NAME = "Chords"
LYRICS_PART_ID = "lyrics"
LYRICS_PART_NAME = "Lyrics"

# Tablature: a real top-level synthetic PART, created by
# parsers/ug_timeline_builder.py for an Ultimate Guitar *Tab* import (an
# ASCII-tablature page). Holds one note per struck fret with string/fret
# data; sits alongside Chords/Lyrics when the same page also has [ch]/lyric
# sections.
TAB_PART_ID = "tablature"
TAB_PART_NAME = "Tablature"

# Fabricated VOICE ids, as opposed to the fabricated parts above: each
# attaches to a REAL part/staff and drops into Region 2's existing
# part->staff->voice tree for free, needing no changes to mute/solo,
# active-voice-tuple or ScoreConfig machinery - all of which key off
# (part_id, staff, voice) and don't care what a voice number means. The
# same trick percussion items use (NoteData.voice = the item's own declared
# key, see CLAUDE.md).
#
# Both are 1000: clearly out of range of any real notated voice number
# (MusicXML's are small integers, GP has only slots 1-4), and they can
# never collide with each other because no single score is both a Guitar
# Pro file and a MusicXML one.

# Guitar Pro's synthetic Chords voice - one entry per chord-shaped beat on a
# track that carries chord names or Brush directions anywhere in the piece.
GP_CHORD_VOICE_ID = 1000
GP_CHORD_VOICE_NAME = "Chords"

# Generic "stave text": any free-text <direction><direction-type><words> a
# real part carries (guitar left-hand position roman numerals, tempo/
# technique words an exporter wrote as plain text instead of semantic
# markup - "Allegro", "Staccato", "Pizz.", all confirmed in real fixtures)
# becomes its own event, distinct from the notes around it - deliberately
# NOT sticky/carried forward to later notes (the user's own call: inferring
# how long a marking "lasts" would invent information the score doesn't
# state). Unlike Chords/Lyrics above this is NOT a new top-level part; each
# occurrence attaches to whichever REAL part/staff its <direction> element
# is physically inside. That is what makes a guitar duet's two independent
# fret-position tracks (or a flute+guitar duet's guitar-only fret text) fall
# out for free with zero cross-part guessing: a part's own <direction>
# elements can only ever produce a voice on that same part.
STAVE_TEXT_VOICE_ID = 1000
STAVE_TEXT_VOICE_NAME = "Stave Text"
