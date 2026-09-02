# tests/models/test_vocabulary.py
"""F4/D-6: UK/US music terminology word-choice helpers."""
from models.vocabulary import (
    articulation_name,
    attribute_label,
    bar_word,
    dynamic_name,
    duration_name,
    looks_like_chord_token,
    spell_out_minor_chord,
)


def test_bar_word():
    assert bar_word(uk_terms=False) == "measure"
    assert bar_word(uk_terms=True) == "bar"


def test_duration_name_passes_through_us_when_not_uk_terms():
    assert duration_name("dotted quarter", uk_terms=False) == "dotted quarter"


def test_duration_name_translates_every_base_name_to_uk():
    cases = {
        "whole": "semibreve",
        "half": "minim",
        "quarter": "crotchet",
        "eighth": "quaver",
        "sixteenth": "semiquaver",
        "thirty-second": "demisemiquaver",
        "sixty-fourth": "hemidemisemiquaver",
        "hundred-twenty-eighth": "semihemidemisemiquaver",
        "two-hundred-fifty-sixth": "demisemihemidemisemiquaver",
    }
    for us, uk in cases.items():
        assert duration_name(us, uk_terms=True) == uk


def test_duration_name_double_whole_is_not_matched_as_a_dotted_whole():
    """"double whole" ends with "whole" too - must match the longer base
    name first or this would wrongly render as "dotted semibreve"."""
    assert duration_name("double whole", uk_terms=True) == "breve"


def test_duration_name_preserves_dotted_prefix():
    assert duration_name("dotted quarter", uk_terms=True) == "dotted crotchet"
    assert duration_name("double-dotted eighth", uk_terms=True) == "double-dotted quaver"


def test_duration_name_unmapped_base_passes_through():
    assert duration_name("maxima", uk_terms=True) == "maxima"
    assert duration_name("longa", uk_terms=True) == "longa"


def test_attribute_label_translates_measure_key():
    assert attribute_label("measure", uk_terms=False) == "measure"
    assert attribute_label("measure", uk_terms=True) == "bar"


def test_attribute_label_stave_is_excluded_by_d15_and_never_translated():
    assert attribute_label("stave", uk_terms=False) == "stave"
    assert attribute_label("stave", uk_terms=True) == "stave"


def test_attribute_label_passes_through_unmapped_keys():
    for key in ("step", "octave", "midi", "beat position", "duration", "part", "voice", "string", "fret"):
        assert attribute_label(key, uk_terms=False) == key
        assert attribute_label(key, uk_terms=True) == key


def test_dynamic_name_translates_common_marks():
    cases = {
        "f": "forte",
        "ff": "fortissimo",
        "p": "piano",
        "pp": "pianissimo",
        "mf": "mezzo-forte",
        "mp": "mezzo-piano",
        "sfz": "sforzando",
        "fp": "fortepiano",
    }
    for mark, spoken in cases.items():
        assert dynamic_name(mark) == spoken


def test_dynamic_name_unmapped_mark_falls_back_to_raw_text():
    """Covers <other-dynamics> custom text, whose value can't be tabulated."""
    assert dynamic_name("poco piano") == "poco piano"


def test_articulation_name_translates_common_tags():
    cases = {
        "staccato": "staccato",
        "strong-accent": "marcato",
        "trill-mark": "trill",
        "mordent": "mordent",
    }
    for tag, spoken in cases.items():
        assert articulation_name(tag) == spoken


def test_articulation_name_unmapped_tag_replaces_hyphens_with_spaces():
    assert articulation_name("some-unmapped-tag") == "some unmapped tag"


def test_spell_out_minor_chord_expands_the_bare_m():
    """Reported: NVDA reads "Cmaj7"/"Dsus4"/"C7"/"G" fine as-is, but a bare
    trailing "m" for a minor chord ("Am", "Am7") is read as the letter "m",
    not the word "minor" - the only abbreviation that needed expanding.
    Shared by every chord-symbol source: MusicXML <harmony>
    (parsers/timeline_builder.py, via music21's ChordSymbol.figure), an
    Ultimate Guitar import's own raw chord text
    (parsers/ug_timeline_builder.py) and a Guitar Pro chord diagram's own
    name (parsers/gp_timeline_builder.py) - so a fix here covers all three
    sources at once rather than needing three separate regexes in sync."""
    assert spell_out_minor_chord("Am") == "A minor"
    assert spell_out_minor_chord("Am7") == "A minor 7"
    assert spell_out_minor_chord("Am9") == "A minor 9"
    assert spell_out_minor_chord("C#m") == "C# minor"
    assert spell_out_minor_chord("B-m7") == "B- minor 7"
    assert spell_out_minor_chord("Am/C") == "A minor/C"


def test_spell_out_minor_chord_leaves_other_labels_untouched():
    # Already fine on a screen reader, or the "m" isn't a bare minor marker.
    for label in ("Cmaj7", "Dsus4", "C7", "G", "Adim", "A+", "Strum"):
        assert spell_out_minor_chord(label) == label


def test_looks_like_chord_token_accepts_real_chords():
    """P2: the conservative recogniser for a bare (un-[ch]-marked) chord
    token above a UG "Tab" page's lyric line."""
    for token in ("D", "F#m", "Bm", "Cmaj7", "G7", "Dsus4", "A/C#", "N.C.",
                  "Em", "Bb", "C#m7", "Gadd9", "F#7", "Asus2"):
        assert looks_like_chord_token(token), token


def test_looks_like_chord_token_rejects_ordinary_words():
    for token in ("the", "And", "nail", "by", "Bridge", "Solo", "I", "Ma'am",
                  "home", "yard."):
        assert not looks_like_chord_token(token), token
