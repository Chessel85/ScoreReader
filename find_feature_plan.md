# Comprehensive Find — implementation plan

Status: **P0 + P1 + P2 + P3 + P4 implemented (2026-08-28)**; P5–P6 still plan
only. Written 2026-08-28 after auditing every MusicXML file in `files/` and
`examples/` against the MusicXML 4.0 element reference
(https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/).

P0–P4 delivered as specified below — see the "P0 — DONE" … "P4 — DONE" notes
in §5 for the concrete edit lists and any deviations.

Audience: an implementing agent (Sonnet) working phase by phase. Each phase is
independently shippable, has its own tests, and leaves the app working.

---

## 0. The governing principle

> Anything in the score that is **not** a plain note, a rest, or a lyric should be
> findable.

Two corollaries that shape every decision below:

1. **The Find dialog still only lists what the loaded score actually contains.**
   That is already how `FindIndex.available_targets()` works (a target is offered
   only when `candidate_indices_for_target()` returns at least one real
   occurrence) and it must stay that way. Growing the catalogue must not grow the
   dialog for a score that has none of the new artefacts.
2. **"Not limited to" must be structural, not a list we keep extending.** Two
   catch-all targets (D6) guarantee that an artefact nobody enumerated — a rare
   `<direction-type>` child, a `<notations>` child from a future exporter — still
   shows up as a findable, spoken row rather than vanishing silently. This is the
   single most important idea in this plan.

---

## 1. Where Find is today

| File | Role |
| --- | --- |
| `models/find_target.py` | `FindTarget(category, key, label)` + `MARKING_KINDS`, the closed list of structural marking types. |
| `models/find_index.py` | `FindIndex` — the catalogue (`available_targets`) and the scanner (`candidate_indices_for_target`, `sorted_candidate_indices`, `find_occurrence`). Attribute-target occurrence lists are cached per key; the cache is dropped by `invalidate_cache()` from `MusicData._invalidate_visibility_cache`. |
| `widgets/find_dialog.py` | Modal list, one row per target, `"Attribute: …"` / `"Marking: …"` prefix. |
| `controllers/navigation_controller.py` | `current_find_target`, `find_next` / `find_previous` (Alt+Right / Alt+Left). |
| `models/music_data.py` | `DISPLAY_ATTRIBUTE_ORDER`, `CORE_ATTRIBUTE_KEYS`, delegators `available_find_targets` / `find_occurrence`. |
| `models/note_renderer.py` | `note_attribute_pairs()` — the definition of what an attribute *is*; `attribute_keys_for_voices()` — the presence scan the catalogue uses. |

**The two mechanisms available, and the rule for choosing between them:**

- **Attribute target** — a per-note fact. Add a field to `NoteData`, populate it
  in the parser, emit it from `NoteRenderer.note_attribute_pairs`, add the key to
  `MusicData.DISPLAY_ATTRIBUTE_ORDER`. Find, Region 3 rendering, Region 4 rows,
  the attribute toggle menu, Reorder Attributes and `.rsc` persistence all pick it
  up **for free**. Use this whenever the artefact hangs off a `<note>`.
- **Marking target** — a structural fact that is not attached to a timeline note.
  Add a model in `models/`, populate it in `TimelineBuilder`, publish it through
  `models/timeline_build.py`, add a `MARKING_KINDS` entry plus a branch in
  `FindIndex.candidate_indices_for_target`, and (for anything a performer needs to
  see) a Region 5 row in `MusicData.get_performance_region_rows` and a line in
  `get_performance_report_lines`. Use this for barlines, clefs, and
  `<direction>`-level spans and points.

Prefer the attribute mechanism. It is roughly a tenth of the work and it is the
mechanism the CLAUDE.md architecture notes already tell you to reach for.

---

## 2. What the scores actually contain (evidence)

Scan of all 15 MusicXML files in `files/` + `examples/` (`.mxl` members resolved
through `META-INF/container.xml`). Counts are element occurrences.

| Artefact (element) | Total | Files |
| --- | --- | --- |
| `<tied>` | 786 | allegro-sonatina, chopin-etude, i-see-angels (752), pachelbel |
| `<slur>` | 248 | allegro-sonatina (38), chopin-etude (150), pachelbel (60) |
| `<pedal>` | 142 | chopin-etude |
| `<arpeggiate>` | 115 | Three Blind Mice (11), pachelbel (104) |
| `<tuplet>` / `<time-modification>` | 54 / 80 | Hit It, Quavers and triplets, Three Blind Mice, chopin-etude, i-see-angels |
| `<accidental>` | 438 (56 `cautionary="yes"`) | Way To Go, allegro-sonatina, both bach-bourree, etude 1 tab (10 cautionary), chopin-etude (46 cautionary), i-see-angels, pachelbel |
| `<bar-style>` | 43 | every file (`light-heavy` final bar; `light-light` double bar in Way To Go; `heavy-light` in bach-bourree) |
| `<octave-shift>` | 22 | chopin-etude |
| `<fermata>` | 7 | chopin-etude (2), pachelbel (5) |
| mid-part `<clef>` change | many | chopin-etude (P1, bars 15–20+), i-see-angels (P3, P4) |
| `<grace>` | 2 | allegro-sonatina |
| `<harmony>` | 4 | Three Blind Mice |
| `<ornaments>` children | 8 | Fingers and articulations (trill-mark), pachelbel (mordent, trill-mark ×6) |
| `<articulations>` children | 998 | bach-bourree (accent ×36, twice over — two copies of the file), chopin-etude (accent ×160), i-see-angels (staccato ×562), pachelbel (staccato ×195, accent ×9) |
| `<technical>` children | 876 | string/fret (bach-bourree, etude 1 tab), fingering (Fingers…, etude 1 tab), pluck (Fingers…) |
| `<dynamics>` children | 223 | 8 files, incl. `other-dynamics` ×4 in chopin-etude |
| `<words>` | 28 | allegro-sonatina ("Allegro"), etude 1 tab, chopin-etude, pachelbel ("Pizz.") |
| `<repeat>` / `<ending>` | 8 / 16 | both bach-bourree copies only |
| `<frame>`, `<rehearsal>`, `<glissando>`, `<slide>`, `<measure-style>`, `<non-arpeggiate>`, `<breath-mark>`, `<caesura>`, `<hammer-on>`, `<pull-off>`, `<bend>`, `<harmonic>` | 0 | none in the sample set, but all are ordinary in the guitar/wind/orchestral scores the app is meant to open |

**Findable today:** `string`, `fret`, `dynamic`, `articulation` (articulations
*and* ornaments merged), `fingering`, `pluck`, `strum`, `text` (stave text) as
attributes; repeat start/end, ending start/end, crescendo/diminuendo start/end,
segno, coda, to coda, fine, da capo, dal segno, key/time/tempo change as markings.

**Confirmed unparsed anywhere in `parsers/` or `models/`** (by grep): `tied`,
`slur`, `fermata`, `pedal`, `octave-shift`, `tuplet` (only `time-modification`,
and only for duration naming), `accidental`, `rehearsal`, `glissando`, `slide`,
`bar-style`, mid-part `clef`, `frame`, `multiple-rest`, `breath-mark`, `caesura`,
and every `<technical>` child beyond fret/string/fingering/pluck.

