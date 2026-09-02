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
a keystroke or menu name. Section 15 is a single reference table of
every keyboard shortcut in the app - worth bookmarking or returning to
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
uninstaller. Uninstalling does not delete any preferences you've saved
for individual scores (section 13) - those live separately under your
own Windows user profile and are covered in section 16.3 if you ever
want to clear them by hand.

### 2.2 Opening a Score File

Choose File > Open... (or press `Ctrl+O`). A standard file-open dialog
titled "Open Score" appears. Choose your file and select Open. Once the
file has finished loading, the five regions and status bar (section 3)
populate automatically - Region 1 with the score's title, composer, key,
time signature and tempo, Region 2 with its parts and staves, and so on.
The window's title bar always shows "Recall Score - `<filename>`" once a
file is loaded, so you can confirm which piece is open at any time.

Recall Score also remembers where you were in a piece: reopening a file
you've already worked with picks up right where you left off, at the
same note, rather than starting back at the beginning.

### 2.3 Supported File Types

Recall Score opens MusicXML files - `.xml`, `.musicxml`, and the
compressed `.mxl` format that many notation programs (including
MuseScore) export by default - Standard MIDI Files - `.mid` and `.midi`
- and Guitar Pro files - `.gp`. A Guitar Pro file's parts show up in
Region 2 as tab staves rather than the usual clef labels (section 3.3).

MIDI files carry far less information than a real MusicXML score: no
part/instrument names beyond whatever the file itself declares (Region 2
shows one row per track rather than the usual part/stave/voice detail,
since a MIDI track has no real staff or voice concept), and often no - or
wrong - key signature. Edit > Instruments... and Edit > Key Signature...
(section 14.2) correct either.

Recall Score can also import a song directly from an Ultimate Guitar tab
page - its chords and lyrics from a chords page, or its guitar tablature
(with real string and fret numbers) from an ASCII-tablature "Tab" page -
see section 10. If a MusicXML file already carries its own chord symbols
and/or lyrics (for example a lead-sheet-style score exported from
MuseScore), those are picked up automatically as extra Chords and Lyrics
parts too - see section 10.6.

### 2.4 A Five-Minute First Walkthrough

A short first run-through, once you have a MusicXML file to open:

1. Open a file. `Ctrl+O`, choose your file. Region 1 now describes the
   piece - title, composer, key, time signature, starting tempo.
2. Get to the notes. Press `C` from anywhere to jump straight to the
   Note region (Region 3, section 3.4).
3. Step through it. Press `Right Arrow` a few times. Each press moves to
   the next note or chord and plays it. `Left Arrow` goes back.
4. Listen to a chord's individual notes. If you land on a chord (several
   notes at once), press `Down Arrow` to hear each note in it one at a
   time, `Up Arrow` to go back up.
5. Try muting a part. Press `Tab` twice to reach Region 2 (Parts,
   Staves and Voices), which opens fully collapsed. Press `Right Arrow`
   on a part to expand it, `Down Arrow` onto a stave or voice, then `F8`
   to mute it. Pressing `C` returns to the Note region - that part is now
   silent and no longer listed. `F8` again on the same row in Region 2
   restores it.
6. Check your position at any time. Press `F6` to move to the status
   bar and hear the current measure, beat, key and time signature; `F6`
   again returns you to whichever region you were last on.

From here, section 5 onward covers every navigation and playback control
in detail.

## 3. Understanding the Screen Layout

### 3.1 The Five Regions at a Glance

The main window is arranged in two rows, plus a status bar below them:
the top row holds two regions, the bottom row holds three.

- Region 1 (top-left): Score Information - the piece's metadata.
- Region 2 (top-right): Parts, Staves and Voices - what's muted or
  soloed.
- Region 3 (bottom-left): Note Timeline - the notes at your current
  position; this is where you navigate through the music.
- Region 4 (bottom-middle): Note Attributes - full detail on whatever
  is currently selected in Region 3.
- Region 5 (bottom-right): Performance - repeat barlines, 1st/2nd-time
  endings, dynamics hairpins, and other performance markings active at
  or occurring exactly at your current position (section 8).

`Tab` moves focus forward through the five regions in this order,
wrapping back to Region 1 after Region 5; `Shift+Tab` moves backward.
Each region also has its own normal Up/Down row navigation for moving
within it - only Region 3 additionally responds to the timeline keys
described in section 5, and only moving through Region 3 triggers audio
playback.

### 3.2 Region 1: Score Information

Shows the score's title, composer or artist, key signature, time
signature and starting tempo, as read from the file when it was opened.
These are the piece's opening values and don't change as you move
through the score - for values that track your current position instead
(useful on a piece whose key or time signature changes partway through),
see the status bar in section 3.7.

### 3.3 Region 2: Parts, Staves and Voices

A navigable tree mirroring the structure of the opened file: each Part
(for example "Classical Guitar") can contain one or more Staves, each
Stave one or more Voices. Every row starts collapsed; `Right Arrow` on a
part or stave reveals its children, `Left Arrow` collapses it again. A
row's name is followed by "muted", "soloed", or "muted soloed" whenever
that state applies to the row itself - a bare name means neither. `F8`
mutes or unmutes the focused row; `F9` solos or unsolos it - section 6
covers how muting and soloing combine across the hierarchy.

A percussion part's "voices" are its individual drum sounds (for example
"Closed Hi-Hat", "Snare") rather than notated voices, so one drum in a
kit can be muted or soloed without affecting the others; section 7.10
covers renaming a drum sound or changing what it plays back as. A Guitar
Pro file's stave is labelled "Tab stave" rather than a clef name, and a
track carrying real chord names or strum markings gains an extra Chords
voice, shown with the chord name, beat position and stroke direction by
default - the same treatment a MusicXML score's embedded chord symbols
get (section 10.6).

A stave carrying free-text directions written into the score - a
guitar's left-hand position marks, or a tempo/technique instruction some
notation programs write as plain text - gains an extra Stave Text voice,
listed first among that stave's voices; section 9.7 covers what it looks
and sounds like.

For a MIDI file, or an imported song's Chords, Lyrics or Tablature rows
(section 10), the tree stops at the part level: MIDI has no real stave or
voice concept, and an imported Chords, Lyrics or Tablature row has no
notated structure underneath it either, so there's nothing further to
expand.

### 3.4 Region 3: Note Timeline

The region you'll spend the most time in. It lists the note or notes
sounding at your current position in the score. `Left`/`Right Arrow`
move through time; `Up`/`Down Arrow` move between individual notes when
several sound together. Every move plays what's now current through
MIDI, using each part's own instrument sound from the file.

A small ornamental note that decorates the main note (a grace note) is
included in the reading rather than skipped - for example "A grace B"
means the main note A is decorated by a grace note on B. It's also
briefly sounded before the main note plays, so you hear the ornament,
not just its name.

### 3.5 Region 4: Note Attributes

Shows full detail for whichever note(s) are currently selected in Region
3 - by default step, octave, measure number, beat position and
duration, plus dynamics, articulation, fingering, string, fret and other
details when the source file provides them and they've been switched on
(section 9). This region updates automatically to always match Region
3's current selection.

### 3.6 Region 5: Performance

Lists whichever repeat barlines, 1st/2nd-time endings and dynamics
hairpins (crescendo/diminuendo) are active at your current position, and
any Segno, Coda, "To Coda", Fine, Da Capo or Dal Segno mark, or key/time
signature/tempo change, that occurs exactly there - a start line and an
end line for each of the first three, or a single "None" row when
nothing applies. A short sound plays whenever this list changes as you
navigate, so you know to check it. See section 8 for the full detail,
including jumping straight to a marking's start or end and the separate
whole-score Performance Report.

### 3.7 The Status Bar

Six individually focusable fields, in order: measure and beat position,
key signature, time signature, playback tempo, playback status
(Playing/Paused/Stopped) and metronome state (On/Off). Once focus is in
the status bar, `Tab`/`Shift+Tab` cycle only between these six fields and
wrap around, rather than leaving the pane - only `F6`/`Shift+F6` (section
4.2) move focus in or out of the status bar.

Unlike Region 1, the status bar tracks your current cursor position - if
a score changes key or time signature partway through, the status bar
reflects whatever is in effect where you are right now. It can also be
read at any time, from any region, using your screen reader's own
"report status bar" command (`NVDA+End` on NVDA).

