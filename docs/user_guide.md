# Recall Score — User Guide

*This guide describes Recall Score, a screen-reader-first music score and
guitar-tab viewer for visually impaired musicians, for Windows.*

## 1. Introduction

### 1.1 What Recall Score Is For

Recall Score lets you explore, study and memorise a piece of music by
ear, using a screen reader and the keyboard, without needing to see the
page. Every move you make through a score is spoken by your screen
reader and heard as MIDI playback, so you always know exactly where you
are and what's sounding.

The app is built around a simple idea: visually impaired musicians
usually can't read notation and play an instrument at the same time, so
memorising a piece well enough to play it from memory matters more than
it does for a sighted player. Recall Score is designed to make that
memorising process as efficient as possible.

### 1.2 Who This Guide Is For

This guide is written for anyone using Recall Score to read, listen to
and study a score - opening files, navigating and filtering what you
hear, and configuring how notes and performance markings are spoken. If
you're setting the app up for your own workflow (choosing UK or US
terminology, which details are spoken, which attributes appear), the
same sections apply to you too.

### 1.3 How to Read This Guide with a Screen Reader

This document is one long page. Use your screen reader's heading
navigation (for example, the `H` key in NVDA) to jump between the
numbered sections and subsections below, or search the page directly for
a keystroke or menu name. §13 is a single reference table of every
keyboard shortcut in the app - worth bookmarking or returning to
directly rather than reading top to bottom.

Keystrokes are always written out in full, for example `Ctrl+Left Arrow`
means: hold Ctrl and press the Left Arrow key.

## 2. Getting Started

### 2.1 Installing Recall Score (Windows)

Recall Score ships as a standard Windows installer,
`RecallScore-Setup-<version>.exe`. Run it and follow the wizard (Welcome,
Components, Install Location, Start Menu shortcut, Install, Finish).
Because it installs into Program Files, Windows will ask for
administrator permission during setup - this is expected.

Once installed, Recall Score appears in your Start Menu and in
Add/Remove Programs like any other Windows application, with a normal
uninstaller. Uninstalling does **not** delete any preferences you've
saved for individual scores (§11) - those live separately under your own
Windows user profile and are covered in §14.3 if you ever want to clear
them by hand.

### 2.2 Opening a Score File

Choose **File > Open...** (or press `Ctrl+O`). A standard file-open
dialog titled "Open Score" appears. Choose your file and select
Open. Once the file has finished loading, the five regions and status
bar (§3) populate automatically - Region 1 with the score's title,
composer, key, time signature and tempo, Region 2 with its parts and
staves, and so on.

### 2.3 Supported File Types

Recall Score opens **MusicXML** files - `.xml`, `.musicxml`, and the
compressed `.mxl` format that many notation programs (including
MuseScore) export by default - and **Standard MIDI Files** - `.mid` and
`.midi`.

MIDI files carry far less information than a real MusicXML score: no
part/instrument names beyond whatever the file itself declares (Region 2
shows one row per track rather than the usual part/stave/voice detail,
since a MIDI track has no real staff or voice concept), and often no - or
wrong - key signature. Use **Edit > Instruments...** and
**Edit > Key Signature...** (§12.2) to correct either.

Recall Score can also import chords and lyrics directly from an Ultimate
Guitar tab page - see §16. If a MusicXML file already carries its own
chord symbols and/or lyrics (for example a lead-sheet-style score exported
from MuseScore), those are picked up automatically as extra **Chords** and
**Lyrics** parts too - see §16.6.

### 2.4 A Five-Minute First Walkthrough

A short first run-through, once you have a MusicXML file to open:

1. **Open a file.** `Ctrl+O`, choose your file. Region 1 now describes
   the piece - title, composer, key, time signature, starting tempo.
2. **Get to the notes.** Press `N` from anywhere to jump straight to the
   Note region (Region 3, §3.4).
3. **Step through it.** Press `Right Arrow` a few times. Each press
   moves to the next note or chord and plays it. `Left Arrow` goes back.
4. **Listen to a chord's individual notes.** If you land on a chord
   (several notes at once), press `Down Arrow` to hear each note in it
   one at a time, `Up Arrow` to go back up.
5. **Try filtering.** Press `Tab` twice to reach Region 2 (Parts,
   Staves and Voices). Press `Down Arrow` to a part or stave, then `O` to
   switch it off. Press `N` to jump back to the Note region and move
   around again - notice that part is now silent and no longer listed.
   Press `O` again on that same row in Region 2 to bring it back.
6. **Check your position at any time.** Press `F6` to move to the status
   bar and hear the current measure, beat, key and time signature; `F6`
   again returns you to whichever region you were last on.