---

## 3. Gap catalogue

`Key` is the attribute key or marking id to implement. Phase maps to §5.

### 3a. Per-note attributes (new keys)

| # | Artefact | MusicXML | Today | Key / values | Phase |
| --- | --- | --- | --- | --- | --- |
| A1 | Grace note | `<grace slash>` | parsed into `NoteData.grace_notes`, rendered inside `step` ("A grace B"), **no key of its own → unfindable** | `grace` → `"acciaccatura"` / `"appoggiatura"` (comma-joined for a group) | P1 |
| A2 | Tie | `notations/tied type=start\|stop\|continue` | none | `tie` → `"start"` / `"stop"` / `"start, stop"` | P1 |
| A3 | Slur | `notations/slur type=start\|stop\|continue` | none | `slur` → `"start"` / `"stop"` | P1 |
| A4 | Tuplet | `time-modification` + `notations/tuplet` | folded into the duration *name* only | `tuplet` → `duration_units.tuplet_word(actual)` e.g. `"triplet"`, else `"5 in the time of 4"` | P1 |
| A5 | Fermata | `notations/fermata` | none | `fermata` → `"fermata"` (+ shape when not `normal`) | P1 |
| A6 | Arpeggiated chord | `notations/arpeggiate` on a chord note, `notations/non-arpeggiate` | only the *single-note* case, re-read as a Chords-part strum stroke; a chord arpeggio (all 104 in pachelbel) is dropped entirely | `arpeggio` → `"arpeggio up"` / `"arpeggio down"` / `"arpeggio"` / `"non-arpeggio"` | P1 |
| A7 | Accidental — **cautionary/editorial only**, per D14 | `<accidental cautionary="yes" editorial="yes">` | spelling only lives inside `step` | `accidental` → `"cautionary sharp"`, `"editorial flat"`, … | P1 |
| A8 | Playing technique (tier 2) | `notations/technical/*` other than fret/string/fingering/pluck: `hammer-on`, `pull-off`, `bend`, `harmonic`, `open-string`, `up-bow`, `down-bow`, `snap-pizzicato`, `stopped`, `tap`, `thumb-position`, `golpe`, `fingernails`, `heel`, `toe`, `double-tongue`, `triple-tongue`, `brass-bend`, `flip`, `smear`, `half-muted`, `harmon-mute`, `other-technical` | none | `technique` → comma-joined spoken names, the same `findall`-merge shape `articulation` already uses | P1 |
| A9 | Glissando / slide | `notations/glissando`, `notations/slide` | none | `glissando` → `"glissando start"` / `"slide stop"` | P1 |
| A10 | Anything else under `<notations>` | `other-notation`, future children | none | **catch-all** `other notation` → the element's own tag, hyphens → spaces (D6) | P1 |
| A11 | Chord symbol | `<harmony>` (also GP chord diagrams, UG `[ch]` markup) | becomes a synthetic Chords-part note whose `step` is the label — and `step` is a **core** key, so Find never offers it | `chord symbol` → the label ("G7", "F/C") | P2 |
| A12 | Chord diagram | `harmony/frame` (+ `frame-note`, `first-fret`, `barre`) | not parsed at all | `chord diagram` → spoken frets, e.g. `"frets 3 2 0 0 0 1"` | P2 |

Already comprehensive, **no parser work needed**, but say so in the docs:
`<articulations>` and `<ornaments>` are merged with a wildcard
`findall("notations/{parent}/*")` and `vocabulary.articulation_name()` falls back
to `tag.replace("-", " ")`, so `breath-mark`, `caesura`, `soft-accent`, `haydn`,
`other-articulation` and `other-ornament` are *already* captured and already
findable under `articulation`. Per-value Find (D1) is what makes them individually
reachable.

### 3b. Structural markings (new marking kinds)

| # | Artefact | MusicXML | Today | Kind / label | Phase |
| --- | --- | --- | --- | --- | --- |
| M1 | Sustain pedal — Find + report only, **no Region 5 rows** (D15) | `direction-type/pedal type=start\|stop\|change\|sostenuto` | none | span: `pedal_start` / `pedal_end` → "Pedal start" / "Pedal end"; point: `pedal_change` → "Pedal change" | P3 |
| M2 | Octave shift — Find + report only, **no Region 5 rows** (D15) | `direction-type/octave-shift type=up\|down\|stop size=8\|15` | none | span: `octave_shift_start` / `octave_shift_end` → "Octave shift start: 8va" | P3 |
| M3 | Rehearsal mark | `direction-type/rehearsal` | none | point: `rehearsal` → "Rehearsal mark A" | P3 |
| M4 | Dashed / bracketed line | `direction-type/dashes`, `direction-type/bracket` | none | span: `dashed_line_start` / `_end`, `bracket_start` / `_end` | P3 |
| M5 | Anything else under `<direction-type>` | `damp`, `damp-all`, `harp-pedals`, `string-mute`, `scordatura`, `principal-voice`, `accordion-registration`, `percussion`, `staff-divide`, `eyeglasses`, `symbol`, `image`, `other-direction` | none | **catch-all** point: `other_direction` → "Direction: harp pedals" (D6) | P3 |
| M6 | Double / dashed / dotted barline — **not the final barline** (D16) | `barline/bar-style` (repeat barlines already covered by `repeat_spans`) | none | point: `double_barline`, `other_barline` | P4 |
| M7 | Clef change | an `attributes/clef` after a staff's first one | none | point: `clef_change` → "Clef change: bass, staff 2" | P4 |
| M8 | Multi-measure rest / measure repeat | `measure-style/multiple-rest`, `/measure-repeat`, `/beat-repeat`, `/slash` | none | point: `multi_measure_rest`, `measure_repeat` | P4 |

Deliberately **not** Find targets (they belong to Region 1 / the Performance
Report, not to positional navigation): `<transpose>`, `<capo>`, `<staff-tuning>` /
scordatura, `<part-symbol>`, `<instrument-change>`, `<print>` page/system breaks,
`<credit>`, `<identification>`.

---

## 4. Design decisions

**D1 — Find by value, not just by presence.** Today "Find articulation" in
pachelbel matches 195 staccatos, 9 accents, 6 trills and a mordent
indiscriminately; the user wants "find the next trill". Add an optional `value` to
`FindTarget`:

```python
@dataclass(frozen=True)
class FindTarget:
    category: str
    key: str
    label: str
    value: Optional[str] = None   # None = "any occurrence of this key"
```

`FindIndex.candidate_indices_for_target` matches on presence when `value is None`,
otherwise on membership: several keys hold a comma-joined list (`articulation`,
`fingering`, `pluck`, `technique`, `grace`), so compare against
`[v.strip() for v in pairs[key].split(",")]`, never `==` on the whole string. The
per-key cache becomes keyed on `(key, value)`.

**D2 — Which keys get expanded into per-value targets: an explicit allow-list, not
a count threshold.** (User decision, 2026-08-28.) A numeric threshold was
considered and rejected: measured against the real files it would have expanded
`fingering` (4 distinct) and `string` (6) while refusing `fret` (11), which is
incoherent — the question is whether the *value carries musical identity a
performer would navigate by*, not how many there happen to be. So:

```python
# models/find_target.py
VALUE_EXPANDED_KEYS = frozenset({
    "articulation", "technique", "dynamic", "accidental",
    "tie", "slur", "glissando", "tuplet",
    "chord symbol", "other notation",
})
```

Everything else — `fret`, `string`, `fingering`, `pluck`, `text` (stave text),
`strum`, `fermata`, `grace`, `arpeggio` — is offered as a single "any" target.
Rationale per group:

- **Expanded:** `articulation` is the case that motivated this (Pachelbel holds 195
  staccatos, 9 accents, 6 trills and 1 mordent under one target). `dynamic` reaches
  8 distinct values in the same file and "find the next *fff*" is a real request.
  `technique` has the same character as `articulation`. `tie`/`slur`/`glissando`
  only ever have two values (start/stop), and "next tie start" is a genuinely
  different question from "next tie stop". `tuplet` has 1–2 values per score
  (triplet; i-see-angels also has 7-in-8). `chord symbol` is 3 values in Three Blind
  Mice and 15–20 in a real song, and the chord name is exactly what a player
  navigates by. `other notation` **must** expand — its value *is* the element name,
  which is the entire mechanism by which an un-enumerated artefact becomes findable
  (D6).
- **Not expanded:** `pluck` and `fingering` are the user's own explicit "potential
  for overwhelming the user" case; `string` (6 rows on every tab score) and `fret`
  (9–11) are the same class; `text` would contribute 11 rows from
  `files/etude 1 tablature.mxl` alone. `fermata`, `grace`, `arpeggio` and `strum`
  have one or two near-constant values, so "any" already says everything.

Always keep the "any" target, listed first, labelled `"Articulation (any)"`. Note
`string` and stave `text` as the two the user may want to revisit after live use —
"jump between guitar position marks" is the plausible future request — but do not
build a preference for it now.

**D3 — Labels are shared with Region 5 and Region 4, never re-invented.** A
marking label copies `get_performance_region_rows`'s own wording verbatim (already
the documented rule in `find_target.py`); an attribute label comes from
`vocabulary.attribute_label(key, uk_terms)`. Add every new key to `vocabulary`'s
attribute-label table in the same commit that adds the key, or the dialog will read
a raw identifier to NVDA.

**D4 — New attributes are per-note, so cross-format cost is zero.** New `NoteData`
fields default to `None`; the MIDI, GP and UG builders never set them and are
unaffected. New marking lists default to empty in `TimelineBuild`, so those formats
show none of the new marking targets — which is correct, since none of those
formats encode them.

**D5 — Direction spans are collected per part, not from the first part only.**
`TimelineBuilder._scan_first_part` reads `root.find("part")` alone, which is right
for score-wide structure (time signatures, tempo, repeats, hairpins). Pedal,
octave-shift, rehearsal marks and clef changes are **per-part / per-staff** facts —
`i-see-angels` changes clef on P3 and P4, not P1. Collect these inside the existing
per-part walk (`_handle_direction` for directions, a new `_handle_attributes` hook
for clefs) and store `part_id` / `staff` on the mark. Where more than one part
contributes marks of the same kind, prefix the Region 5 label with the part name;
where only one does, omit it (no noise in the common single-piano case). One small
helper, applied once at row-building time.

**D6 — Two catch-alls guarantee completeness.** This is what makes the feature
comprehensive rather than "a longer list".

- *Notations catch-all:* in `_read_notations`, after every recognised child has
  been consumed, any remaining `<notations>` child tag becomes the `other notation`
  attribute, value `tag.replace("-", " ")`. Keep the recognised-tag set as a
  module-level frozenset beside it, so adding a real handler later automatically
  removes that tag from the catch-all.
- *Direction catch-all:* in `_handle_direction`, any `<direction-type>` child that
  is not `words`/`dynamics`/`wedge`/`metronome`/`segno`/`coda`/`pedal`/
  `octave-shift`/`rehearsal`/`dashes`/`bracket` produces an `other_direction`
  point mark, labelled `"Direction: <tag with hyphens as spaces>"`.

Both are presence-filtered like everything else, so a score with none of them shows
nothing extra. Both must be covered by a test that feeds an invented element name
and asserts it becomes findable.

**D7 — The arpeggio attribute goes only on chord notes.** A lone note's
`<arpeggiate>` is already deliberately re-read as a pick/strum direction producing a
Chords-part stroke, on the user's explicit reasoning that "strumming does not take
place on a piano". Do not change that. Set the new `arpeggio` attribute only when
the note is part of a chord (2+ notes sharing the offset, i.e. the `<chord>`
grouping) — where "roll this chord" is the real, unambiguous notation meaning.
Guard it with a test using `tests/fixtures/chord_and_stroke_same_note.musicxml` so
the existing single-note behaviour stays pinned.

**D8 — Lyrics stay out**, per the user's own scoping ("not a note or a rest or
lyric"). The Lyrics part remains navigable but is not a Find target.

**D9 — `DISPLAY_ATTRIBUTE_ORDER` growth breaks a pinned test.**
`tests/models/test_music_data.py:1421` asserts
`move_attribute_order("strum", up=False) is False` ("strum is already last").
Append the new keys after `strum` and update that test deliberately, in the same
commit, to pin whatever the new last key is. Do not work around it by inserting
keys in the middle — reading order should be: existing core keys, then existing
optional keys, then the new ones grouped (`tie, slur, tuplet, grace, arpeggio,
fermata, accidental, glissando, technique, other notation, chord symbol,
chord diagram`).

**D10 — Watch the Find hot path.** `note_attribute_pairs` runs per visible note per
slice inside `candidate_indices_for_target`; M1's cache exists precisely for that.
Adding ~12 keys makes each call modestly more expensive, and D1's per-value targets
multiply the number of cached lists. Keep the cache keyed on `(key, value)`, keep
`invalidate_cache()` wired to `MusicData._invalidate_visibility_cache`, and add a
test that a second `sorted_candidate_indices` call for the same target does not
re-scan (monkeypatch `_compute_sorted_candidates` and count calls).

**D11 — Dialog length.** With D2's allow-list the catalogue reaches roughly 25–30
rows on the richest score in the set (Pachelbel: dynamics ×8 values,
articulations ×4, ties, slurs, fermatas, arpeggios, stave text, barlines). Add a single-line filter `QLineEdit` above the list in
`FindDialog`, label "Filter:", buddy-linked, narrowing the list as you type.
Initial focus must still be the **first widget in tab order** (the project's
dialog-focus rule) — so either place the filter after the list in tab order, or
focus the filter and make Down Arrow move into the list; pick the latter only if
the user asks for it. Keep the flat one-row-per-target shape — no tree, no group
headers: Region 2's flat list established that one focus stop per row is what reads
well under NVDA.

**D12 — Region 5 and the Performance Report follow, they do not lead.** A new
*marking* gets a Performance Report line, and — where D15 allows — a Region 5 row
(`get_performance_region_rows`), always using the same label text as its Find
target. New *attributes* get neither; they already surface in Regions 3 and 4.
Keep `get_performance_region_rows`'s documented stable ordering: repeats, endings,
hairpins, then (new) dashes/bracket, then the one-shot rows.
`MainWindow._refresh_region_5` diffs the label list, so an unstable order causes
spurious change cues.