## 4. Moving Between Regions

### 4.1 Cycling Through the Five Regions (Tab / Shift+Tab)

`Tab` moves focus to the next region in the Region 1 to 2 to 3 to 4 to 5
to 1 cycle; `Shift+Tab` moves in reverse. This is separate from each
region's own internal Up/Down navigation - `Tab` always changes which
region has focus, it never scrolls within one.

### 4.2 Switching Between the Regions Area and the Status Bar (F6)

`F6` toggles focus between the regions area (returning to whichever
region you last had focus in) and the status bar. `Shift+F6` does the
same thing - since there are only two panes, there's no meaningful
"reverse" direction. The menu bar is reached the normal Windows way
(the `Alt` key), not through `F6`.

### 4.3 Jumping to Any Region Directly (Z / X / C / V / B)

Each region also has its own direct-jump key that moves focus straight
to it from anywhere in the window - another region, the status bar,
wherever - without changing your timeline position. The five keys sit
together on the keyboard's bottom row, left to right, in the same order
as the five regions:

| Key | Jumps to |
| :--- | :--- |
| `Z` | Region 1, Score Info |
| `X` | Region 2, Parts List |
| `C` | Region 3, Notes |
| `V` | Region 4, Note Attributes |
| `B` | Region 5, Performance |

This saves repeatedly tabbing all the way around just to reach a
particular region.

## 5. Navigating the Timeline

Everything in this section only takes effect while focus is in the Note
region (Region 3). The same keys do nothing in the other regions - each
of those uses its own native navigation instead.

Moving the cursor with the keys in this section always steps through the
score's notated notes in written order, from start to end - it never
follows a repeat barline, ending, Segno, Coda or Da Capo/Dal Segno
instruction. Those markings are only actually followed during real
playback (section 7); section 8 covers seeing and jumping
to them directly.

### 5.1 Stepping Note by Note (Left / Right Arrow)

Moves to the next or previous active event - a position in the score
where at least one currently-visible note sounds. All notes at the new
position are selected and played together.

### 5.2 Jumping by Measure (Ctrl+Left / Ctrl+Right)

`Ctrl+Right Arrow` jumps to the first active event of the next bar.
`Ctrl+Left Arrow` jumps to the first active event of the current bar, or
to the previous bar's first active event if you're already sitting on
it. If the piece has a pickup bar, it's numbered 0 and comes before bar
1. A short "Measure `<number>`" announcement is spoken just before the
notes at the new bar are read, so you always know which bar you've
landed on - the same announcement is heard when jumping by Home/End,
typing a bar number, using Go to Measure..., or navigating by voice
command.

Bar numbers come straight from the file's own notation for a MusicXML or
Guitar Pro score. A MIDI file has no real bar markers - measure
boundaries are reconstructed from its tempo and time-signature timing, so
a missing or incorrect time signature can shift them - and an Ultimate
Guitar import fabricates exactly one bar per chord change rather than
reading any real rhythm (section 10.5). Treat bar numbers from either of
those two sources as a close approximation, not a musically exact fact.

### 5.3 Jumping to the Start and End of the Piece (Home / End)

`Home` moves to the very first active note (the pickup bar, if there is
one); `End` moves to the very last. Trailing bars that are nothing but
rests padding out the final printed system don't count - `End` lands on
the last note actually played, not on empty bars after it. `Home` and
`End` never play the boundary sound (section 5.6) even if you're already
at that position, since they're jumping to a known place rather than
attempting to move past a limit.

### 5.4 Jumping to a Specific Bar Number

Type a bar number using the digit keys - no dialog needed - then press
`Enter` to jump straight to its first active event, which plays
immediately. This works from anywhere in the window: any of the five
regions or the status bar, exactly like Play and the tempo
keys. The number you're building shows in the status bar's position
field as you type. Press `Escape` at any point before `Enter` to clear
what you've typed without moving, and any ordinary move (an arrow key, a
menu jump, Find) also clears a half-typed number so a later `Enter`
can't act on a stale one. Typing a bar number that doesn't exist in the
piece plays the boundary sound (section 5.6) and leaves your position
unchanged.

You can also reach the same feature through Navigation > Go to
Measure... (`Ctrl+G`), a dialog pre-filled with your current bar number
if you'd rather use a menu.

### 5.5 Moving Between Notes in a Chord (Up / Down Arrow)

When several notes sound together at one position, `Left`/`Right Arrow`
selects and plays all of them at once. `Up`/`Down Arrow` narrows the
selection down to one note at a time, so you can hear and inspect each
note in the chord individually. Press `Ctrl+A`, or choose Edit > Select
All, at any point to reselect every note at the current position again -
this is also what makes `Shift+Space` (section 7.5) play the whole chord
together rather than just the one note `Up`/`Down Arrow` last left you
on. Select All only does anything useful from the Note region, so both
the shortcut and the Edit > Select All menu item are only active while
it has focus.

### 5.6 Boundary Sounds: What the "Doh" Means

A short, quiet, low note plays whenever you try to move past either end
of the piece - with `Left`/`Right Arrow`, `Ctrl+Left`/`Ctrl+Right`, by
typing a bar number that doesn't exist, or by pressing `Space` to start
playback while already sitting on the very last note. It's a deliberate,
unobtrusive "you've reached the edge" cue, not an error message - your
position never changes when you hear it. The same sound also plays when
Find (section 5.7) has nothing further to jump to, or when it has to
wrap back around to the first or last occurrence of what you're
searching for.

### 5.7 Finding an Attribute or Performance Marking (Ctrl+F)

Rather than stepping note by note, Find jumps you straight to
occurrences of a particular thing wherever it occurs in the score. Two
kinds of thing are findable:

- **Note attributes** - anything that hangs off a note: string, fret,
  fingering, pluck, dynamic, articulation, ornament, playing technique
  (hammer-on, harmonic, and the like), tie, slur, tuplet, grace note,
  fermata, arpeggiated chord, a cautionary or editorial accidental,
  glissando, chord symbol and chord diagram.
- **Performance markings** - structural events not tied to a single
  note: repeat and ending starts and ends, crescendo and diminuendo
  hairpins, written dynamics instructions ("cresc.", "dim.") and tempo
  instructions ("rall.", "a tempo"), Segno, Coda, To Coda, Fine, Da Capo,
  Dal Segno, key, time and tempo changes, the sustain pedal, octave
  shifts, rehearsal marks, dashed and bracket lines, clef changes, double
  barlines, and multi-measure rests.

Anything in the score that is not a plain note, a rest or a lyric is
meant to be findable. Two catch-all rows - "Other notation" and
"Direction" - make sure that even a marking this list doesn't name still
appears as its own findable row, spoken by the name the file gives it.

1. Press `Ctrl+F`, or choose Navigation > Find..., to open the Find
   dialog. It lists only attributes and markings that actually occur
   somewhere in the currently loaded score.
2. Optionally type in the **Filter** field to narrow the list as you go
   - it matches the text of the rows, so typing `trill` leaves just the
   trill rows.
3. Choose what to find and select OK. Recall Score jumps immediately to
   the nearest occurrence from your current position.
4. Press `Alt+Right Arrow` (Find Next) or `Alt+Left Arrow` (Find
   Previous) to keep moving between further occurrences without
   reopening the dialog - these two shortcuts work from anywhere in the
   window, not only with focus in the Note region.

If there are no further occurrences in the direction you're moving, Find
wraps around to the first or last one in the piece and plays the
boundary sound (section 5.6) so you know a wrap just happened, rather
than silently repeating your last stop.

#### Finding a Particular Value

For the attributes and markings where the exact value is something a
player navigates by - articulation, playing technique, dynamic,
accidental, tie, slur, glissando, tuplet and chord symbol - the dialog
breaks the single row out into one row per value found in this score.
So a piece with staccatos, accents and a couple of trills offers
"articulation (any)" plus "articulation: staccato", "articulation:
accent" and "articulation: trill" as separate rows, and Find on the
trill row visits only the trills. The other attributes - string, fret,
fingering, pluck, stave text - stay as one "any" row however many
distinct values they hold, so the list doesn't fill up with, say, one
row per fret number.

#### The Occurrence Count

Every row ends with how many occurrences it has in the score - "12
occurrences", or "1 occurrence". An occurrence is a **position**, not a
note: a chord whose three notes are all staccato counts once, and the
number tells you exactly how many times `Alt+Right Arrow` will move
before it wraps back to where you started.