From here, §5 onward covers every navigation and playback control in
detail.

## 3. Understanding the Screen Layout

### 3.1 The Five Regions at a Glance

The main window is arranged in two rows, plus a status bar below them:
the top row holds two regions, the bottom row holds three.

- **Region 1 (top-left): Score Information** - the piece's metadata.
- **Region 2 (top-right): Parts, Staves and Voices** - what's switched
  on or off.
- **Region 3 (bottom-left): Note Timeline** - the notes at your current
  position; this is where you navigate through the music.
- **Region 4 (bottom-middle): Note Attributes** - full detail on
  whatever is currently selected in Region 3.
- **Region 5 (bottom-right): Performance** - repeat barlines, 1st/2nd-
  time endings and dynamics hairpins active at your current position
  (§8).

`Tab` moves focus forward through the five regions in this order,
wrapping back to Region 1 after Region 5; `Shift+Tab` moves backward.
Each region also has its own normal Up/Down row navigation for moving
within it - only Region 3 additionally responds to the timeline keys
described in §5, and only moving through Region 3 triggers audio
playback.

### 3.2 Region 1: Score Information

Shows the score's title, composer or artist, key signature, time
signature and starting tempo, as read from the file when it was opened.
These are the piece's **opening** values and don't change as you move
through the score - for values that track your current position instead
(useful on a piece whose key or time signature changes partway through),
see the status bar in §3.7.

### 3.3 Region 2: Parts, Staves and Voices

A flat, navigable list representing the score's structure: each Part
(for example "Classical Guitar") can contain one or more Staves, each
Stave one or more Voices. Every row reads its name together with its
current state, for example `Classical Guitar - on` or `Treble stave -
on`. Use `O` to toggle the focused row - see §6 for how filtering works.

For a MIDI file, this list shows one row per track only - MIDI has no
real stave or voice concept, so there's nothing further to navigate
underneath a track.

### 3.4 Region 3: Note Timeline

The region you'll spend the most time in. It lists the note or notes
sounding at your current position in the score. `Left`/`Right Arrow`
move through time; `Up`/`Down Arrow` move between individual notes when
several sound together. Every move plays what's now current through
MIDI, using each part's own instrument sound from the file.

### 3.5 Region 4: Note Attributes

Shows full detail for whichever note(s) are currently selected in Region
3 - by default step, octave, measure number, beat position and
duration, plus dynamics, articulation, fingering, string, fret and other
details when the source file provides them and they've been switched on
(§9). This region updates automatically to always match Region 3's
current selection.

### 3.6 Region 5: Performance

Lists whichever repeat barlines, 1st/2nd-time endings and dynamics
hairpins (crescendo/diminuendo) are active at your current position - a
start line and an end line for each, or a single "None" row when nothing
applies there. A short sound plays whenever this list changes as you
navigate, so you know to check it. See §8 for the full detail, including
jumping straight to a marking's start or end and the separate whole-
score Performance Report.

### 3.7 The Status Bar

Six individually focusable fields, in order: measure and beat position,
key signature, time signature, playback tempo, playback status
(Playing/Paused/Stopped) and metronome state (On/Off). Once focus is in
the status bar, `Tab`/`Shift+Tab` cycle only between these six fields and
wrap around, rather than leaving the pane - only `F6`/`Shift+F6` (§4.2)
move focus in or out of the status bar.

Unlike Region 1, the status bar tracks your **current cursor position**
- if a score changes key or time signature partway through, the status
bar reflects whatever is in effect where you are right now. It can also
be read at any time, from any region, using your screen reader's own
"report status bar" command (`NVDA+End` on NVDA).

## 4. Moving Between Regions

### 4.1 Cycling Through the Five Regions (Tab / Shift+Tab)

`Tab` moves focus to the next region in the Region 1 → 2 → 3 → 4 → 5 → 1
cycle; `Shift+Tab` moves in reverse. This is separate from each region's
own internal Up/Down navigation - `Tab` always changes which region has
focus, it never scrolls within one.

### 4.2 Switching Between the Regions Area and the Status Bar (F6)

`F6` toggles focus between the regions area (returning to whichever
region you last had focus in) and the status bar. `Shift+F6` does the
same thing - since there are only two panes, there's no meaningful
"reverse" direction. The menu bar is reached the normal Windows way
(the `Alt` key), not through `F6`.

### 4.3 Jumping to Any Region Directly (I / V / N / A / P)

Each region also has its own direct-jump key that moves focus straight
to it from anywhere in the window - another region, the status bar,
wherever - without changing your timeline position:

| Key | Jumps to |
| :--- | :--- |
| `I` | Region 1, Score Info |
| `V` | Region 2, Parts List |
| `N` | Region 3, Notes |
| `A` | Region 4, Note Attributes |
| `P` | Region 5, Performance |

This saves repeatedly tabbing all the way around just to reach a
particular region.

## 5. Navigating the Timeline

Everything in this section only takes effect while focus is in the Note
region (Region 3). The same keys do nothing in the other regions - each
of those uses its own native navigation instead.

### 5.1 Stepping Note by Note (Left / Right Arrow)

Moves to the next or previous **active event** - a position in the score
where at least one currently-visible note sounds. All notes at the new
position are selected and played together.

### 5.2 Jumping by Measure (Ctrl+Left / Ctrl+Right)

`Ctrl+Right Arrow` jumps to the first active event of the next bar.
`Ctrl+Left Arrow` jumps to the first active event of the current bar, or
to the previous bar's first active event if you're already sitting on
it. If the piece has a pickup bar, it's numbered 0 and comes before bar
1.

### 5.3 Jumping to the Start and End of the Piece (Home / End)

`Home` moves to the very first active note (the pickup bar, if there is
one); `End` moves to the very last. Trailing bars that are nothing but
rests padding out the final printed system don't count - `End` lands on
the last note actually played, not on empty bars after it. `Home` and
`End` never play the boundary sound (§5.6) even if you're already at
that position, since they're jumping to a known place rather than
attempting to move past a limit.

### 5.4 Jumping to a Specific Bar Number

With focus in the Note region, type a bar number using the digit keys -
no dialog needed - then press `Enter` to jump straight to its first
active event, which plays immediately. Press `Escape` at any point
before `Enter` to clear what you've typed without moving. Typing a bar
number that doesn't exist in the piece plays the boundary sound (§5.6)
and leaves your position unchanged.

You can also reach the same feature through **Navigation > Go to
Measure...** (`Ctrl+G`), a dialog pre-filled with your current bar
number if you'd rather use a menu than type directly into the Note
region.

### 5.5 Moving Between Notes in a Chord (Up / Down Arrow)

When several notes sound together at one position, `Left`/`Right Arrow`
selects and plays all of them at once. `Up`/`Down Arrow` narrows the
selection down to one note at a time, so you can hear and inspect each
note in the chord individually. Press `Ctrl+A` at any point to reselect
every note at the current position again.

### 5.6 Boundary Sounds: What the "Doh" Means

A short, quiet, low note plays whenever you try to move past either end
of the piece - with `Left`/`Right Arrow`, `Ctrl+Left`/`Ctrl+Right`, by
typing a bar number that doesn't exist, or by pressing `Space` to start
playback while already sitting on the very last note. It's a deliberate,
unobtrusive "you've reached the edge" cue, not an error message - your
position never changes when you hear it.

## 6. Choosing What You Hear and See

### 6.1 The Part / Stave / Voice Hierarchy

Region 2 (§3.3) mirrors the structure of the file you've opened: each
Part can contain one or more Staves, and each Stave one or more Voices.
A guitar-and-piano duet, for example, typically shows two Parts, with
the piano Part split into two Staves (treble and bass) each with its own
Voices.

### 6.2 Turning a Part, Stave or Voice On or Off

With focus on a row in Region 2, press `O` to toggle it between on and
off. Switching a Part or Stave off hides everything nested underneath it
from both the Note region and playback - but each child keeps its own
individual on/off state in the background, so turning the parent back on
restores exactly what you had before, not a blanket "everything on"
reset.

### 6.3 How Filtering Affects Navigation and Playback

Filtering changes what you hear and see at each position in the
timeline - it never changes which positions exist to move between. Your
current place in the timeline, and Region 3's selection, stay exactly
where they were before and after any toggle in Region 2.

## 7. Listening to the Score

### 7.1 Automatic Playback While You Navigate

Every move within the Note region - stepping with `Left`/`Right Arrow`,
moving within a chord with `Up`/`Down Arrow`, or switching a part on or
off in Region 2 - immediately plays whatever is now current, using each
part's own instrument sound from the file. A chord spanning two parts
(say, piano and guitar) sounds both instruments together, not just one.

### 7.2 Playing the Whole Piece (Play / Pause / Stop)

`Space` starts playback from your current position, and also resumes
playback if it's currently paused. `Ctrl+Space` pauses playback (resume
with `Space`, not `Ctrl+Space` again). Pausing updates the regions to
reflect wherever playback stopped. Stopping playback - or letting it
reach the end of the piece naturally - always returns your position to
wherever playback originally started from, not to the last note heard.

### 7.3 Auditioning a Short Phrase (Enter)