**D13 — Show the occurrence count on every dialog row.** (User request,
2026-08-28.) Row text becomes
`"Attribute: Articulation: staccato, 78 occurrences"` (`"1 occurrence"` singular).
Three points to implement carefully:

- *An occurrence is a position, not a note.* The count is
  `len(sorted_candidate_indices(target))` — timeline slices — so a chord whose three
  notes are all staccato counts once. That is exactly what Alt+Right visits, so the
  number is a promise about how many presses it takes to come back round.
- *It is nearly free.* `available_targets()` already runs the full occurrence scan
  for every marking target, and for attribute targets the scan populates the same
  M1 cache the first Alt+Right would populate a moment later. Compute counts by
  calling `sorted_candidate_indices` (the cached path), never by re-scanning.
  Refactor `available_targets()` to build the list once and read both presence and
  count off it — do not scan twice for the same target.
- *Attribute counts respect the Region 2 voice filter; marking counts don't.* That
  asymmetry already exists in the scanner (markings are structural, like Region 5);
  the count merely makes it visible. Leave it as is and document it in the user
  guide — muting a voice legitimately changes how many articulations are reachable.

Every offered target has at least one occurrence by construction, so no row ever
reads "0 occurrences"; add a test pinning that.

**D14 — Only cautionary and editorial accidentals are findable.** (User decision,
2026-08-28.) MuseScore writes an `<accidental>` for every printed accidental —
Chopin's etude has 189, of which 46 are cautionary — so an unfiltered
"Find accidental" would be little more than "find the next accidental-bearing
note", and the accidental is already spoken inside the note name ("F sharp"). Set
the `accidental` attribute **only** when the element carries `cautionary="yes"` or
`editorial="yes"`; leave it `None` otherwise. Values are the full spoken form
(`"cautionary natural"`, `"editorial flat"`) so D2's per-value expansion
distinguishes them. Add a test that a plain `<accidental>sharp</accidental>` leaves
the key absent.

**D15 — Pedal and octave shift are Find + Performance Report only, with no Region 5
rows.** (User decision, 2026-08-28.) Chopin's etude carries 142 pedal marks, about
71 spans — roughly one per bar. `MainWindow._refresh_region_5` rebuilds Region 5
and fires the performance cue whenever the row-label set changes, so pedal rows
would make that cue fire on most bars of pedal-heavy music and reset Region 5's own
focus constantly. Region 5 stays reserved for structural events (repeats, endings,
hairpins, signature and tempo changes). Both are still fully findable via
Alt+Right/Alt+Left and both are listed in the Performance Report by bar range.
Consequence for P3: build the spans and the Find targets, add the report lines, and
**skip** the `get_performance_region_rows` branch for these two kinds. Dashes and
bracket lines (M4) are rare and do get Region 5 rows.

**D16 — No "Final barline" target.** (User decision, 2026-08-28.) Every score ends
with a `light-heavy` barline, so the target would appear on every file with exactly
one occurrence, and the End key already goes there. `_step_barline` should record
double/dashed/dotted barlines and ignore a `light-heavy` at the last measure. A
`light-heavy` that is *not* the last measure (a multi-movement score) is real
information — record it under `other_barline`.

---

## 5. Phases

Each phase: edit, test, run `.venv\Scripts\python.exe -m pytest`, then run the
fingerprint gate in §7.

### P0 — Value-level Find (infrastructure, do first)