For a note attribute, the count follows what you have muted in Region 2
(section 6) - muting a voice genuinely reduces how many of its
articulations you can reach, so the number drops to match. For a
performance marking the count is of the whole score and ignores muting,
because a repeat or a clef change is structural and doesn't belong to
any one voice.

#### What Is Not Made Audible

Find lets you locate ties, arpeggios, ornaments, pedal marks, octave
shifts and the rest, and your screen reader speaks them, but Recall
Score does not change the playback to perform them - a trill is spoken
as "trill" and still plays as the plain written note, and an octave
shift does not transpose what you hear. Finding and studying these
markings is the feature; sounding them is not.

## 6. Muting and Soloing Parts, Staves and Voices

### 6.1 The Part / Stave / Voice Hierarchy

Region 2 (section 3.3) mirrors the structure of the opened file: each
Part can contain one or more Staves, and each Stave one or more Voices.
A guitar-and-piano duet, for example, typically shows two Parts, with
the piano Part split into two Staves (treble and bass), each with its
own Voices.

### 6.2 Expanding and Collapsing a Row

`Right Arrow` on a part or stave with an expand indicator reveals its
children; `Left Arrow` collapses it again. Every row starts collapsed on
each score load - collapsing a row also forgets whatever was open
underneath it, so a re-expanded row always opens fresh.

### 6.3 Muting and Soloing a Row

With focus on a row in Region 2, `F8` mutes or unmutes it; `F9` solos or
unsolos it. Muting a Part or Stave silences everything nested underneath
it, in both the Note region and playback - but each child keeps its own
independent mute state in the background, so unmuting the parent
restores exactly what was set before, not a blanket "everything on"
reset.

Soloing a row overrides muting everywhere else: with anything soloed
anywhere in the tree, only the soloed row(s) and what's nested under them
sound, regardless of any other mute state - muting is set aside, not
cleared. With nothing soloed, muting works as described above. `Alt+F8`
clears every mute in the score without touching solo state; `Alt+F9`
clears every solo without touching mute state.

### 6.4 How Muting and Soloing Affect Navigation and Playback

Muting and soloing change what sounds and what's listed at each timeline
position - never which positions exist to move between. The current
timeline position, and Region 3's selection, stay exactly where they
were before and after any change in Region 2.

## 7. Listening to the Score

### 7.1 Automatic Playback During Navigation

Every move within the Note region - stepping with `Left`/`Right Arrow`,
moving within a chord with `Up`/`Down Arrow`, or muting or soloing a part
in Region 2 - immediately plays whatever is now current, using each
part's own instrument sound from the file. A chord spanning two parts
(say, piano and guitar) sounds both instruments together, not just one.

### 7.2 Playing the Whole Piece (Play / Pause / Stop)

`Space` starts playback from your current position, and also resumes
playback if it's currently paused. `Ctrl+Space` (Playback > Pause) pauses
playback - resume with `Space`, not `Ctrl+Space` again, which is why the
menu item is named just "Pause" rather than "Pause/Resume". Pausing
updates the regions to reflect wherever playback stopped. Stopping
playback - or letting it reach the end of the piece naturally - always
returns your position to wherever playback originally started from, not
to the last note heard.

Unlike stepping through the Note region with the arrow keys, real
playback follows repeat barlines, 1st/2nd-time endings, and Segno/Coda/
Da Capo/Dal Segno/Fine instructions exactly as notated - so what you
hear during Play can genuinely revisit or skip bars, even though those
same bars are simply listed in order when you browse them with
`Left`/`Right Arrow`. Looping playback follows repeat barlines and endings
within its window too, according to the "Repeat handling while looping"
choice in Play Settings (section 7.3).

### 7.3 Looping and the Lead-in Count-in

`Space` is the single play control. What it does depends on two habit
settings you can leave on or off:

- **Looping on**: `Space` loops a fixed window of bars starting from the
  bar your cursor is in, over and over, until you press `Space` again.
  Your cursor does not move while a loop plays. The window length is the
  "Loop length in bars" setting.
- **Looping off**: `Space` plays from your cursor to the end of the piece
  and stops, with your cursor following along - the ordinary transport.
- **Lead-in on**: a metronome count-in plays first, giving you a moment
  to get your hands back onto your instrument before the notes start.

Toggle looping with `Ctrl+L` (Playback > Toggle Looping) and the lead-in
with `Ctrl+I` (Playback > Toggle Lead-in). Both are announced and shown
in the status bar.

**Repeat handling while looping.** When your loop window clips a repeat
barline - the repeat sign is inside the window but the bar it jumps back
to is not - Recall Score has to choose which way through those bars to
loop. `Ctrl+R` (Playback > Cycle Loop Repeat Handling) cycles between
three readings, spoken aloud each press:

- **Repeat the first play-through** - the repeat is taken and its
  first-time ending played, so the loop keeps going round the repeated
  path.
- **Repeat the second play-through** - the first-time ending is skipped
  and the final ending played, so the loop is the "last time through"
  version.
- **Alternate the first and second play-throughs** - the two versions
  alternate on successive loop passes, the way a real repeat is performed
  once each way.

When the loop is long enough that the repeat's target bar *is* inside the
window, repeats and endings just play as they normally would - the choice
only matters for a clipped repeat. If a loop pass runs off the end of the
piece before its bar count is met, it stops at the last bar and the loop
restarts from the top. `Ctrl+R` says "Looping is off" or "This score has
no repeats" when it cannot apply.