With focus in the Note region and no bar number currently being typed
(§5.4), `Enter` plays a short phrase: from beat 1 of the current measure
through the end of the next measure, then stops on its own. This is
meant for hearing the immediate musical context around your position
without committing to full playback. Pressing `Enter` again while it's
still playing stops it early. Either way, your actual cursor position is
left untouched.

### 7.4 Auditioning the Current Chord (Shift+Space)

Plays every note sounding at your current position together, each held
for its own written duration. Press `Shift+Space` again at any point to
re-trigger it.

### 7.5 Changing Playback Tempo

`F` speeds playback up by 10bpm, `S` slows it down by 10bpm, and `D`
resets to the score's own written tempo. These are global shortcuts -
they work regardless of which region has focus, since tempo is a
playback-wide setting rather than something tied to one region. Changing
it is purely a listening aid: it never edits the tempo actually written
into the score.

For finer control, **Options > Tempo Offset...** (or `Ctrl+T`) opens a
dialog where you can type an exact offset, including decimal values.
Recall Score always keeps the effective tempo within a hard 30-300bpm
range - a value you enter outside that range is automatically brought
back within it rather than rejected.

The status bar's "Playback tempo" field always shows the current
effective tempo in the score's own units (for example, "96 eighth notes
per minute" for a piece marked in eighth notes), and reads "(score
default)" whenever no offset is currently applied.

### 7.6 Using the Metronome

**Options > Toggle Metronome**, or `Ctrl+M`, turns a click on: one per
beat, with a distinctly louder, accented click on beat 1 of every bar.
With the metronome switched on, beat positions that have no note or rest
of their own become reachable, audible stops in the timeline too, so you
can navigate through - and hear the pulse of - even entirely silent
passages.

### 7.7 Using the Position Announcer

**Options > Toggle Position Announcer**, or `Ctrl+P`, turns on a spoken
"talking metronome": at each beat position it speaks a word for where
you are in the bar - "one" through "seven" for whole beats, and "e",
"and" or "a" for the subdivisions in between, the standard way musicians
count subdivided beats aloud. It's independent of the metronome switch
(§7.6) - you can have either, both, or neither running at once, and each
is remembered separately.

### 7.8 Adjusting Volume and Pan (the Mixer)

**Edit > Mixer...**, or `Ctrl+Shift+X`, opens a dialog listing every
instrument in the score, plus the metronome and the position announcer.
Select an entry, then use the **Volume** (0-100%) and **Pan** (-100% left
to +100% right) fields to adjust it - type an exact value, or use
`Home`/`End` to jump straight to that field's highest/lowest value and
`Insert` to reset it to a sensible starting point (centre for Pan, 50%
for Volume). Volume is scaled to roughly match what you'd expect to hear:
100% is the instrument's normal loudness, 50% sounds about half as loud,
and 0% is silent.

Changes take effect immediately as you make them, so you can compare
before committing to them. **Preview Alt+W** plays a short phrase (the
current bar and the next) using your changes so far, without moving your
place in the score - press it again to stop early. **OK** keeps your
changes and saves them with the score (see §11.1); **Cancel** puts
everything back exactly as it was before you opened the dialog.

## 8. Performance Markings: Repeats, Endings and Dynamics

### 8.1 What Appears in the Performance Region

Region 5 (§3.6) shows two lines for every repeat barline, 1st/2nd-time
ending, or dynamics hairpin (crescendo/diminuendo) that covers your
current position - one for where it starts, one for where it ends - for
example:

```
Repeat start: bar 2
Repeat end: bar 9
```

or, for a hairpin that doesn't begin or end exactly on the first beat of
a bar:

```
Crescendo start: bar 12 beat 3
Crescendo end: bar 13
```

A beat position is only shown when a marking's start or end doesn't fall
on beat 1 of its bar - repeats and endings never show one, since
barlines only ever occur at the start of a bar. When your current
position isn't covered by any marking, Region 5 shows a single "None"
row.

Region 5 also shows a one-off row - with no start/end pair - the moment
you land exactly where the time signature or tempo changes, for example:

```
Time signature change: 3/4
Tempo change: 96 quarter notes per minute
```

Unlike the repeat/ending/hairpin rows above, this disappears again as
soon as you move to the next note - it's a "something changed here" flag
for that one position, not a range you're inside. The score's *opening*
time signature and tempo are never flagged this way, since Region 1 and
the status bar already show those the moment a file loads.

### 8.2 The "Something Changed" Cue

A short, distinct sound plays whenever the set of entries showing in
Region 5 changes as you navigate - for example the moment you step into
or out of a repeated section. It doesn't repeat on every move while
you're still inside the same passage, only when what's showing actually
changes, so it's a reliable signal to check Region 5 rather than
background noise.