> **P0 — DONE (2026-08-28).** Implemented as written. Edits:
> - `models/find_target.py`: `FindTarget.value: Optional[str] = None`;
>   `VALUE_EXPANDED_KEYS` frozenset (the full D2 list, incl. the not-yet-produced
>   `chord symbol`/`other notation` — harmless, a key absent from the score never
>   expands); new `occurrence_label(count)`.
> - `models/find_index.py`: `candidate_indices_for_target` attribute branch does
>   membership matching over the comma-split value list when `target.value` is set;
>   new `_distinct_values_by_key(voice_tuples)` (one pass over
>   `_real_timeline_slices`, restricted to `VALUE_EXPANDED_KEYS`); `available_targets()`
>   is now the count-less projection of new `available_targets_with_counts()`, which
>   emits the "any" target then per-value targets and computes each occurrence list
>   once via the cached path; cache dict re-keyed on `(key, value)`.
> - `models/music_data.py`: `available_find_targets_with_counts()` delegator.
> - `widgets/find_dialog.py`: row text `"Attribute: articulation: staccato, 78 occurrences"`
>   (value after label with a colon, then the count); `counts` constructor arg;
>   "Filter:" `QLineEdit` matching label text only, placed **after** the list in tab
>   order (showEvent still focuses the list — the first-widget rule).
> - `main_window.py`: `_show_find_dialog` passes `targets` + `counts`.
>
> Deviations / decisions made while implementing:
> - **"any"-label suffix.** `" (any)"` is appended to the any-target label **only
>   when that key actually expands** (in `VALUE_EXPANDED_KEYS` *and* has ≥1 distinct
>   value in this score). A non-expanded key keeps its plain label (`"fret"`, not
>   `"fret (any)"`). The capitalisation in this doc's prose ("Articulation") is
>   illustrative — the real label is still `vocabulary.attribute_label(key,…)` (lower
>   case today), so rows read `"Attribute: articulation (any), …"`.
> - **Per-value row order** is most-common-first (`sort(key=lambda r: (-count, value))`),
>   matching the acceptance example's prose order (staccato, accent, trill, mordent).
> - **Single-value expansion is not suppressed.** A `VALUE_EXPANDED_KEYS` key with
>   exactly one distinct value still gets `"… (any)"` + one value row (e.g. etude 1
>   tablature's lone `mezzo-forte`). Mild redundancy, but the allow-list is explicit
>   and "structural, not a threshold" per D2 — no special-case added.
> - **Two passes, not one.** `attribute_keys_for_voices` already scans the score for
>   present keys; `_distinct_values_by_key` adds a second full pass for the values.
>   Not merged — keeps the collaboration simple; both are O(notes).
> - Tests: 5 existing Find tests updated for the new label text / `counts=` kwarg;
>   new `tests/models/test_find_index.py`; new dialog-filter test in
>   `tests/test_main_window_find.py`; new fixture
>   `tests/fixtures/chord_all_staccato.musicxml` + its `chord_all_staccato_score`
>   conftest fixture (pins "an occurrence is a position, not a note"). Full suite:
>   1044 passed.
> - §7 fingerprint gate not run for P0 — it is a pre-P1 baseline step, and P0's
>   intended change (new/relabelled Find targets) is covered by the test edits above.

Doing this first means every attribute added later gets per-value targets for free.

1. `models/find_target.py`: add `value: Optional[str] = None` to `FindTarget`; add
   the `VALUE_EXPANDED_KEYS` frozenset from D2.
2. `models/find_index.py`:
   - `candidate_indices_for_target`: for `category == "attribute"`, when
     `target.value` is set, match membership over the comma-split value list.
   - New private `_distinct_values_by_key(voice_tuples)` scanning
     `_real_timeline_slices` (same scan shape as
     `NoteRenderer.attribute_keys_for_voices`), restricted to
     `VALUE_EXPANDED_KEYS`. Build it once per `available_targets()` call for all
     present keys — one pass over the score, not one per key.
   - `available_targets()`: emit the "any" target, then the per-value targets, per
     D2. Restructure so each target's occurrence list is computed once and both
     presence and count (D13) are read from it.
   - Cache dict keyed `(key, value)`.
3. New `models/find_target.occurrence_label(count)` → `"1 occurrence"` /
   `"N occurrences"`, so the dialog and any future caller share one wording.
4. `widgets/find_dialog.py`: row text becomes
   `"Attribute: Articulation: staccato, 78 occurrences"` — keep the existing
   category prefix, append the value after the label with a colon, then the count
   (D13). Add the filter box (D11); the filter must match against the label text
   only, so typing a digit doesn't accidentally filter on the count.
5. Tests (`tests/test_main_window_find.py`, new `tests/models/test_find_index.py`):
   a value target matches only its own value; a comma-joined multi-value note
   matches each of its values; a key outside `VALUE_EXPANDED_KEYS` offers only
   "any" no matter how many values it has; the count equals the number of Alt+Right
   presses needed to wrap; a chord with three staccato notes counts as one
   occurrence; no row ever reads "0 occurrences"; caching (D10).

Acceptance: on `examples/pachelbels-canon-in-d-string-quartet.mxl` the dialog
offers "Articulation (any)", "Articulation: staccato", "Articulation: accent",
"Articulation: trill" and "Articulation: mordent", each with its own occurrence
count, and Alt+Right on the trill target visits exactly the six trill positions.
`files/etude 1 tablature.mxl` still offers one "Fret" row, one "String" row and one
"Stave text" row — not 11, 6 and 11.

### P1 — Note-attached notations (A1–A10)

> **P1 — DONE (2026-08-28).** Implemented as written. Edits:
> - `models/note_data.py`: 10 new `Optional[str] = None` fields — `tie`,
>   `slur`, `tuplet`, `fermata`, `arpeggio`, `accidental`, `technique`,
>   `glissando`, `grace`, `other_notation`.
> - `parsers/timeline_builder.py`: `_RECOGNISED_NOTATION_TAGS` frozenset +
>   D6 catch-all in `_read_notations`; new reads for tied/slur (findall),
>   `time-modification` → `tuplet` word, fermata (+shape), tier-2
>   `technical/*`, glissando/slide. Accidental read from the `<accidental>`
>   `<note>` child, set only for `cautionary="yes"`/`editorial="yes"`
>   (D14). Arpeggio (D7) gated on a per-measure chord-member id set
>   (`<chord/>` adjacency scan) threaded into `_read_notations` as
>   `is_chord_member` — a lone note's `<arpeggiate>` still becomes a strum
>   stroke, unchanged. `grace` summary set in `_handle_note` where
>   `grace_notes` is attached.
> - `models/note_renderer.py`: 10 entries appended to
>   `note_attribute_pairs`' optional tail; attribute key for the catch-all
>   is `"other notation"` (space), like `"beat position"`.
> - `models/music_data.py`: `DISPLAY_ATTRIBUTE_ORDER` gains the 10 keys in
>   D9's group order; `"other notation"` is last.
> - `models/vocabulary.py`: `attribute_label` maps `"grace"` → `"grace
>   note"`; every other new key already reads correctly and passes through.
> - `tests/models/test_music_data.py:1421`: the pinned boundary test now
>   pins `"other notation"` as the last attribute.
>
> Deviations / decisions:
> - **`grace` is populated by the parser**, not derived in the renderer —
>   step 1 lists it as a real field and this keeps the renderer tail
>   uniform (`("grace", note.grace)` like every other key). The value is
>   still derived *from* `grace_notes` ("acciaccatura"/"appoggiatura",
>   comma-joined), just at parse time.
> - **`tie` preserves document order** on a note that both ends and begins
>   a tie → `"stop, start"` (not normalised to `"start, stop"`).
> - Fixtures added: `tie_and_slur`, `fermata_and_arpeggio`,
>   `cautionary_accidental`, `technical_tier2`, `unknown_notation`
>   (+ conftest fixtures); `triplet_bar` reused for A4. Tests: 11 parser
>   characterisation tests in `test_timeline_characterisation.py`, 8
>   find/render tests in `test_music_data.py`. Full suite: 1062 passed.
> - §7 gate run (git-worktree baseline at HEAD `7fbfbb8`, both fingerprint
>   harnesses): after normalising out the new `=None` repr fields and the
>   P0-era `chord_all_staccato.musicxml` fixture the baseline lacked, the
>   parser fingerprint is **identical** and the model fingerprint changes
>   are **only** new `find` targets/counts/occurrence lists and new
>   Region 4 rows (`('note N tie', 'tie', 'stop')`, `… tuplet …`) — no
>   change to any navigation walk, beat position, duration, ring-out,
>   playback event/span, Region 3 text, Region 5, bar bounds,
>   `total_measures`, key-override round trip, or the performance report.

1. `models/note_data.py`: add `tie`, `slur`, `tuplet`, `fermata`, `arpeggio`,
   `accidental`, `technique`, `glissando`, `grace` (a spoken summary, distinct from
   the existing `grace_notes` list) and `other_notation` — all
   `Optional[str] = None`, each with a docstring comment in the established style.
2. `parsers/timeline_builder.py`, `_read_notations`: read each per §3a. Use
   `findall`, never `find`, for anything repeatable (the F3 rasgueado bug). Add the
   recognised-tag frozenset and the catch-all (D6). Tuplet reads
   `time-modification/actual-notes` via `models/duration_units.tuplet_word`.
   Accidental reads the `<accidental>` sibling of `<pitch>` (a `<note>` child, not a
   `notations` child) and is set **only** when `cautionary="yes"` or
   `editorial="yes"` (D14). Arpeggio per D7.
3. `models/note_renderer.py`: emit the new keys in `note_attribute_pairs`'s optional
   tail (one tuple entry each). `grace`'s value derives from `note.grace_notes`
   (`"acciaccatura"` when `slash` else `"appoggiatura"`, comma-joined) — do not
   touch the existing `step` "A grace B" rendering.
4. `models/music_data.py`: append the new keys to `DISPLAY_ATTRIBUTE_ORDER` (D9).
   They are all optional, so `CORE_ATTRIBUTE_KEYS` is unchanged and they become
   findable automatically.
5. `models/vocabulary.py`: `attribute_label` entries for each new key (UK/US
   variants where relevant) — "tie", "slur", "tuplet", "fermata", "arpeggio",
   "accidental", "technique", "glissando", "grace note", "other notation".
6. Fixtures: add `tests/fixtures/tie_and_slur.musicxml`,
   `fermata_and_arpeggio.musicxml`, `cautionary_accidental.musicxml`,
   `technical_tier2.musicxml`, `unknown_notation.musicxml` (the catch-all). Keep
   them minimal, in the style of the existing hand-authored fixtures.
7. Tests in `tests/parsers/` (the parser reads the field) and
   `tests/models/test_music_data.py` (the key renders, is findable, and is absent on
   notes that do not carry it).

Acceptance: on
`files/allegro-first-movement-from-sonatina-no-1-in-g-trinity-grade-2-piano.mxl`
the dialog offers Grace note, Tie and Slur, and Find on Grace note visits exactly
the two grace-note positions.

### P2 — Chord symbols and chord diagrams (A11–A12)

> **P2 — DONE (2026-08-28).** Implemented as written. Edits:
> - `models/note_data.py`: two `Optional[str] = None` fields — `chord_symbol`
>   (the label, findable where `step` — a core key — is not) and
>   `chord_diagram` (spoken `harmony/frame` summary).
> - `parsers/timeline_builder.py`: new `_resolve_chord_diagram(harmony_elem)`
>   → `"frets x 3 2 0 1 0"` (string `frame-strings`→1, `"x"` for a muted /
>   absent `frame-note`), `", barre at fret N"` when any `frame-note` has a
>   `<barre>`, `", from fret N"` when `first-fret` > 1. `_handle_harmony`
>   sets `chord_symbol=chord_label or None` + `chord_diagram=...` on the
>   Chords `NoteData`; the arpeggiate-stroke Chords `NoteData` gets
>   `chord_symbol=part_state.current_chord_label or None`.
> - `parsers/ug_timeline_builder.py`: `chord_symbol=spell_out_minor_chord(event.symbol)`
>   on the UG chord entry (mirrors `step_name`).
> - `parsers/gp_timeline_builder.py`: `chord_symbol=current_chord_name` on the
>   GP chord entry — `None` while the name is only the `"Strum"` fallback.
> - `models/note_renderer.py`: two entries appended to the optional tail.
> - `models/music_data.py`: `DISPLAY_ATTRIBUTE_ORDER` gains
>   `"chord symbol", "chord diagram"` after `"other notation"` (D9) —
>   `"chord diagram"` is now the pinned last key.
> - `models/vocabulary.py`: comment only; both keys pass through
>   `attribute_label` unchanged.
> - `chord symbol` is in `VALUE_EXPANDED_KEYS` already (P0) → per-chord
>   targets for free; `chord diagram` is not → single "any" target (D2).
>
> Deviations / decisions:
> - P2 step 4 (add `"chord symbol"` to the Chords voice's default
>   `voice_display_attributes`) was **not** done — `step` already carries the
>   label into Region 3, and adding it would read the chord name twice in one
>   row. Left as the step itself gates on ("only if live testing shows...").
> - Tests: 4 pinned tests updated (`DISPLAY_ATTRIBUTE_ORDER` last-key,
>   `move_attribute_order` boundary, GP/UG chord-entry asserts); new fixture
>   `tests/fixtures/chord_diagram.musicxml` + `chord_diagram_score` conftest
>   fixture; 5 new `test_p2_*` tests in `test_music_data.py`, 1 in
>   `test_gp_timeline_builder.py`. Full suite: 1068 passed.
> - §7 gate run (git-worktree baseline at HEAD `71957db`). Parser
>   fingerprint: after normalising out the two new `=None` repr fields the
>   only difference is the new `chord_diagram.musicxml` fixture — **no
>   existing file's slices/beats/durations/spans/`total_measures` changed**.
>   Model fingerprint: **only** new `chord symbol` Find targets/occurrence
>   walks and a trailing `('note N chord symbol', …)` Region 4 row on
>   Chords-part notes — no navigation walk, playback event, Region 3 text,
>   Region 5, bar bounds or performance-report change.

1. `parsers/timeline_builder.py` `_handle_harmony`: set `chord_symbol` on the
   synthetic Chords `NoteData` (the same label already in `step_name`; a separate
   key is what makes it findable, since `step` is core). Parse `harmony/frame` into
   `chord_diagram` — spoken as `"frets 3 2 0 0 0 1"` reading string 6 → 1, `"x"` for
   a muted string, a `"barre at fret N"` suffix, and `"from fret N"` when
   `first-fret` > 1.
2. `parsers/ug_timeline_builder.py` and `parsers/gp_timeline_builder.py`: set the
   same `chord_symbol` key on their own synthetic chord entries, so "Find chord
   symbol" behaves identically across the three chord sources (the same
   shared-vocabulary rule `spell_out_minor_chord` already established).