While focus is in the Note region, `Alt+PageUp` and `Alt+PageDown`
increase or decrease the loop length by one bar at a time, and
`Ctrl+Enter` sets it directly from a number you have just typed (section
5.4) - if looping is off, `Ctrl+Enter` says "Looping is off" instead.
Each change speaks the new length aloud ("Loop length 3 bars" or "Loop
length 3 measures", depending on your Terminology (UK/US) setting).

`Enter` on its own no longer starts playback - it only completes a
half-typed bar number.

### 7.4 Play Settings (Playback > Play Settings...)

Playback > Play Settings... (`Ctrl+Shift+V`, also `Ctrl+T`) is the one
dialog for how playback behaves:

- **Playback tempo** - an exact tempo in beats per minute (see section
  7.6). Saved with this score.
- **Play a lead-in metronome click** - the master switch for the
  count-in. When on, the "Lead-in bars" and "Extra lead-in beats"
  fields set its length.
- **Repeat (loop) until stopped** - turns looping on. When on, "Loop
  length in bars" sets the window.
- **Repeat handling while looping** - how a repeat barline clipped by the
  loop window is played (section 7.3). Enabled only with looping on and a
  score that actually has repeat barlines. Like the other looping
  settings, it is a global practice habit, not saved per score.
- **Play the lead-in again on every repeat** - only meaningful with both
  looping and the lead-in switched on, and greyed out otherwise.

The lead-in and looping settings are global practice habits that follow
you between pieces; only the playback tempo is saved per score.

### 7.5 Auditioning the Current Chord (Shift+Space)

Plays every note sounding at your current position together, each held
for its own written duration. Press `Shift+Space` again at any point to
re-trigger it.

### 7.6 Changing Playback Tempo

`F` speeds playback up by 10, `S` slows it down by 10, and `D` resets to
the score's own written tempo. These are global shortcuts - they work
regardless of which region has focus, since tempo is a playback-wide
setting. For an exact value, open Play Settings... (`Ctrl+Shift+V` or
`Ctrl+T`) and type into the "Playback tempo" field.

The tempo you set is an **absolute** value between 5 and 300, where a
beat is the time-signature denominator (a quarter in 4/4, an eighth in
6/8). Recall Score keeps it inside that range - a value outside is
brought back in rather than rejected. Your setting is saved with the
score, so reopening the piece restores it.

Playback is always **flat**: any rall./accel./section tempo changes
written into the score are still described in the Performance region and
Performance Report, but they are not sounded - playback holds one
steady tempo throughout.

The status bar's "Playback tempo" field shows the current tempo in
time-signature-denominator beats per minute, and reads "(score default)"
while no tempo has been set. Because Region 1 shows the score's own
*written* marking (which may be in a different note value), the two
numbers can legitimately differ.

### 7.7 Using the Metronome

Options > Toggle Metronome, or `Ctrl+M`, turns a click on: one per beat,
with a distinctly louder, accented click on beat 1 of every bar. With
the metronome switched on, beat positions that have no note or rest of
their own become reachable, audible stops in the timeline too, so you
can navigate through - and hear the pulse of - even entirely silent
passages.

Playback > Play Metronome, or `Ctrl+Alt+Space`, is a separate free-running
click, for playing along by ear rather than following the score. It
starts clicking straight away at the current playback tempo (the `F` /
`S` / `D` tempo keys still adjust it while it runs) and in the time
signature at your current position, with the accented click on beat 1,
and it keeps going until you switch it off again. It never moves the
timeline. `Ctrl+Alt+Space` toggles it off, and so does pressing `Space` or
loading another score.

### 7.8 Using the Position Announcer

Options > Toggle Position Announcer, or `Ctrl+P`, turns on a spoken
"talking metronome": at each beat position it speaks a word for where
you are in the bar - "one" through "seven" for whole beats, and "e",
"and" or "a" for the subdivisions in between, the standard way musicians
count subdivided beats aloud. It's independent of the metronome switch
(section 7.7) - you can have either, both, or neither running at once,
and each is remembered separately.

### 7.9 Adjusting Volume and Pan (the Mixer)

Playback > Mixer... (`Ctrl+Shift+X`) opens a dialog listing every
instrument in the score, plus the metronome and the position announcer.
Select an entry, then use the Volume (0-100%) and Pan (-100% left to
+100% right) fields to adjust it - type an exact value, or use
`Home`/`End` to jump straight to that field's highest/lowest value and
`Insert` to reset it to a sensible starting point (centre for Pan, 50%
for Volume). Volume is scaled to roughly match natural loudness: 100% is
the instrument's normal level, 50% sounds about half as loud, and 0% is
silent. Muting an instrument entirely is a separate control, in Region 2
(section 6.3), not part of this dialog.

Changes take effect immediately, so different settings can be compared
before committing to them. Preview (`Alt+W`) starts or stops ordinary
playback (honouring your current loop and lead-in settings) so you can
hear whatever's been changed so far. OK keeps the changes and saves them
with the score (see section 13.1); Cancel puts everything back exactly
as it was before the dialog opened.

### 7.10 Renaming a Part or Changing Its Instrument

Edit > Instruments... (`Ctrl+Shift+I`) lists every part in the score.
Selecting one shows its name in an editable field and its GM instrument
in a searchable combo box (typing a few letters of an instrument's name
jumps to it) - changing either and selecting OK applies both to the
score. Especially useful for a MIDI file, where a track may have no
name, or an unhelpful one, and defaults to Acoustic Grand Piano when it
declares no instrument of its own.

A percussion part's own row has no single instrument to choose, since a
kit is several sounds at once - only its name can be changed there.
Underneath it, one row per drum sound (for example "Closed Hi-Hat")
allows that sound's own name and its GM percussion sound to be changed
independently. When the score has at least one percussion part, a
checkbox, "Apply MusicXML offset for percussion", also appears: some
notation programs export a percussion part's key numbers one step away
from the correct General MIDI sound, and checking it detects a
consistent shift from whichever items already match a real GM sound name
and applies the same correction across the whole part, including items
with no exact match of their own.

### 7.11 Playing a Connected MIDI Keyboard (Live MIDI Input)

If you have a MIDI keyboard or controller plugged in, Recall Score can
play it live through its own sound engine - useful for trying out a part
by ear, or simply having a familiar instrument sound while you work.

Options > Toggle Live MIDI Input, or `Ctrl+D`, turns it on or off.
Options > Live MIDI Input Settings... (`Ctrl+Shift+L`) chooses which
device to listen on (with a Refresh button, since devices can be plugged
in or removed while the dialog is open), what instrument it should sound
as, and its volume and pan - each heard immediately as you adjust it.
Notes you play live are entirely separate from the score's own playback:
navigating, muting or stopping playback in Recall Score never silences a
note you're still physically holding down on your keyboard.

### 7.12 Hands-Free Voice Control

For anyone whose hands are busy holding an instrument, spoken commands can
control playback and navigation instead of the keyboard. Toggle it on or
off with `Alt+Enter`, or Options > Toggle Voice Control - a
distinct tone confirms whether listening actually started or stopped.

Options > Voice Control Settings... (`Ctrl+Shift+R`) chooses which
microphone to listen on and how confident a spoken command must be
before it is acted on (the Confidence Threshold), plus the volume and
pan of the confirmation sound described below - both are heard
immediately as you adjust them. Its Test... button opens a practice
session that shows what was heard and whether it would have been
accepted, without controlling the app for real - useful for checking
your microphone and finding a threshold that suits your room. A word
that isn't one of the recognized commands is reported there as "Word not
in dictionary - rejected".

A short confirmation sound plays whenever a spoken command is recognized
and acted on.

The full list of recognized commands:

- play - starts or resumes playback
- stop - stops playback
- pause - pauses playback
- forward / right - moves right one note, like the Right Arrow key
- back / left - moves left one note, like the Left Arrow key
- next bar / next measure - moves to the start of the next bar
- previous bar / previous measure - moves to the start of the previous bar
- home - moves to the first note
- end - moves to the last note
- slower / faster / default speed - adjusts the playback tempo, like `S` / `F` / `D`
- looping on / looping off (or loop on / loop off) - turns looping on or off
- lead in on / lead in off - turns the lead-in count-in on or off
- go to bar `<number>` / go to measure `<number>` - jumps to a bar
  (only recognizes bar numbers that actually exist in the loaded score)
- loop length `<number>` - sets the loop length in bars (the same value
  as Playback > Play Settings...'s "Loop length in bars" field, or
  `Alt+PageUp`/`Alt+PageDown`), recognizing 1 through 64 bars
- attribute `<number>` - speaks the Nth row of the Note Attributes region
  for the currently selected note(s) without moving focus (the same lookup
  as `Ctrl+1` through `Ctrl+9` in the Note region - see section 9.6),
  recognizing 1 through 9
- slower - reduces playback tempo
- faster - increases playback tempo
- default speed - resets playback tempo to the score's own tempo

Recognition only ever matches this fixed list of phrases - nothing else is
interpreted as a command, which keeps background noise or music from
accidentally triggering something.

## 8. Performance Markings: Repeats, Endings, Codas and Dynamics

### 8.1 What Appears in the Performance Region

Region 5 (section 3.6) shows two lines for every repeat barline,
1st/2nd-time ending, or dynamics hairpin (crescendo/diminuendo) that
covers your current position - one for where it starts, one for where it
ends - for example:

```
Repeat start: bar 2
Repeat end: bar 9
```

or, for a hairpin that doesn't begin or end exactly on the first beat of
a bar:

```
Crescendo start: bar 12 beat 3, to bar 13
Crescendo end: bar 13, from bar 12 beat 3
```

Each hairpin row states its full range, so one row read on its own tells
you where the marking begins and ends. A beat position is only shown
when an endpoint doesn't fall on beat 1 of its bar - repeats and endings
never show one, since barlines only ever occur at the start of a bar.
When your current position isn't covered by any marking, Region 5 shows
a single "None" row.

Hairpins are gathered from every part in the score, not just the first.
Where more than one part has a hairpin, each row names its part, for
example "Cello: Crescendo start: bar 12, to bar 14". If the file gives a
hairpin a start with no matching end (or an end with no start), the row
says so plainly - "Diminuendo start: bar 23, no end marked in the file" -
rather than guessing or dropping it.

A written instruction such as "cresc.", "dim." or "rall." also shows as
its own one-off Region 5 row when you land on the bar it sits in - for
example `Crescendo (marked "cresc.")` or `Tempo instruction: rall.`.

Region 5 also shows a one-off row - with no start/end pair - the moment
you land exactly where the time signature or tempo changes, or exactly
on a Segno, Coda, "To Coda", Fine, Da Capo or Dal Segno mark, for
example:

```
Time signature change: 3/4
Tempo change: 96 quarter notes per minute
Segno
Coda
```

Unlike the repeat/ending/hairpin rows above, this disappears again as
soon as you move to the next note - it's a "something changed here" flag
for that one position, not a range you're inside. The score's opening
time signature and tempo are never flagged this way, since Region 1 and
the status bar already show those the moment a file loads.

For an imported Ultimate Guitar song (section 10), Region 5 also carries
up to three "what's in effect here" rows at the top - `Section:`, `Chord:`
and `Lyric:` - naming the current song section, the chord sounding now,
and the lyric being sung. These update quietly as you move through the
song: stepping to a new chord within the same section relabels the
`Chord:` row without re-sounding the change cue, while crossing into a
new section (or a new repeat/ending/hairpin) still sounds it.
`Ctrl+Home` / `Ctrl+End` on one of these rows jumps to where that
section, chord or lyric began.

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

### 8.4 The Performance Report (Tools > Performance Report...)

Tools > Performance Report... (`Ctrl+Shift+P`) opens a read-only summary of the whole
piece, independent of whatever's currently filtered in Region 2: title,
composer, key, time signature and tempo (the same details Region 1
shows), whether the piece has a pickup bar, its total number of bars, a
note count for each instrument, and a list of every repeat, ending,
Segno, Coda, "To Coda" and Fine mark and Da Capo/Dal Segno instruction
in the score by bar number.

The report's **Dynamics** section is one list, in bar order, of every
way the piece marks a change of volume: crescendo/diminuendo hairpins
(named by part where more than one part has them), written words such as
"cresc." or "dim.", and single dynamic marks like "mf" or "p". A hairpin
with a missing start or end is listed with that stated. Written tempo
instructions ("rall.", "a tempo") get their own **Tempo instructions**
section. A dashed or bracketed line drawn under a word like "cresc." is
listed separately under "Dashed lines" or "Bracket lines" - it and the
word are two things in the file, so the report shows both.

The whole report is a single flat list you can read top to bottom with
Up/Down Arrow. Like the Performance region, it describes the whole piece
and ignores whatever is currently filtered in Region 2. Close it with
the Close button or `Escape`; focus returns to wherever it was before
you opened it.

## 9. Understanding Note Attributes

### 9.1 What's Shown by Default

By default, the Note region (Region 3) speaks only each note's plain
name - for example "C", "F sharp", "B double flat". Accidentals are
always spelled out in full for clear pronunciation, and octave numbers
are left out to keep things brief. A rest is simply announced as "rest".

Region 4 always shows a fuller picture of whatever is currently selected
- step, octave, measure number, beat position and duration - plus
whichever of the extra details in section 9.2 the file provides and
you've chosen to show.

### 9.2 Adding More Detail (Dynamics, Articulation, Fingering, String, Fret)

Depending on what the source file contains, additional details may be
available: dynamics markings (forte, piano, and so on), articulation
(staccato, accent, trill, and similar), fingering, string and fret
numbers, and plucking-hand markings for guitar. A Guitar Pro file
provides string and fret the same way a MusicXML tab score does. An
attribute only appears on a note when it's both switched on for that
voice and actually present on that specific note - if a key is simply
missing from one note's row, that's expected, not a fault.

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

Options > Reorder Attributes... (`Ctrl+Shift+A`) opens a dialog scoped to whatever part,
stave or voice is currently selected in Region 2, listing every
attribute relevant there, whether it's currently switched on or not. Use
Move Up (`Alt+U`) and Move Down (`Alt+D`) to reorder them live. This
order is a single setting that applies everywhere - both Region 3's note
labels and Region 4's rows follow it - it isn't a separate ordering per
voice.

The Add/Remove... button switches the currently selected attribute on or
off, offering the same voice/stave/part/score scope choice as the
context menu in section 9.2 - a quicker way to switch on an attribute
that occurs only rarely in the score, without first having to find a
note in Region 3/4 that already shows it.

### 9.5 Grace Notes and Ornaments

A grace note - a small ornamental note attached to a main note, such as
an acciaccatura or appoggiatura - is read and sounded along with the
note it decorates, rather than skipped. Region 3 reads it as, for
example, "A grace B": the main note's name, the word "grace", then the
grace note's own name. It's briefly sounded just before the main note
plays, so the ornament itself is audible, not only described.

### 9.6 Quick Lookup by Number (Ctrl+1 through Ctrl+9)

While focus is on a note in Region 3, pressing `Ctrl+1` through `Ctrl+9`
speaks that numbered row from Region 4 - "1" for the first row, "5" for
the fifth, and so on - without moving focus away from the Note region.
It's a fast way to check one detail (say, the fret number or a dynamic
marking) mid-navigation, rather than tabbing over to Region 4 and back.
The number always matches Region 4's rows as currently displayed, so it
reflects whichever attributes are switched on and in whatever order
section 9.4 has them in. Pressing a number beyond how many rows are
currently showing does nothing - there's simply nothing there to read.
The "attribute `<number>`" voice command (section 7.12) does the same
thing hands-free.