### 8.3 Jumping to a Marking's Start or End (Ctrl+Home / Ctrl+End)

With focus on an entry in the Performance region, `Ctrl+Home` moves your
timeline position to that marking's start; `Ctrl+End` moves it to the
last sounding note of the marking's end bar. Either jump plays the notes
at the new position immediately, the same as any other timeline move.

### 8.4 The Performance Report (Edit > Performance Report...)

**Edit > Performance Report...** opens a read-only summary of the whole
piece, independent of whatever's currently filtered in Region 2: title,
composer, key, time signature and tempo (the same details Region 1
shows), whether the piece has a pickup bar, its total number of bars, a
note count for each instrument, and a list of every repeat, ending and
dynamics hairpin in the score by bar range. It's a single flat list you
can read top to bottom with Up/Down Arrow. Close it with the Close
button or `Escape`; focus returns to wherever it was before you opened
it.

## 9. Understanding Note Attributes

### 9.1 What's Shown by Default

By default, the Note region (Region 3) speaks only each note's plain
name - for example "C", "F sharp", "B double flat". Accidentals are
always spelled out in full for clear pronunciation, and octave numbers
are left out to keep things brief. A rest is simply announced as "rest".

Region 4 always shows a fuller picture of whatever is currently selected
- step, octave, measure number, beat position and duration - plus
whichever of the extra details in §9.2 the file provides and you've
chosen to show.

### 9.2 Adding More Detail (Dynamics, Articulation, Fingering, String, Fret)

Depending on what the source file contains, additional details may be
available: dynamics markings (forte, piano, and so on), articulation
(staccato, accent, trill, and similar), fingering, string and fret
numbers, and plucking-hand markings for guitar. An attribute only
appears on a note when it's **both** switched on for that voice **and**
actually present on that specific note - if a key is simply missing from
one note's row, that's expected, not a fault.

To switch an attribute on or off, open the context menu on the relevant
row in Region 4: right-click it, or press the `Menu` key (or
`Shift+F10`) while focused on it. The menu offers "Add to notes for this
voice", "Add to notes in same stave", "Add to notes in the same part"
and "Add to notes in the whole score" for an attribute that isn't
showing yet - or the matching "Remove for notes in..." options once it
already is.

### 9.3 Choosing Where an Attribute Applies (Voice / Stave / Part / Score)

The scope you choose from that context menu decides how far the change
reaches: just the one voice you're on, everything sharing its stave,
everything in its part, or the entire score. If you open the menu while
several notes across different voices are selected (a chord), the scope
you pick applies across every voice represented in that selection, not
only the note you happened to open the menu from.

### 9.4 Changing the Order Attributes Are Read

**Options > Reorder Attributes...** opens a dialog scoped to whatever
part, stave or voice is currently selected in Region 2, listing only the
attributes relevant there. Use **Move Up** (`Alt+U`) and **Move Down**
(`Alt+D`) to reorder them live. This order is a single setting that
applies everywhere - both Region 3's note labels and Region 4's rows
follow it - it isn't a separate ordering per voice.

## 10. Terminology: UK and US Music Vocabulary

### 10.1 What Changes When You Switch

Recall Score can speak either UK or US musical terminology: **bar**
versus **measure**, and the **crotchet/quaver/semiquaver** family versus
**quarter note/eighth note/sixteenth note**. This is purely a matter of
wording on screen and in speech - nothing about how the score is stored,
counted or played changes underneath it.

One family is deliberately left out of this toggle: stave/staff naming
(Region 2's clef labels, and Region 4's "stave" attribute) always reads
the same way regardless of which terminology language is selected.

### 10.2 Switching Terminology Language

**Options > Terminology Language** offers UK and US as two mutually
exclusive choices - exactly one is always selected at a time. This is a
single preference that applies across the whole application, not tied to
any individual score, so opening a different file mid-session never
changes which wording you're hearing.

## 11. Your Settings Are Remembered

### 11.1 What's Saved Per Score

For each individual score file, Recall Score remembers, and restores the
next time you open that same file:

- Which parts, staves and voices are switched on or off.
- Whether the metronome is switched on.
- Whether the position announcer is switched on.
- Which note attributes are shown for each voice (§9.2).
- The order those attributes are read in (§9.4).
- Volume and pan set for each instrument, the metronome and the position
  announcer, via the Mixer (§7.8).

Files are matched by their own filename, so moving a file to a different
folder doesn't lose its saved settings. If a saved setting no longer
matches the file - for example a part that's since been renamed or
removed - it's simply left out rather than causing an error or a dialog.

### 11.2 What's Saved Across All Scores