3. `DISPLAY_ATTRIBUTE_ORDER` + `vocabulary` labels, as in P1.
4. Only add `"chord symbol"` to the Chords part/voice's default
   `voice_display_attributes` (`MusicXMLReader.load`, `GpReader.load`) if live
   testing shows the label is not already carried by `step` — do not make Region 3
   read the same chord name twice in one row.

Acceptance: `files/Three Blind Mice.mxl` offers "Chord symbol (any)" plus one
target per distinct chord; `files/UG/Half the world away.ug` behaves the same.

### P3 — Direction spans and points (M1–M5)

> **P3 — DONE (2026-08-28).** Implemented per the closed design decisions
> (D5 per-part collection, D6 catch-all, D12 order, D15 no-Region-5 for
> pedal/octave-shift). Edits:
> - `models/direction_span.py` (`DirectionSpan`, quarters-based like
>   `HairpinSpan`, kinds `pedal`/`octave_shift`/`dashes`/`bracket`, carries
>   `part_id`/`staff`/`label`) and `models/direction_mark.py`
>   (`DirectionMark`, point cases `rehearsal`/`pedal_change`/
>   `other_direction`).
> - `parsers/timeline_builder.py`: `_RECOGNISED_DIRECTION_TYPE_TAGS`
>   frozenset; `_PartState.open_direction_spans` slot (most-recent-wins on an
>   unclosed second start, like `_step_barline`); `build()` threads
>   `measure_start_quarters` into `_handle_direction` and calls
>   `_flush_open_direction_spans` after each part's measure loop; new
>   `_step_direction_marks` + `_step_pedal` / `_step_octave_shift` /
>   `_step_direction_line` / `_open`/`_close_direction_span` helpers.
>   octave-shift `size="8"|"15"` + `type="up"|"down"` → label
>   `8va`/`8vb`/`15ma`/`15mb`.
> - `models/timeline_build.py`: `direction_spans` / `direction_marks` fields
>   in the dataclass, `from_builder`, and `apply_to`. MIDI/GP/UG builders
>   each stub the two lists empty (D4).
> - `models/find_target.py`: 11 `MARKING_KINDS` entries (`pedal_start`/
>   `pedal_end`/`pedal_change`, `octave_shift_start`/`_end`, `rehearsal`,
>   `dashed_line_start`/`_end`, `bracket_line_start`/`_end`,
>   `other_direction`).
> - `models/find_index.py`: 11 marking branches — spans via `at_quarters`
>   (mid-measure, like hairpins), points via `first_of(measure)`. Uncached,
>   like every existing marking branch.
> - `models/music_data.py`: `direction_spans` / `direction_marks` fields;
>   `get_performance_region_rows` gains a dashes/bracket/`other_direction`
>   block after the hairpin loop (D12 order) with a `_dir_prefix` helper that
>   part-prefixes a label only when >1 part contributes that kind (D5) —
>   pedal/octave-shift deliberately skipped (D15);
>   `get_performance_report_lines` gains six summary blocks (Pedal marks /
>   Octave shifts / Rehearsal marks / Dashed lines / Bracket lines / Other
>   directions) between "Performance markers" and "Segno marks".
>
> Deviations / decisions while implementing:
> - **Region 5 for the catch-all.** §5.4 says "dashes/bracket and the
>   catch-all only" — `other_direction` DirectionMarks get a one-shot Region
>   5 row (`"Direction: <label>"`); `rehearsal` and `pedal_change` get Find +
>   report only, no row.
> - **`find_occurrence` is strictly-after.** A catch-all test that assumed
>   `find_occurrence(from_index=0)` returns the occurrence *at* index 0 was
>   corrected — it returns the next one and wraps, matching every other
>   marking target.
> - **Marking targets are not value-expanded.** `other_direction` is a
>   single "Direction" target that walks every unrecognised direction point
>   regardless of tag (the specific tag shows in Region 5 / the report),
>   same shape as `segno`. D2's per-value expansion is attribute-only.
> - Fixtures: `pedal`, `octave_shift`, `rehearsal_mark`, `direction_lines`
>   (dashes + bracket), `unknown_direction` (`<other-direction>` + an
>   invented `<harp-pedals>`, in separate bars so each is its own
>   occurrence) + their conftest fixtures. Tests: 7 parser
>   characterisation tests in `test_timeline_characterisation.py`, 8
>   find/Region-5/report/D13/D15 tests in `test_music_data.py`. Full suite:
>   1082 passed.
> - §7 gate run (git-worktree baseline at HEAD `eebf33b`, both harnesses).
>   **Parser fingerprint:** the only diff is the 5 new fixture blocks — no
>   existing file's slices / beat positions / durations / spans /
>   `total_measures` changed (additive only, as §7 expects for new
>   fixtures). **Model fingerprint:** every diff line is either a new
>   fixture block, a new `find marking/<direction kind>` occurrence list, or
>   the six new Performance Report summary keys appended to each file's
>   `report=` line — no navigation walk, Region 3/4/5 text, playback/grace
>   event, bar bound, key-override round trip, or existing report line
>   changed.