### 9.7 Position Marks and Other Stave Text

Some scores carry free-text directions written directly into the file
alongside the real notes - a guitar's left-hand position marks (Roman
numerals), or a tempo or technique instruction some notation programs
write as plain text rather than a proper marking. Recall Score surfaces
this as its own event in the Note region, on whichever stave it's
actually written against, rather than leaving it out. It reads as just
the text itself, with nothing sounded - a position mark is a label to
read, not a note to hear - and it always comes first among that stave's
items, in both the Note region and Region 2, matching where a mark like
this sits above the stave on a printed page.

Region 4 shows a shorter set of detail for one of these than for an
ordinary note: the text itself, its measure, beat position, part and
stave - never a duration or a voice number, since a direction like
"Allegro" has no length of its own, and there's only ever one Stave Text
item per stave, so a voice number wouldn't distinguish anything. This
appears automatically wherever the source file includes it; there's no
setting to turn it on or off.

## 10. Chords and Lyrics

### 10.1 What This Feature Is For

Alongside notated scores (section 2.3), Recall Score can import a song
directly from Ultimate Guitar (ultimate-guitar.com). Two kinds of page
are supported:

- A **chords page** - chord names positioned above the lyric words they
  go with, rather than full sheet music. This is a different, simpler
  kind of material than a MusicXML or MIDI score: there's no notated
  rhythm or real bar structure, just chord changes and the words that go
  with them.
- An **ASCII-tablature "Tab" page** - the rows of dashes and fret numbers
  that spell out exactly which string and fret to play. Recall Score
  reads these into a Tablature part whose notes carry real string and
  fret numbers and play back (section 10.3), plus any plain-text chords
  and lyrics printed alongside the tab.

A MusicXML file can carry the same kind of information too - chord
symbols and/or lyric text written directly into the score alongside its
real notated notes. Recall Score picks these up automatically, with no
importing step needed - see section 10.6.

### 10.2 Importing a Song

Choose File > Import from Ultimate Guitar.... A dialog asks for the
page's web address - paste the full URL of an Ultimate Guitar chords
page (for example
`https://tabs.ultimate-guitar.com/tab/<artist>/<song>-chords-<id>`) or
ASCII-tablature "Tab" page and select OK. Only "Chords" and "Tab" pages
are supported - a Guitar Pro tab, bass tab or ukulele-chords page on the
same site will be rejected with an explanation. The import runs in the
background, the same way opening a file does, so the rest of the app
stays responsive while it fetches the page.

Once imported, Region 1 shows the song's title, artist, key, tuning,
difficulty and tempo the same way any other score does. When the page
carries the extra information, Region 1 also shows:

- **Source** - shown for a "Tab" page, noting that the material came from
  an Ultimate Guitar tablature page rather than a plain chords page.
- **Capo** - the fret a capo is placed at, for example "2nd fret".
- **Strumming Pattern** - for a single pattern, the sequence of strokes
  (down, up, muted, palm mute, pause) as written; for a song with more
  than one pattern, the names of the patterns. See Tools > Strumming
  Patterns... (section 10.7) for the full slot-by-slot detail.
- **Tablature** - for a "Tab" page, the number of tablature bars that
  were read in. (On a chords page this instead reads "Tablature blocks"
  with a count of any raw tablature riffs that were left out, so "there
  was nothing there" and "we didn't import that part" stay
  distinguishable.)
- **Ultimate Guitar ID** - the numeric ID of the tab on ultimate-guitar.com,
  shown as the last row.

### 10.3 Chords, Lyrics and Tablature as Parts

An imported song shows up in Region 2 as two parts, Chords and Lyrics -
or three, when the page is an ASCII-tablature "Tab" page, which adds a
Tablature part. Each is a single flat row with nothing further to expand
underneath - the same simplified display a MIDI track gets (section 3.3),
since none has real staves or voices. Mute any of them with `F8` exactly
like any other part.