Your UK/US terminology choice (§10) is the one preference that applies to
every score, not just one - it stays as you last set it no matter which
file you open next.

### 11.3 Clearing Saved Preferences for a Score

**Edit > Clear Preferences for `<filename>`** deletes just that one
file's saved settings, so it reverts to defaults the next time it's
opened. This menu item is disabled when no file is currently loaded.

**Edit > Open Local Folder** opens the folder on disk where these saved
settings actually live, in case you ever want to inspect or back them up
directly (see also §14.3).

## 12. Menu Reference

### 12.1 File Menu

| Item | Shortcut | What it does |
| :--- | :--- | :--- |
| Open... | Ctrl+O | Opens a MusicXML or MIDI file, or a previously saved Ultimate Guitar import (§16.4). |
| Recent Files | - | Submenu listing the last 8 files you've opened, most recent first, for quick reopening. |
| Import from Ultimate Guitar... | - | Imports chords and lyrics from an Ultimate Guitar tab page URL (§16). |
| Save Ultimate Guitar Import As... | - | Saves the currently loaded Ultimate Guitar import to a file so it can be reopened later (§16.4). Only meaningful when an Ultimate Guitar import is currently loaded. |
| Exit | - | Closes Recall Score. |

### 12.2 Edit Menu

| Item | Shortcut | What it does |
| :--- | :--- | :--- |
| Open Local Folder | - | Opens the folder where saved per-score preferences are stored. |
| Clear Preferences for `<filename>` | - | Deletes the currently loaded file's saved settings. Disabled when no file is loaded. |
| Performance Report... | - | Opens a read-only summary of the whole piece (§8.4). |
| Mixer... | Ctrl+Shift+X | Opens the volume/pan mixer for every instrument, the metronome and the position announcer (§7.8). |
| Instruments... | Ctrl+Shift+I | Renames a part, or changes what instrument it plays back as, for the currently loaded score. Especially useful for MIDI files, where a track may have no name or an unhelpful one. |
| Key Signature... | Ctrl+Shift+K | Overrides the whole piece's key signature - a single choice from a list of all major and minor keys, or "use the file's own key". Mainly for MIDI files, which often carry no key signature at all. |

### 12.3 Navigation Menu

| Item | Shortcut | What it does |
| :--- | :--- | :--- |
| Move to First Note | Home | Jumps to the first active note. Only enabled while focus is already in the Note region. |
| Move to Last Note | End | Jumps to the last active note. Only enabled while focus is already in the Note region. |
| Go to Measure... | Ctrl+G | Opens a dialog, pre-filled with the current bar, to jump to a specific bar number. |
| Move to Notes | N | Jumps focus to the Note region from anywhere, without moving your timeline position. |
| Move to Info | I | Jumps focus to the Score Info (metadata) region from anywhere. |
| Move to Parts List | V | Jumps focus to the Parts List region from anywhere. |
| Move to Attributes | A | Jumps focus to the Note Attributes region from anywhere. |
| Move to Performance | P | Jumps focus to the Performance region from anywhere. |

### 12.4 Options Menu

| Item | Shortcut | What it does |
| :--- | :--- | :--- |
| Tempo Offset... | Ctrl+T | Sets an exact playback tempo offset, including decimal values (§7.5). |
| Terminology Language | - | Submenu to choose UK or US wording (§10.2). |
| Toggle Metronome | Ctrl+M | Turns the beat click on or off (§7.6). |
| Toggle Position Announcer | Ctrl+P | Turns the spoken beat-position announcer on or off (§7.7). |
| Reorder Attributes... | - | Changes the order note attributes are read in for the current Region 2 scope (§9.4). |
| Reorder Parts... | - | Changes the order parts are listed in Region 2, and in turn the order their notes are listed in Region 3 (§16.3). |

### 12.5 Help Menu

| Item | Shortcut | What it does |
| :--- | :--- | :--- |
| About Recall Score... | - | Shows the application name, version number and a short description. |

## 13. Keyboard Shortcut Reference