1. New models mirroring `HairpinSpan` (quarters-based, since a direction can start
   mid-measure): `models/direction_span.py` — `DirectionSpan(kind, part_id, staff,
   label, start_measure, start_beat_position, start_quarters_from_start,
   end_measure, end_beat_position, end_quarters_from_start)`; and
   `models/direction_mark.py` — `DirectionMark(kind, part_id, staff, label, measure,
   beat_position, quarters_from_start)` for the point cases (rehearsal, pedal
   change, catch-all).
2. `parsers/timeline_builder.py` `_handle_direction`: recognise `pedal`,
   `octave-shift`, `rehearsal`, `dashes`, `bracket`; open/close spans with a
   per-part "currently open" slot keyed by kind (the same most-recent-wins
   convention `_step_barline` uses for an unclosed forward repeat); everything
   unrecognised goes to the catch-all (D6). A span still open at the end of a part
   closes at that part's last measure rather than being dropped.
3. `models/timeline_build.py`: two new fields, plus `from_builder` and `apply_to`
   (its docstring is explicit that every field must land in one place).
4. `models/music_data.py`: `direction_spans` / `direction_marks` fields;
   `get_performance_report_lines` summary lines for every kind; Region 5 rows per
   D5/D12 for dashes/bracket and the catch-all **only** — pedal and octave shift
   deliberately get no Region 5 row (D15). Add a test pinning that, with a comment
   pointing at D15, so a later "for consistency" change can't quietly reintroduce
   the cue storm.
5. `models/find_target.py`: `MARKING_KINDS` entries. `models/find_index.py`:
   branches resolving spans and points via `slice_index_at_or_after_quarters` (the
   hairpin pattern).
6. Fixtures: `pedal.musicxml`, `octave_shift.musicxml`, `rehearsal_mark.musicxml`,
   `unknown_direction.musicxml`.

Acceptance: `examples/etude-opus-25-no-12-ocean-frederic-chopin.mxl` offers Pedal
start/end and Octave shift start/end with their occurrence counts; the Performance
Report lists them by bar range; Region 5 is unchanged from today while stepping
through the piece, and the performance cue does not fire on pedal changes.

### P4 — Barlines, clefs, measure styles (M6–M8)