Moving through the Note region works the same as any other score: each
step forward is one chord change. The Chords row names the chord (for
example "Fmaj7") and plays it as a plain chord. The Lyrics row shows the
words sung during that chord, or "No lyrics" for instrumental passages
such as an intro with nothing sung yet.

The Tablature row, when present, carries the actual notes read from the
tab: each shows its note name, the string and fret it's played on, and a
duration, and plays back on a steel-string guitar sound. Because an
ASCII tab has no written rhythm, the notes are laid out on a plain
even-eighth-note grid - a reading aid for stepping through the riff, not
a claim about how it's actually timed. String and fret numbers are shown
by default for this part without your having to add them (section 9.2).
Where a tab page also prints chord names and lyric lines, those still
feed the Chords and Lyrics parts as usual.

(Earlier versions played the chords as an arpeggiated strum. That is
gone: the strum audio was almost impossible to follow by ear, and a song
with more than one pattern had no way to know which one applied to a
given bar. The pattern is now shown as readable text in a dialog
instead - section 10.7.)

Most chord names are shown exactly as written ("Fmaj7", "C7", "Dsus4", a
bare "G" for G major) since a screen reader already reads those clearly.
A minor chord is the one exception: rather than show it as a bare "Am" or
"Am7" - which a screen reader reads as the letter "m", not the word
"minor" - Recall Score spells it out as "A minor" or "A minor 7". This
applies everywhere a chord name is shown, including the embedded-MusicXML
chords in section 10.6.

Because Region 3's currently-selected row is always the first one shown,
whichever part is listed first in Region 2 is the one announced by
default on every move. To hear the lyric first and the chord name
second, or vice versa, use Options > Reorder Parts... (`Ctrl+Shift+O`): a dialog listing
Chords and Lyrics with Move Up (`Alt+U`) and Move Down (`Alt+D`) buttons,
plus OK and Cancel. Moving Lyrics above Chords and selecting OK swaps
which one is read first from then on, without affecting anything already
muted or soloed in Region 2. This dialog works the same way for any
multi-part score, not just an Ultimate Guitar import.

### 10.4 Saving and Reopening an Import

An imported song only exists for the current session until you save it.
File > Save Ultimate Guitar Import As... writes it to a file on disk (a
`.ug` file) that you can reopen later with the ordinary File > Open...
dialog or from File > Recent Files - both treat it exactly like any
other score file from then on, including remembering its own settings
(section 13.1).

### 10.5 Things to Be Aware Of

Because a chord-tab page has no real notated bar structure, Recall Score
treats every chord change as one bar - this is a simplification for
navigation purposes, not a claim about the song's actual notated rhythm.
Occasionally a lyric line's timing in the source page is imprecise (the
original contributor's own spacing), which can very occasionally show a
lyric fragment split slightly oddly - this reflects the source page, not
a fault in the import.

For a "Tab" page, the same caveats apply to the Tablature part. An ASCII
tab names only the string letters and fret numbers, never octaves, so
which octave each string sounds in is inferred from a standard
low-string-up layout - right for standard tuning and the common "drop"
and step-down variants, but not for unusual tunings. Rhythm is the even
grid described in section 10.3, and any lead-in text, technique markers
(hammer-ons, slides and the like) or spacing quirks in the original tab
are read as faithfully as possible but can occasionally group a note
slightly oddly.

### 10.6 Chords and Lyrics Embedded in an Ordinary MusicXML Score

Some MusicXML files carry chord symbols and/or lyric text written directly
into the score alongside its real notated notes - typically a
lead-sheet-style piece exported from a program like MuseScore, with chord
names printed above the staff and words printed underneath it. Opening
such a file with File > Open... shows this content automatically, with
no separate import step: Region 2 gains a Chords part, a Lyrics part, or
both, alongside the score's own instrument parts - each shown as a
single flat row with nothing further to expand underneath (section
10.3), the same as an Ultimate Guitar import's Chords/Lyrics parts,
since neither has any real staves or voices of its own. The score's own
real instrument keeps its normal part/stave/voice detail untouched.

Unlike an Ultimate Guitar import (section 10.3), these two parts line up
with the score's own real notated timing rather than one fabricated bar
per chord change - a chord symbol or lyric shows up at exactly the beat
it was written against, right alongside the notated note sounding at
that same moment. Mute either part with `F8` exactly like any other
part, and use Options > Reorder Parts... (section 10.3) to have the
lyric announced before the chord name, or the other way round. A bar
with a chord symbol but no note underneath it, or a note with no lyric
under it, simply has no Chords or Lyrics entry there - there's no "No
lyrics" placeholder the way an Ultimate Guitar import uses for a
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

### 10.7 The Strumming Patterns Dialog

Tools > Strumming Patterns... (`Ctrl+Shift+U`) opens a read-only view of
an Ultimate Guitar import's strum pattern (or patterns). It is disabled
unless the loaded song actually has one.

If the song has more than one pattern, a Pattern list at the top lets you
choose which to view; each entry names the pattern ("Verse", "Chorus"),
its tempo, its note subdivision and how many bars it spans. Below that, a
list has one row per slot of the pattern, each row giving the slot's time
position and its stroke - for example "Bar 1, 1: down", "Bar 1, 1 e:
pause", "Bar 1, 1 and: up muted". Time positions use the same "1", "1 e",
"1 and", "1 a" wording as the position announcer (section 7.9).

A Tempo box sets the speed of the demo playback. It starts at the tempo
you have already chosen for the score, and the same `S`, `F` and `D` keys
that change tempo in the main window (slower, faster, reset) work here
too; changing it here changes the score's playback tempo. Tick **Include
metronome click** to hear a click on each beat under the demo.

A Play pattern button (`Alt+P`) plays the pattern as audio, looping until
you press it again (it then reads Stop) or close the dialog. It plays on
whichever chord is currently selected in the Note region, or a plain C
major chord if none is. The dialog does not let you edit the pattern -
it is there to be read.

### 10.8 Jumping Between Song Sections

An Ultimate Guitar page marks its structure with section labels -
`[Intro]`, `[Verse 1]`, `[Chorus]`, `[Bridge]`, `[Outro]` and so on.
Recall Score records these as spans of bars. Two shortcuts jump straight
to a section boundary, from anywhere in the window:

- **`Ctrl+Alt+Right`** - jump to the start of the next section.
- **`Ctrl+Alt+Left`** - jump to the start of the previous section.

At the last section, `Ctrl+Alt+Right` plays the boundary sound (section
5.6) and stays put rather than wrapping. On a score with no section
information (anything that is not an Ultimate Guitar import, so far),
both shortcuts just play the boundary sound.

While the cursor is inside a section, the Performance region (Region 5,
section 8) shows it: a `Section:` context row at the top naming the
current section, plus a "Section start" and a "Section end" row giving
its bar range. `Ctrl+Home` / `Ctrl+End` on any of them jumps to the
section's first or last bar. The section is also a Find target
(section 5.7) - "Section" in the Find list steps between section starts.

## 11. Tuning Your Instrument (the Tuner)

### 11.1 Opening the Tuner

Tools > Tuner... (`Ctrl+Shift+T`) opens a chromatic tuner that listens
through your microphone - useful for tuning a guitar, bass, violin,
viola, cello, double bass, ukulele or mandolin before or during a
practice session, entirely independent of whichever score, if any, is
currently loaded.

There's no separate Start/Stop Listening control: the tuner listens
continuously for as long as the dialog is open, the same way a physical
clip-on tuner behaves once switched on, and stops the moment you close
the dialog (the Close button or `Escape`).

### 11.2 Reading the Tuner

There's no Instrument or String list to choose from first - the tuner
auto-detects whatever note is currently sounding, the nearest of the 12
chromatic notes (always named with "sharp", e.g. "D sharp", never a flat
or a symbol), so you just play the string you want to tune and it tells
you what it heard. Play a note. Once a clear, sustained pluck or bow
stroke is detected, the tuner speaks the result once - for example
"signal 50 percent. D sharp. 5 cents sharp" or "signal 62 percent. A. in
tune" - then goes quiet again until you play another note. It doesn't
talk continuously while a note rings, and it won't react to background
noise or a note that's too quiet: the Signal Threshold setting (section
11.3) controls how loud a pluck needs to be before it's trusted as a real
reading at all.