| Action | Keystroke |
| :--- | :--- |
| Move focus to the next / previous region | Tab / Shift+Tab |
| Toggle focus between the regions area and the status bar | F6 / Shift+F6 |
| Jump focus to the Note region from anywhere | N |
| Jump focus to the Score Info region from anywhere | I |
| Jump focus to the Parts List region from anywhere | V |
| Jump focus to the Note Attributes region from anywhere | A |
| Jump focus to the Performance region from anywhere | P |
| Step to the next / previous active event *(Note region only)* | Left Arrow / Right Arrow |
| Jump to the first active event of the next / current-or-previous bar *(Note region only)* | Ctrl+Left Arrow / Ctrl+Right Arrow |
| Jump to the first / last active note *(Note region only)* | Home / End |
| Type a bar number, then jump to it *(Note region only)* | 0-9, then Enter |
| Clear a typed bar number without moving *(Note region only)* | Escape |
| Move between notes within a chord *(Note region only)* | Up Arrow / Down Arrow |
| Reselect every note at the current position *(Note region only)* | Ctrl+A |
| Open the Go to Measure dialog | Ctrl+G |
| Toggle the focused Part, Stave or Voice on/off *(Parts List region only)* | O |
| Play / stop playback from the current position (also resumes from pause) | Space |
| Pause playback (resume with Space) | Ctrl+Space |
| Play a two-bar phrase around the current position *(Note region, no bar number pending)* | Enter |
| Play every note at the current position together | Shift+Space |
| Increase / decrease playback tempo by 10bpm | F / S |
| Reset playback tempo to the score's own tempo | D |
| Open the Tempo Offset dialog | Ctrl+T |
| Toggle the metronome on/off | Ctrl+M |
| Toggle the position announcer on/off | Ctrl+P |
| Open the Mixer dialog | Ctrl+Shift+X |
| Play a short preview from the Mixer dialog *(Mixer dialog only)* | Alt+W |
| Open the Instruments dialog | Ctrl+Shift+I |
| Open the Key Signature dialog | Ctrl+Shift+K |
| Move the selected attribute up / down *(Reorder Attributes dialog only)* | Alt+U / Alt+D |
| Move the selected part up / down *(Reorder Parts dialog only)* | Alt+U / Alt+D |
| Jump to the start / end of the focused Performance region entry *(Performance region only)* | Ctrl+Home / Ctrl+End |
| Open the Performance Report | Edit menu > Performance Report... |
| Open a note attribute's context menu *(Note Attributes region only)* | right-click, or Menu key / Shift+F10 |
| Open a score file | Ctrl+O |

## 14. Troubleshooting

### 14.1 No Sound

Recall Score plays sound through a bundled audio engine and instrument
library that need to start up successfully when the application
launches. If your machine has no working audio output, or something
about the installation is incomplete, Recall Score still runs and lets
you navigate and use every region normally - it simply won't produce any
sound, without announcing that fact on screen. As a first check, confirm
your system's normal audio output is working outside Recall Score too.

### 14.2 A File Won't Open

If a file fails to load, nothing changes on screen. Check the log file
at `%LOCALAPPDATA%\Recall Score\recall_score.log` for details of what
went wrong. The most common cause is a file that isn't valid MusicXML,
or isn't one of the supported extensions (§2.3): `.xml`, `.musicxml` or
`.mxl`.

### 14.3 Where Settings Are Stored on Disk

**Edit > Open Local Folder** opens the storage location directly. Both
your per-score settings (§11.1) and your shared UK/US preference (§11.2)
live under your own Windows user profile, entirely separate from where
Recall Score itself is installed - reinstalling or moving the
application doesn't affect them.

## 15. Getting Help and Reporting Problems

If you run into a problem, **Help > About Recall Score...** shows the
exact version you're running - worth including if you report an issue.
Check §14 (Troubleshooting) first; if that doesn't resolve it, please
raise an issue on the project's GitHub page:

<https://github.com/Chessel85/ScoreReader/issues>

Include what you were doing, the version number, and - if the app was
involved - the contents of `recall_score.log` (§14.2).

## 16. Chords and Lyrics

### 16.1 What This Feature Is For

Alongside notated scores (§2.3), Recall Score can import a song's chords
and lyrics directly from a chord-tab page on Ultimate Guitar
(ultimate-guitar.com) - the kind of page that shows chord names
positioned above the lyric words they go with, rather than full sheet
music. This is a different, simpler kind of material than a MusicXML or
MIDI score: there's no notated rhythm or real bar structure, just chord
changes and the words that go with them.

A MusicXML file can carry the same kind of information too - chord
symbols and/or lyric text written directly into the score alongside its
real notated notes. Recall Score picks these up automatically, with no
importing step needed - see §16.6.

### 16.2 Importing a Song

Choose **File > Import from Ultimate Guitar...**. A dialog asks for the
page's web address - paste the full URL of an Ultimate Guitar chords page
(for example `https://tabs.ultimate-guitar.com/tab/<artist>/<song>-chords-<id>`)
and select **OK**. Only "Chords"-type tab pages are supported - a Guitar
Pro tab, plain tab, bass tab or ukulele-chords page on the same site will
be rejected with an explanation. The import runs in the background, the
same way opening a file does, so the rest of the app stays responsive
while it fetches the page.

