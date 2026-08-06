# models/key_signatures.py
# Shared by parsers/musicXML_reader.py (Region 1's opening-of-score key) and
# music_data.py (the status bar's live-position key, C6/D-11) - moved here
# from musicXML_reader.py so music_data.py can read it without a
# parsers->models reverse import.
FIFTHS_MAP = {
    0: "C major / A minor",
    1: "G major / E minor",
    2: "D major / B minor",
    3: "A major / F# minor",
    4: "E major / C# minor",
    5: "B major / G# minor",
    6: "F# major / D# minor",
    7: "C# major / A# minor",
    -1: "F major / D minor",
    -2: "Bb major / G minor",
    -3: "Eb major / C minor",
    -4: "Ab major / F minor",
    -5: "Db major / Bb minor",
    -6: "Gb major / Eb minor",
    -7: "Cb major / Ab minor",
}
