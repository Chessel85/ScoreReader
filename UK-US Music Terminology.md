# UK vs US Music Terminology Reference

Scratch reference for Phase F4 / D-6 (UK-US vocabulary toggle). Not authoritative
for the app - cross-check against the Product Definition Document before wiring
any of this into `models/` display strings.

## Note & rest durations

| UK term              | US term            | Symbol / notes            |
|-----------------------|---------------------|----------------------------|
| Breve                 | Double whole note   | Rare, 2x semibreve         |
| Semibreve             | Whole note          |                            |
| Minim                 | Half note           |                            |
| Crotchet               | Quarter note        |                            |
| Quaver                 | Eighth note         |                            |
| Semiquaver             | Sixteenth note      |                            |
| Demisemiquaver         | Thirty-second note  |                            |
| Hemidemisemiquaver     | Sixty-fourth note   |                            |
| Semihemidemisemiquaver | Hundred-twenty-eighth note | Very rare           |
| Dotted note (same both)| Dotted note         | "dotted crotchet" / "dotted quarter note" |

Rests take the same name + "rest": *crotchet rest* / *quarter rest*, *semibreve
rest* / *whole rest*, etc.

## Bars, beats, and time

| UK term            | US term              | Notes |
|---------------------|-----------------------|-------|
| Bar                 | Measure                | Central to D-6; used throughout this app's UI/status bar |
| Bar line            | Bar line / measure line | Both often just "barline" |
| Time signature       | Time signature         | Same |
| Anacrusis / upbeat   | Pickup (note/measure)  | Relevant to Ref 17 pickup-bar handling |
| First-time bar / second-time bar | First ending / second ending | Repeat-bracket wording |
| Tone                | Whole step             | Interval of 2 semitones |
| Semitone            | Half step               | Also used informally in US |
| Simple time / compound time | Simple meter / compound meter | |

## Staves, lines, and notation

| UK term        | US term        | Notes |
|-----------------|------------------|-------|
| Stave (pl. staves) | Staff (pl. staves) | Both languages use "staves" as the plural |
| Leger lines      | Ledger lines     | Spelling variant only |
| Clef            | Clef             | Same |
| Tie             | Tie              | Same |
| Slur            | Slur             | Same |
| Natural/sharp/flat | Natural/sharp/flat | Same symbols and names |
| Key signature    | Key signature    | Same |

## Dynamics, tempo, articulation

Almost entirely shared Italian vocabulary (piano, forte, crescendo, allegro,
legato, staccato, etc.) - no UK/US split. Exceptions:

| UK term          | US term            | Notes |
|-------------------|----------------------|-------|
| Metronome mark    | Metronome marking    | Minor phrasing only |
| Grace note        | Grace note           | Same |

## Instruments (orchestral/general)

| UK term          | US term         | Notes |
|-------------------|-------------------|-------|
| Cor anglais       | English horn      |       |
| Horn              | French horn       | UK often drops "French" |
| Side drum         | Snare drum        |       |
| Kettledrums       | Timpani           | "Timpani" is common in both; "kettledrums" is the older English term |
| Double bass       | (Double) bass / contrabass | Both understood |

## Guitar / tab-specific (relevant to this app)

| UK term    | US term  | Notes |
|-------------|-----------|-------|
| Plectrum    | Pick      | Common substitution |
| Fret        | Fret      | Same |
| Capo        | Capo      | Same |
| Barre chord | Bar chord / barre chord | Both spellings seen in US |

## Score/part vocabulary

| UK term        | US term        | Notes |
|-----------------|------------------|-------|
| Score           | Score            | Same |
| Full score      | Full score / conductor's score | Same |
| Part            | Part             | Same |
| Conductor       | Conductor        | Same |

## Notes for F4 implementation

- The app's likely candidates for a toggle: **bar/measure**, **crotchet/quarter
  note** family (all duration names), **leger/ledger** spelling, and
  **anacrusis/pickup** (already a concept in `TimelineBuilder`'s pickup-bar
  handling, Ref 17).
- Dynamics/tempo/articulation markings are Italian in both dialects, so no
  toggle needed there - reduces scope.
- Decide (per D-6, still open): does the toggle affect screen-reader
  announcements only, on-screen labels only, or both; and does it reach Region
  4 attribute *keys* (e.g. "measure" is currently a literal dict key in the
  codebase, not just a display string).