The Current Reading field alongside the spoken result always shows the
same information as plain text, so you can confirm what was detected
independently of speech - useful for checking your microphone is picking
up sound at all, even before you've settled on a threshold that suits
your room.

If you're tuning to an interval other than a plain note - for example a
deliberately dropped string - just aim for 50 cents off the natural
neighbour on whichever side you expect; the tuner will name the actual
nearest chromatic note once you're close enough to it.

### 11.3 Settings: Reference Pitch, Microphone and Sensitivity

The Settings... button opens a second dialog for the values you're
unlikely to change mid-session:

- Reference Pitch (A4), in Hz - shifts the whole pitch standard, useful
  for Baroque pitch (commonly 415Hz) or a slightly sharper orchestral
  pitch (commonly around 442-443Hz), rather than the usual 440Hz concert
  pitch.
- Signal Threshold, as a percentage - sets how loud a pluck must be
  before a reading is trusted; raise it in a noisy room, or lower it if
  the tuner isn't reacting to quiet playing.
- Device - chooses which microphone to listen on, with a Refresh button
  to re-scan for devices that were plugged in after the dialog opened.
  Unlike the other two fields, a device change here takes effect
  immediately, since the main Tuner dialog keeps listening the whole
  time this Settings dialog is open.

For best results, make sure any microphone enhancement features (echo
cancellation, noise suppression and similar effects, usually configured
through your microphone's own control panel or Windows' sound settings)
are switched off - they can distort the signal enough that the tuner
can't lock onto a clear pitch.

## 12. Terminology: UK and US Music Vocabulary

### 12.1 What Changes Between UK and US Wording

Recall Score can speak either UK or US musical terminology: bar versus
measure, and the crotchet/quaver/semiquaver family versus quarter
note/eighth note/sixteenth note. This is purely a matter of wording on
screen and in speech - nothing about how the score is stored, counted or
played changes underneath it.

One family is deliberately left out of this toggle: stave/staff naming
(Region 2's clef labels, and Region 4's "stave" attribute) always reads
the same way regardless of which terminology language is selected.

### 12.2 Switching Terminology Language

Options > Terminology (UK/US) offers UK and US as two mutually
exclusive choices - exactly one is always selected at a time. This is a
single preference that applies across the whole application, not tied to
any individual score, so opening a different file mid-session never
changes which wording you're hearing.

## 13. Settings Are Remembered

### 13.1 What's Saved Per Score

For each individual score file, Recall Score remembers, and restores the
next time that file is opened:

- Your last position in the timeline, so you pick up where you left off.
- Which parts, staves and voices are muted or soloed.
- Whether the metronome is switched on.
- Whether the position announcer is switched on.
- Which note attributes are shown for each voice (section 9.2).
- The order those attributes are read in (section 9.4).
- Volume and pan set for each instrument, the metronome and the position
  announcer, via the Mixer (section 7.9).
- Renamed parts, instrument-sound overrides, and any percussion sound
  renames, reassignments or offset correction (section 7.10).
- A key signature override, if one was set (Edit > Key Signature...,
  section 14.2).
- A custom part order, if one was set (Options > Reorder Parts...).

Files are matched by their own filename, so moving a file to a different
folder doesn't lose its saved settings. If a saved setting no longer
matches the file - for example a part that's since been renamed or
removed - it's simply left out rather than causing an error or a dialog.

### 13.2 What's Saved Across All Scores

Your UK/US terminology choice (section 12) and your Tuner, Live MIDI
Input and Voice Control settings are preferences that apply to every
score, not just one - they stay as you last set them no matter which
file you open next.

### 13.3 Clearing Saved Preferences for a Score

File > Clear Preferences for `<filename>` deletes just that one file's
saved settings, so it reverts to defaults the next time it's opened.
This menu item is disabled when no file is currently loaded.

File > Open Local Folder opens the folder on disk where these saved
settings actually live, in case you ever want to inspect or back them up
directly (see also section 16.3).

## 14. Menu Reference

### 14.1 File Menu

| Item | Shortcut | What it does |
| :--- | :--- | :--- |
| Open... | Ctrl+O | Opens a MusicXML, MIDI or Guitar Pro file, or a previously saved Ultimate Guitar import (section 10.4). |
| Recent Files | - | Submenu listing the last 8 files you've opened, most recent first, for quick reopening. |
| Import from Ultimate Guitar... | - | Imports a song from an Ultimate Guitar tab page URL - chords and lyrics from a chords page, or guitar tablature from an ASCII "Tab" page (section 10). |
| Save Ultimate Guitar Import As... | - | Saves the currently loaded Ultimate Guitar import to a file so it can be reopened later (section 10.4). Only meaningful when an Ultimate Guitar import is currently loaded. |
| Open Local Folder | - | Opens the folder where saved preferences are stored. |
| Clear Preferences for `<filename>` | - | Deletes the currently loaded file's saved settings. Disabled when no file is loaded. |
| Exit | - | Closes Recall Score. |

### 14.2 Edit Menu

| Item | Shortcut | What it does |
| :--- | :--- | :--- |
| Select All | Ctrl+A | Reselects every note at the current position (section 5.5), so `Shift+Space` plays them all together. Only enabled while focus is in the Note region. |
| Instruments... | Ctrl+Shift+I | Renames a part, changes its instrument, or edits individual percussion sounds (section 7.10). |
| Key Signature... | Ctrl+Shift+K | Overrides the whole piece's key signature - a single choice from a list of all major and minor keys, or "use the file's own key". Mainly for MIDI files, which often carry no key signature at all. |

### 14.3 Navigation Menu

| Item | Shortcut | What it does |
| :--- | :--- | :--- |
| Move to First Note | Home | Jumps to the first active note. Only enabled while focus is already in the Note region. |
| Move to Last Note | End | Jumps to the last active note. Only enabled while focus is already in the Note region. |
| Go to Measure... | Ctrl+G | Opens a dialog, pre-filled with the current bar, to jump to a specific bar number. |
| Find... | Ctrl+F | Opens the Find dialog (section 5.7). |
| Find Next | Alt+Right Arrow | Jumps to the next occurrence of whatever Find last armed (section 5.7). |
| Find Previous | Alt+Left Arrow | Jumps to the previous occurrence of whatever Find last armed (section 5.7). |
| Next Section | Ctrl+Alt+Right Arrow | Jumps to the start of the next song section (section 10.8). |
| Previous Section | Ctrl+Alt+Left Arrow | Jumps to the start of the previous song section (section 10.8). |
| Move to Info | Z | Jumps focus to the Score Info (metadata) region from anywhere. |
| Move to Parts List | X | Jumps focus to the Parts List region from anywhere. |
| Move to Notes | C | Jumps focus to the Note region from anywhere, without moving your timeline position. |
| Move to Attributes | V | Jumps focus to the Note Attributes region from anywhere. |
| Move to Performance | B | Jumps focus to the Performance region from anywhere. |

### 14.4 Playback Menu

| Item | Shortcut | What it does |
| :--- | :--- | :--- |
| Play/Stop | Space | Starts playback from the current position (looping when looping is on), resumes from pause, or stops it (sections 7.2, 7.3). |
| Pause | Ctrl+Space | Pauses playback; resume with Space, not Ctrl+Space again (section 7.2). |
| Play Metronome | Ctrl+Alt+Space | Starts or stops a free-running click track at the current tempo, without moving the timeline, for playing along by ear (section 7.7). |
| Play Settings... | Ctrl+Shift+V (also Ctrl+T) | Sets the playback tempo, the lead-in count-in, and looping (sections 7.4, 7.6). |
| Toggle Looping | Ctrl+L | Turns looping playback on or off (section 7.3). |
| Toggle Lead-in | Ctrl+I | Turns the metronome count-in before playback on or off (section 7.3). |
| Cycle Loop Repeat Handling | Ctrl+R | Cycles how a repeat barline clipped by the loop window is played: first play-through, second play-through, or alternating (section 7.3). |
| Mute | F8 | Mutes or unmutes the focused row in the Parts region (section 6.3). |
| Solo | F9 | Solos or unsolos the focused row in the Parts region (section 6.3). |
| Unmute All | Alt+F8 | Clears every mute in the score (section 6.3). |
| Unsolo All | Alt+F9 | Clears every solo in the score (section 6.3). |
| Mixer... | Ctrl+Shift+X | Opens the volume/pan mixer for every instrument, the metronome and the position announcer (section 7.9). |