Once imported, Region 1 shows the song's title, artist, key, tuning,
difficulty and tempo the same way any other score does, plus (when the
page provides one) a **Strumming Pattern** field describing the song's
strum rhythm as a sequence of downstrokes, upstrokes and muted strums.

### 16.3 Chords and Lyrics as Two Parts

An imported song shows up in Region 2 as two parts, **Chords** and
**Lyrics**, each a single flat row with nothing further to expand
underneath - the same simplified display a MIDI track gets (§3.3), since
neither has real staves or voices. Switch either off with `O` exactly as
you would any other part.

Moving through the Note region works the same as any other score: each
step forward is one chord change. The Chords row names the chord (for
example "Fmaj7") and plays it - as a real strummed pattern when the song
has strumming data, arpeggiated up or down per the pattern rather than
every note firing at once, otherwise as a plain chord. The Lyrics row
shows the words sung during that chord, or "No lyrics" for instrumental
passages such as an intro with nothing sung yet.

Most chord names are shown exactly as written ("Fmaj7", "C7", "Dsus4", a
bare "G" for G major) since a screen reader already reads those clearly.
A minor chord is the one exception: rather than show it as a bare "Am" or
"Am7" - which a screen reader reads as the letter "m", not the word
"minor" - Recall Score spells it out as "A minor" or "A minor 7". This
applies everywhere a chord name is shown, including the embedded-MusicXML
chords in §16.6.

Because Region 3's currently-selected row is always the first one shown,
whichever part is listed first in Region 2 is the one your screen reader
announces by default on every move. If you'd rather hear the lyric first
and the chord name second (or vice versa), use **Options > Reorder
Parts...**: a dialog listing Chords and Lyrics with **Move Up** (`Alt+U`)
and **Move Down** (`Alt+D`) buttons, plus OK and Cancel. Moving Lyrics
above Chords and selecting OK swaps which one is read first from then on,
without affecting anything already switched on or off in Region 2. This
dialog works the same way for any multi-part score, not just an Ultimate
Guitar import.

### 16.4 Saving and Reopening an Import

An imported song only exists for the current session until you save it.
**File > Save Ultimate Guitar Import As...** writes it to a file on disk
(a `.ug` file) that you can reopen later with the ordinary **File >
Open...** dialog or from **File > Recent Files** - both treat it exactly
like any other score file from then on, including remembering its own
settings (§11.1).

### 16.5 Things to Be Aware Of

Because a chord-tab page has no real notated bar structure, Recall Score
treats every chord change as one bar - this is a simplification for
navigation purposes, not a claim about the song's actual notated rhythm.
Occasionally a lyric line's timing in the source page is imprecise (the
original contributor's own spacing), which can very occasionally show a
lyric fragment split slightly oddly - this reflects the source page, not
a fault in the import.

### 16.6 Chords and Lyrics Embedded in an Ordinary MusicXML Score

Some MusicXML files carry chord symbols and/or lyric text written directly
into the score alongside its real notated notes - typically a
lead-sheet-style piece exported from a program like MuseScore, with chord
names printed above the staff and words printed underneath it. Opening
such a file with **File > Open...** shows this content automatically, with
no separate import step: Region 2 gains a **Chords** part, a **Lyrics**
part, or both, alongside the score's own instrument parts - each shown as
a single flat row with nothing further to expand underneath (§16.3), the
same as an Ultimate Guitar import's Chords/Lyrics parts, since neither has
any real staves or voices of its own. The score's own real instrument
keeps its normal part/stave/voice detail untouched.

Unlike an Ultimate Guitar import (§16.3), these two parts line up with the
score's own real notated timing rather than one fabricated bar per chord
change - a chord symbol or lyric shows up at exactly the beat it was
written against, right alongside the notated note sounding at that same
moment. Switch either part off with `O` exactly as you would any other
part, and use **Options > Reorder Parts...** (§16.3) if you'd rather your
screen reader announce the lyric before the chord name, or the other way
round. A bar with a chord symbol but no note underneath it, or a note with
no lyric under it, simply has no Chords or Lyrics entry there - there's no
"No lyrics" placeholder the way an Ultimate Guitar import uses for a
wordless bar, since with real notated timing there's no ambiguity about
whether something is missing.

If the score also marks individual notes with an up- or down-stroke
indicator (some notation programs let you add this to guide a strummed
accompaniment), the Chords row shows it too - for example "A minor, beat
position 2.0, strum down stroke" - since a stroke direction is something
the chord accompaniment does, not something the notated melody note does.
A bar can show more than one Chords row when it has more than one marked
stroke in it, one per stroke, each still following the score's own real
timing.
