# tests/models/test_vocabulary.py
"""F4/D-6: UK/US music terminology word-choice helpers."""
from models.vocabulary import attribute_label, bar_word, clef_name, duration_name, staff_word


def test_bar_word():
    assert bar_word(uk_terms=False) == "measure"
    assert bar_word(uk_terms=True) == "bar"


def test_staff_word():
    assert staff_word(uk_terms=False) == "staff"
    assert staff_word(uk_terms=True) == "stave"


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


def test_clef_name_passes_through_when_uk_terms():
    assert clef_name("Treble stave", uk_terms=True) == "Treble stave"


def test_clef_name_translates_trailing_stave_to_staff():
    assert clef_name("Treble stave", uk_terms=False) == "Treble staff"
    assert clef_name("Bass stave", uk_terms=False) == "Bass staff"
    assert clef_name("Tab stave", uk_terms=False) == "Tab staff"
    assert clef_name("Standard stave", uk_terms=False) == "Standard staff"


def test_attribute_label_translates_measure_and_stave_keys():
    assert attribute_label("measure", uk_terms=False) == "measure"
    assert attribute_label("measure", uk_terms=True) == "bar"
    assert attribute_label("stave", uk_terms=False) == "staff"
    assert attribute_label("stave", uk_terms=True) == "stave"


def test_attribute_label_passes_through_unmapped_keys():
    for key in ("step", "octave", "midi", "beat position", "duration", "part", "voice", "string", "fret"):
        assert attribute_label(key, uk_terms=False) == key
        assert attribute_label(key, uk_terms=True) == key