### 14.5 Options Menu

| Item | Shortcut | What it does |
| :--- | :--- | :--- |
| Terminology (UK/US) | - | Submenu to choose UK or US wording (section 12.2). |
| Toggle Metronome | Ctrl+M | Turns the beat click on or off (section 7.7). |
| Toggle Position Announcer | Ctrl+P | Turns the spoken beat-position announcer on or off (section 7.8). |
| Toggle Live MIDI Input | Ctrl+D | Turns a connected MIDI keyboard's live playback through Recall Score on or off (section 7.11). |
| Live MIDI Input Settings... | Ctrl+Shift+L | Chooses the MIDI device, instrument, volume and pan for live input (section 7.11). |
| Toggle Voice Control | Alt+Enter | Turns hands-free voice control on or off (section 7.12). |
| Voice Control Settings... | Ctrl+Shift+R | Chooses the microphone and confidence threshold for voice control (section 7.12). |
| Reorder Attributes... | Ctrl+Shift+A | Changes the order note attributes are read in, and switches attributes on or off, for the current Region 2 scope (section 9.4). |
| Reorder Parts... | Ctrl+Shift+O | Changes the order parts are listed in Region 2, and in turn the order their notes are listed in Region 3 (section 10.3). |

### 14.6 Tools Menu

| Item | Shortcut | What it does |
| :--- | :--- | :--- |
| Tuner... | Ctrl+Shift+T | Opens the microphone-based chromatic tuner (section 11). |
| Performance Report... | Ctrl+Shift+P | Opens a read-only summary of the whole piece (section 8.4). |
| Strumming Patterns... | Ctrl+Shift+U | Opens a read-only view of an Ultimate Guitar import's strum pattern(s), with a tempo / metronome-click control and looped demo playback (section 10.7). Disabled unless such an import is loaded. |

### 14.7 Help Menu

| Item | Shortcut | What it does |
| :--- | :--- | :--- |
| User Guide... | - | Opens this guide. |
| About Recall Score... | - | Shows the application name, version number and a short description. |

## 15. Keyboard Shortcut Reference

| Action | Keystroke |
| :--- | :--- |
| Move focus to the next / previous region | Tab / Shift+Tab |
| Toggle focus between the regions area and the status bar | F6 / Shift+F6 |
| Jump focus to the Score Info region from anywhere | Z |
| Jump focus to the Parts List region from anywhere | X |
| Jump focus to the Note region from anywhere | C |
| Jump focus to the Note Attributes region from anywhere | V |
| Jump focus to the Performance region from anywhere | B |
| Step to the next / previous active event *(Note region only)* | Left Arrow / Right Arrow |
| Jump to the first active event of the next / current-or-previous bar *(Note region only)* | Ctrl+Left Arrow / Ctrl+Right Arrow |
| Jump to the first / last active note *(Note region only)* | Home / End |
| Type a bar number, then jump to it *(any region or the status bar)* | 0-9, then Enter |
| Type a number, then set it as the loop length *(any region or the status bar)* | 0-9, then Ctrl+Enter |
| Clear a typed bar number without moving *(any region or the status bar)* | Escape |
| Move between notes within a chord *(Note region only)* | Up Arrow / Down Arrow |
| Reselect every note at the current position, so `Shift+Space` plays them all together *(Note region only, also Edit > Select All)* | Ctrl+A |
| Speak the Nth row of the Note Attributes region without moving focus *(Note region only)* | Ctrl+1 - Ctrl+9 |
| Open the Go to Measure dialog | Ctrl+G |
| Open the Find dialog | Ctrl+F |
| Jump to the next / previous occurrence of the current Find target | Alt+Right Arrow / Alt+Left Arrow |
| Jump to the start of the next / previous song section | Ctrl+Alt+Right Arrow / Ctrl+Alt+Left Arrow |
| Expand / collapse the focused row *(Parts List region only)* | Right Arrow / Left Arrow |
| Mute / unmute the focused row *(Parts List region only)* | F8 |
| Solo / unsolo the focused row *(Parts List region only)* | F9 |
| Clear every mute in the score *(Parts List region only)* | Alt+F8 |
| Clear every solo in the score *(Parts List region only)* | Alt+F9 |
| Play / stop playback from the current position, looping when looping is on (also resumes from pause) | Space |
| Pause playback (resume with Space, not Ctrl+Space again) | Ctrl+Space |
| Complete a pending typed bar number *(any region or the status bar)* | Enter |
| Toggle looping on/off | Ctrl+L |
| Toggle the lead-in count-in on/off | Ctrl+I |
| Cycle how a clipped repeat is handled while looping | Ctrl+R |
| Increase / decrease the loop length by one bar, spoken aloud *(Note region only)* | Alt+PageUp / Alt+PageDown |
| Set the loop length from a typed number *(any region or the status bar)* | Ctrl+Enter |
| Play every note at the current position together | Shift+Space |
| Increase / decrease playback tempo by 10 *(works from any region or the status bar)* | F / S |
| Reset playback tempo to the score's own tempo *(works from any region or the status bar)* | D |
| Open the Play Settings dialog | Ctrl+Shift+V (also Ctrl+T) |
| Toggle the metronome on/off | Ctrl+M |
| Start / stop a free-running click track at the current tempo, without moving the timeline | Ctrl+Alt+Space |
| Toggle the position announcer on/off | Ctrl+P |
| Toggle live MIDI input on/off | Ctrl+D |
| Open the Live MIDI Input Settings dialog | Ctrl+Shift+L |
| Toggle voice control on/off | Alt+Enter |
| Open the Voice Control Settings dialog | Ctrl+Shift+R |
| Open the Mixer dialog | Ctrl+Shift+X |
| Start / stop playback from the Mixer dialog *(Mixer dialog only)* | Alt+W |
| Open the Instruments dialog | Ctrl+Shift+I |
| Open the Key Signature dialog | Ctrl+Shift+K |
| Open the Strumming Patterns dialog | Ctrl+Shift+U |
| Play / stop the strum pattern demo *(Strumming Patterns dialog only)* | Alt+P |
| Tempo slower / faster / reset *(Strumming Patterns dialog only)* | S / F / D |
| Open the Tuner dialog | Ctrl+Shift+T |
| Open the Reorder Attributes dialog | Ctrl+Shift+A |
| Move the selected attribute up / down *(Reorder Attributes dialog only)* | Alt+U / Alt+D |
| Open the Reorder Parts dialog | Ctrl+Shift+O |
| Move the selected part up / down *(Reorder Parts dialog only)* | Alt+U / Alt+D |
| Jump to the start / end of the focused Performance region entry *(Performance region only)* | Ctrl+Home / Ctrl+End |
| Open the Performance Report | Ctrl+Shift+P |
| Open a note attribute's context menu *(Note Attributes region only)* | right-click, or Menu key / Shift+F10 |
| Open a score file | Ctrl+O |

## 16. Troubleshooting

### 16.1 No Sound

Recall Score plays sound through a bundled audio engine and instrument
library that need to start up successfully when the application
launches. If your machine has no working audio output, or something
about the installation is incomplete, Recall Score still runs and lets
you navigate and use every region normally - it simply won't produce any
sound, without announcing that fact on screen. As a first check, confirm
your system's normal audio output is working outside Recall Score too.

### 16.2 A File Won't Open

If a file fails to load, nothing changes on screen. Check the log file
at `%LOCALAPPDATA%\Recall Score\recall_score.log` for details of what
went wrong. The most common cause is a file that isn't valid MusicXML,
or isn't one of the supported extensions (section 2.3): `.xml`,
`.musicxml` or `.mxl`.

### 16.3 Where Settings Are Stored on Disk

File > Open Local Folder opens the storage location directly. Both your
per-score settings (section 13.1) and your shared preferences (section
13.2) live under your own Windows user profile, entirely separate from
where Recall Score itself is installed - reinstalling or moving the
application doesn't affect them.

## 17. Getting Help and Reporting Problems

If you run into a problem, Help > About Recall Score... shows the exact
version you're running - worth including if you report an issue. Check
section 16 (Troubleshooting) first; if that doesn't resolve it, please
raise an issue on the project's GitHub page:

<https://github.com/Chessel85/ScoreReader/issues>

Include what you were doing, the version number, and - if the app was
involved - the contents of `recall_score.log` (section 16.2).