> **P4 — DONE (2026-08-28).** Implemented per the closed design decisions
> (D5 per-part clef/measure-style collection, D12 order, D16 no final
> barline). Edits:
> - New models: `models/barline_mark.py` (`BarlineMark`, score-wide, kinds
>   `double_barline`/`other_barline`, carries `style`/`measure`/`location`),
>   `models/clef_change_mark.py` (`ClefChangeMark`, per part/staff, quarters
>   + beat_position like its `DirectionMark` cousin),
>   `models/measure_style_mark.py` (`MeasureStyleMark`, kinds
>   `multi_measure_rest`/`measure_repeat`).
> - `models/vocabulary.py`: new `clef_name(sign, line, octave_change)` →
>   `"treble"` / `"bass"` / `"alto"` / `"treble 8vb"` / `"tab"` /
>   `"percussion"`, lowercase, no `" stave"` suffix — deliberately separate
>   from `MusicXMLReader`'s own `"Treble stave"` sign map (that names a
>   whole staff in Region 2).
> - `parsers/timeline_builder.py`: `_FirstPartScan` gains `raw_barlines`
>   (buffered) + `barline_marks`; `_step_barline` reads `<bar-style>` when
>   there is no sibling `<repeat>`; `_scan_first_part` post-loop resolves
>   the buffer, dropping a `light-heavy` on `max(measure_start_quarters)`
>   (D16). `_PartState.clef_by_staff` tracks the `(sign, line,
>   clef-octave-change)` in force per staff; new `_handle_attributes` hook
>   (called from `build()`'s measure walk beside `refresh_bar_shape`) emits
>   a `ClefChangeMark` for a later, different clef and a `MeasureStyleMark`
>   per `<measure-style>` child (`measure-repeat`/`beat-repeat`/`slash`
>   record the `type != "stop"` end only, so the region reads as one point).
> - `models/timeline_build.py`: 3 new fields + `from_builder` + `apply_to`.
>   MIDI/GP/UG builders each stub the 3 lists empty (D4).
> - `models/find_target.py`: 5 `MARKING_KINDS` entries (`clef_change`,
>   `double_barline`, `other_barline`, `multi_measure_rest`,
>   `measure_repeat`) — generic dialog labels like `other_direction`.
> - `models/find_index.py`: 5 marking branches, all via
>   `first_visible_event_index_of_measure` (the `barline/@location` last-vs-
>   first nuance is deliberately deferred — uniform with every other point
>   marking). Uncached, like all markings.
> - `models/music_data.py`: 3 fields; `get_performance_report_lines` gains
>   "Barline changes" / "Clef changes" / "Measure style markers" blocks
>   between "Other directions" and "Segno marks" (D12); `get_performance_
>   region_rows` gains one-shot rows for all three, gated on the mark's own
>   measure (the segno/coda point-mark pattern, not the prev-slice diff).
>   D15 keeps only pedal/octave-shift out of Region 5, so these stay in.
>   Clef-change Region 5 rows are part-prefixed only when >1 part
>   contributes (D5), inline (clef marks aren't in `direction_*`).
>
> Deviations / decisions while implementing:
> - **`<rest measure="yes"/>` still produces a slice**, so a multi-rest
>   bar's `multi_measure_rest` mark resolves to a real index — no special
>   handling needed.
> - **`other_barline` Region 5 label** matches the report wording
>   (`"{style.capitalize()} barline: {bar} N"`, e.g. "Light heavy barline")
>   rather than an ad-hoc `"Barline: light heavy"`.
> - Fixtures: `clef_change` (P1 treble→bass→treble, P2 no change — pins
>   "first clef isn't a change" + no part prefix), `double_barline`
>   (light-light mid-score + light-heavy final — pins D16), `measure_style`
>   (`multiple-rest` + `measure-repeat`) + conftest fixtures. Tests: 5
>   parser characterisation tests in `test_timeline_characterisation.py`
>   (incl. the non-final light-heavy → `other_barline` case, reusing
>   `repeat_ending_then_dc_al_coda`), 7 find/Region-5/report/D13/D16 tests
>   in `test_music_data.py` — the D16 pin is parametrised over every file in
>   `files/` + `examples/`. Full suite: 1108 passed.
> - §7 gate (git-worktree baseline at HEAD `3008f12`, both harnesses).
>   **Parser fingerprint:** purely the 3 new fixture blocks — zero removed
>   lines, no existing file's slices / beats / durations / spans /
>   `total_measures` touched. **Model fingerprint:** every diff line is a
>   new fixture block, a new `find marking/<kind>` occurrence list, the 3
>   new Performance Report keys appended to each file's `report=` line, or a
>   new `('Clef change: …' / 'Double barline: …')` one-shot Region 5 row on
>   `chopin-etude` / `i-see-angels` / `Way To Go` / the dc-al-coda fixture
>   — no navigation walk, Region 3/4 text, playback/grace event, bar bound,
>   or key-override round trip changed.

1. `_step_barline` already parses `<barline>` inside `_scan_first_part` — extend it
   to record `bar-style` as points, skipping the styles already represented by
   repeat spans and skipping a `light-heavy` on the final measure (D16). A
   `light-heavy` anywhere else is recorded under `other_barline`.
2. Clef changes are per-part / per-staff (D5): add a small `_handle_attributes` hook
   to `build()`'s measure walk recording a `ClefChangeMark` whenever an
   `attributes/clef` for a `(part, staff)` differs from the one in force. Label via
   a new `vocabulary.clef_name(sign, line, octave_change)` → "treble", "bass",
   "alto", "treble 8vb", "percussion", "tab".
3. `measure-style` children as simple presence points.
4. Same wiring as P3 steps 3–5.

Acceptance:
`examples/i-see-angels-ascending-descending-on-a-stairway-from-heaven-to-earth-ralph-p-merrifield.mxl`
offers "Clef change" and Find walks the P3/P4 clef changes in bar order;
`files/Way To Go.mxl` offers "Double barline".

### P5 — Cross-format consistency

Guitar Pro already folds `slide`, `muted` and `tied` into the `articulation` string
(`parsers/gp_timeline_builder.py`). Move `tied` → the new `tie` key and `slide` →
the new `glissando` key so the same Find target works on a `.gp` file and a `.mxl`
file. Update `tests/parsers/test_gp_timeline_builder.py`. Keep `muted` where it is
(there is no MusicXML counterpart key).

### P6 — Documentation and settling

1. `docs/user_guide.md` §5.7: describe value-level Find, the occurrence counts (and
   that an occurrence is a position, not a note), the fact that attribute counts
   follow the Region 2 voice filter while marking counts don't, and the artefact
   categories now covered. Regenerate `docs/user_guide.html` with the documented
   pandoc command and commit both together.
2. `CLAUDE.md`: extend the Find paragraph, and **replace the "Ornaments/notations
   survey (2026-08-21)" entry in Known gaps** — most of what it lists as "confirmed
   entirely unparsed" is parsed after P1/P3. Keep its standing decision that
   ornaments are label-only and never audibly realized; that is unchanged here.
3. `tasks.txt` may be updated. `wishlist.txt` is user-maintained — do not edit it.

---

## 6. Tests

Per phase, at minimum:

- **Parser**: one test per new element, using a hand-authored fixture, asserting the
  field lands on the right note/mark and is `None`/absent elsewhere.
- **Catalogue**: `available_find_targets()` on a score *without* the artefact does
  not offer it; on a score *with* it, offers it exactly once, with the exact label.
- **Scanner**: `find_occurrence` from a known index, both directions, including the
  wrap-around (there are existing boundary-cue tests to copy).
- **Catch-alls**: an invented `<other-notation>` / `<other-direction>` child becomes
  a findable target labelled from its tag.
- **Region 5 parity** (markings only): assert the Find label and the Region 5 row
  label are the *same string*, rather than duplicating the literal in both tests.
- **Occurrence counts** (D13): the number shown equals the number of Alt+Right
  presses that returns you to the start; a chord counts once; no row reads zero.
- **Regression pins**: D7's single-note arpeggiate; D9's attribute-order test;
  D14 (a plain accidental leaves the key absent); D15 (pedal produces no Region 5
  row); D16 (no "Final barline" target on any file in `files/` or `examples/`).

Run `.venv\Scripts\python.exe -m pytest` (whole suite, ~0.6 s), and
`-m "not slow"` while iterating.

## 7. Verification gate (mandatory)

`tests/manual/parser_fingerprint.py` and `tests/manual/model_fingerprint.py`
fingerprint every builder output and everything `MusicData` answers across all 56
score files. This work is **not** behaviour-preserving, so unlike a refactor the
expected result is a non-empty diff. Use it as a review instrument:

1. Capture a baseline from the pre-change revision per `tests/manual/README.md`'s
   git-worktree workflow, before starting P1.
2. After each phase, `--check` and **read the diff**. Every changed line must be a
   new field appearing on a note, or a new mark in a list. A changed
   `beat_position`, `quarter_length`, slice count, `total_measures`, or any existing
   `step` / `duration` string is a bug in that phase — the parser must only *add*
   information, never move or re-shape what is already there.
3. Note the diff summary (files touched, lines changed, and why) in the commit
   message.

## 8. Explicitly out of scope

- Making any of this audible. Ornaments, ties, arpeggios, pedal and octave shift
  stay label-only; the standing decision in CLAUDE.md's Known gaps (the auxiliary
  pitch of a trill is not encoded in MusicXML, and inferring it was judged not worth
  the risk) is unchanged, and `<octave-shift>` deliberately does **not** transpose
  playback in this work.
- Lyrics as a Find target (D8).
- Score-level metadata (transpose, capo, scordatura, credits) — Region 1 and the
  Performance Report already own those.
- Free-text search over stave text or chord symbols. Per-value targets (D1) cover
  the realistic cases; a box that searches arbitrary substrings is a separate
  feature and a separate conversation.
- Finding "the next chord" (a slice with more than one note) — derivable from
  Region 3, and not requested.
