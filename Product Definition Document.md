# Product Definition Document: - Recall Score

## 1. Overview
Recall Score is a music score and guitar tab viewer and editor which is screen reader friendly to allow visually impaired users to learn new pieces efficiently or create their own material.
It supports MusicXML, MIDI, Guitar Pro and Braille Music Editor files.  
Workflows are optimized for screen reader users including hands free control via speech recognition.

## Objectives 
The primary objective is to strip away visual UI complexity to provide auditory and screen-reader feedback designed around a visually impaired user wanting to efficiently learn new material.  Since visually impaired users are typically unable to play a musical instrument and read music at the same time, memorising pieces is essential.  Yet it can be difficult to memorise a piece whilst also learning how to play it.   Recall Score aims to ease this dual activity.

## Roles and Requirements 

### 1. User Roles 

The following roles are defined for operating the application:

| Role | Context | Description & Primary Goal |
| :--- | :--- | :--- |
| VI Reader | Visually Impaired Score Learner | A visually impaired musician using a screen reader to explore, study, analyze, and memorize musical arrangements from score files. |
| VI Editor | Visually Impaired Composer / Transcriber | A visually impaired user entering new musical notation or tablature, or editing existing files to correct, transpose, or compose musical arrangements. |
| Hands-Free Reader | Instrument-Bound Performer | A musician operating the application while holding or playing a musical instrument, e.g. Guitar or piano, requiring hands-free navigation and control without taking hands off the instrument. |
| Tab Reader | Fretted Instrument Player | A musician practicing guitar, bass, or another fretted instrument using tablature defined by string, fret, and finger positions. |
| Partially Sighted User | User with Limited Vision | A user with some useful vision who wants to maximize the use of their remaining sight alongside screen-reader and audio feedback. |
| Application Configurer | App configurer | A user tailoring application preferences and options to match individual workflows. |
| Product Owner | Guiding product development | Key stakeholder concerned with the application's overall lifecycle, maintenance, distribution, and community adoption. | 

### 2. Functional Requirements 

The following table lists requirements for each role along with acceptance criteria.

| Ref | Category | User Story | Acceptance Criteria |
| :--- | :--- | :--- | :--- |
| 1 | Navigation | As a VI Reader I want the application organized into discrete regions each providing a different level of detail about the music piece so that I can quickly access all levels of music information. | 1. The interface features distinct structural content regions.<br> 2. Focus transitions sequentially through the regions in a cyclic loop when pressing the forward region navigation control.<br> 3. Focus transitions in reverse order when pressing the reverse region navigation control.<br> 4. The assistive interface announces the newly focused region name immediately upon region change. |
| 2 | Navigation | As a VI Reader I want to step forward and backward through the timeline event-by-event so that I can navigate through a piece of music sequentially. | 1. Triggering step-forward moves focus to the next active musical event.<br> 2. Triggering step-backward moves focus to the previous active musical event.<br> 3. When arriving at an event, the regions are updated with all musical information occurring at that position in the score.<br> 4. Attempting to step past the first or last active event in the timeline leaves the position unchanged and plays a short boundary ("doh") sound. |
| 3 | Navigation | As a VI Reader I want to skip the timeline forward and backward by complete bars so that I can quickly jump across larger sections of a score. | 1. Triggering measure-forward jumps focus directly to the first active event of the next bar.<br> 2. Triggering measure-backward jumps focus directly to the first active event of the current measure, or to the preceding measure's first active event if already there; when a pickup bar is present it precedes measure 1 as measure 0.<br> 3. The new measure number is announced by the screen reader upon arrival.<br> 4. Triggering measure-forward from the first active event of the last measure, or measure-backward from the first active event of the first bar (the pickup bar if present, otherwise measure 1), leaves the position unchanged and plays the boundary ("doh") sound. |
| 4 | Navigation | As a VI Reader I want timeline navigation controls to behave like a standard Windows list control, so that they only act when focus is in the Note region and don't surprise me by firing from elsewhere. | 1. Pressing next event, previous event, next measure, previous measure, start and end only move the timeline when focus is in the Note region.<br> 2. The same keys have no timeline effect when focus is in the Score Information, Parts List or Note Attributes regions; each of those regions uses its own native navigation instead.<br> 3. Navigation controls keep focus in the Note region. |
| 5 | Navigation | As a VI Reader I want to be able to jump to the start and end of the piece. | 1. Activating start moves to the first active event of the piece (the pickup bar if present) and announces the measure number.<br> 2. Activating end moves to the last active event of the piece and announces the measure number.<br> 3. Activating start or end never plays the boundary ("doh") sound, even if the cursor is already there, since these jump to a known limit rather than attempting to move past it. |
| 6 | Navigation | As a VI Reader I want to be able to jump to any measure in the piece. | 1. Typing a number in Read-Only mode inputs the target bar number without needing to open a dialog window.<br> 2. Pressing Enter moves focus immediately to the first event of the typed bar number.<br> 3. Moving to the requested bar announces the new bar number and plays its first note or chord.<br> 4. Typing a bar number that does not exist plays an error sound and leaves the current focus position unchanged.<br> 5. Pressing Escape before pressing Enter clears the typed input and keeps focus at the current position. |
| 7 | Filtering | As a VI Reader I want to filter which notes appear in the note region based on selected parts, staves and voice, so that I can study voices in isolation or in combination. | 1. Selecting parts, staves and voices in the parts List restricts the notes displayed in the Note region to those parts.<br> 2. Deselecting a part, stave or voice immediately removes its associated notes from the note region.<br> 3. Filtering parts on and off retains the current timeline position. |
| 8 | Auditioning | As a VI Reader I want all displayed notes to play audibly as navigation controls move through the timeline. | 1. Moving with any navigation control selects all displayed notes at the new position and hence causes all the visible notes to be played via MIDI.<br> 2. Moving through the timeline stops all notes currently sounding before playing new notes. |
| 9 | Auditioning | As a VI Reader I want selected notes to play audibly as I navigate up and down the note list, so that I receive immediate audio feedback of pitch and duration. | 1. Moving focus to a note in the Note region triggers audio playback of that note.<br> 2. Audio playback matches the note pitch, duration and instrument.<br> 3. Audio playback latency from navigation input to sound generation does not exceed 25 milliseconds. |
| 10 | Auditioning | As a VI Reader I want to be able to play the piece from the current position with pause and stop controls. | 1. Pressing the play control starts MIDI playback from the current position.<br> 2. Playback stops when the end of the piece is reached.<br> 3. Pressing the pause control stops playback and the last music event sounded is the position to restart playback.<br> 4. Pausing refreshes the regions to reflect the new position.<br> 5. Stopping reverts the start position to the original position. |
| 11 | Auditioning | As a VI Reader I want to trigger short phrase audio playback of the current and next bar, so that I can hear the local musical context. | 1. Triggering phrase playback initiates audio generation from beat 1 of the current measure through the end of the next measure.<br> 2. Playback stops when reaching the end of the second measure.<br> 3. Initiating playback when playback is already active stops playback. |
| 12 | Auditioning | As a VI Reader I want to vary the tempo of audio playback. | 1. Playback tempo changes do not change tempo definitions within the piece.<br> 2. Minimum and maximum tempo boundaries are enforced, e.g. 30bpm and 300bpm.<br> 3. Tempo can be changed by controls in 10bpm increments.<br> 4. A control resets the tempo to its original value.<br> 5. A dialogue accessed from a menu item allows the temporary playback tempo to be set to any value (including decimal points) within the hard boundaries of the application. |
| 13 | Auditioning | As a VI Reader I want to play only the active note or chord at the cursor position, so that I can check the harmony without moving through the timeline. | 1. Triggering chord audition plays all notes sounding at the current time position together.<br> 2. Notes hold for their marked length or until the audition key is released or pressed again. |
| 14 | Auditioning | As a VI Reader I want an optional metronome click during playback and step navigation, so that I can keep track of my position in the bar. | 1. When metronome mode is on, phrase playback plays a click sound on every beat.<br> 2. Beat 1 of every bar plays a distinct accented click.<br> 3. Moving step-by-step onto a beat position plays a metronome tick sound.<br> 4. When metronome is on, it counts as a musical event that is stopped at when moving through the timeline even if there is no note at the position. |
| 15 | Note augmentation  | As an Application Configurer I want to choose which note details are automatically spoken when browsing notes, so that I am not overwhelmed by unnecessary speech output. | 1. Default behaviour is each note in the note region is displayed only by its name e.g. C, D, E.<br>  2. An accidental is written out as text so screen readers announce it correctly e.g. C sharp, D flat.<br>  3. Double sharps and double flats are written in full text e.g. B double sharp. |<br> 4. It is possible to append note attributes from the notes attributes region to notes in the same voice, stave, part or score.  The ordering of attributes can also be controlled e.g. Piano finger numbers can be added to a piano stave (C finger 4), or string and fret information added to a guitar tablature stave (D string 6 fret 3). |
| 16 | Note attributes | As a VI reader I want to view details about the active notes at the current time position | 1. Each note has core attributes such as step, octave, measure, beat position and duration.<BR> 2. a rest has a step of 'rest'<br> 3. Additional attributes depend upon the contents of the input file but typically include dynamics information, stacato indicators, fingering, string and fret details. |
| 17 | As a VI reader I want measure numbers to start from 1 for the first complete bar and from zero when a pick-up measure is present | 1. The first complete bar has a measure number of one and each subbsequent bar goes up byb a count of one.<br> | 2. A pick-up measure at the start of a score, indicated by having contents that do not add up to a full measure, has a measure number of zero. |
| 18 | As a VI reader I want beat position to match the time signature of the score at the current position | 1. The first beat is numbered one.<br> 2. The denominator of the time signature is used to work out the position and duration of notes.  So a quarter note in a 4/4 time signature is a unit of 1, whilst in a 7/8 time signature a quarter note is 2 units. |
| 19 | Voice Input | As a Hands-Free Reader I want to control main navigation and playback controls using spoken voice commands, so that I get audio and speech feedback without removing my hands from the instrument. | 1. Spoken voice commands, e.g. Tab, Next, Previous, Next Bar, Previous Bar, Play Bar, perform the same actions as matching keyboard shortcuts.<br> 2. The voice command engine runs continuously when toggled on without interfering with screen reader speech.<br> 3. Successful commands are actioned as soon as possible triggering the same behaviour, screen reader announcements and sound notifications as if carried out by keystrokes. |
| 20 | Tablature | As a Tab Reader I want to check fretted instrument details for selected notes, so that I can learn exact fingerings on the fretboard. | 1. Configuration allows details of String Number, Fret Number, Voice, left finger and right finger assignments to be added to note announcements when present in the score file. |
| 21 | Tablature | As a Tab Reader I want capo information catered for in playback and fingering. | 1. Setting a capo position increases the pitch of notes on playback accordingly.<br> 2. Note names and fret positions are displayed relative to the capo position. |
| 22 | Tablature | As a Tab Reader I want chords automatically analyzed into chord names, so that I can understand the chord structure. | 1. The system identifies notes sounding at the current position and determines the chord name, e.g. G Major.<br> 2. For fretted music, the system turns fretboard positions into clear text descriptions, e.g. Barred G chord at 3rd fret.<br> 3. Chord names are added to the details region and can be configured to be read in the Note region. |
| 23 | Editing | As a VI Editor I want to switch explicitly between Read-Only mode and Edit mode, so that I do not accidentally change scores while browsing. | 1. A global two-key combination switches the application between Read-Only and Edit modes.<br> 2. Mode changes trigger an immediate screen reader announcement, e.g. Edit mode.<br> 3. Editing controls are locked while in Read-Only mode. |
| 24 | Editing | As a VI Editor I want to change note attributes by typing over values or using step controls, so that I can transcribe or edit scores quickly. | 1. When focused on an editable number field like String or Fret, typing a number replaces the current value immediately.<br> 2. Triggering step up or step down controls changes the value by 1.<br> 3. Changing a note value plays the updated note sound immediately to confirm the change. |
| 25 | File I/O | As a VI Reader I want to open files of types MusicXML, MIDI (types 1 and 2), Guitar Pro and Braille Music Editor, so that I can access a wide range of existing music. | 1. The application provides an accessible file open dialog supporting the required file types.<br> 2. Opening a valid file loads all tracks, bar structures, key signatures, time signatures, and notes into the application regions.<br> 3. Corrupt or invalid files show an accessible error message explaining the issue. |
| 26 | File I/O | As a VI Editor I want to save edited or new scores to standard formats for MusicXML, MIDI, Guitar Pro and Braille Music Editor, so that I can save my work or share it with others. | 1. System provides Save and Save As options exporting the score into valid MusicXML, MIDI, Guitar Pro or Braille Music Editor formats.<br> 2. Saved files keep all score information, bars, notes, and fretboard details such as string and fret numbers. |
| 27 | Configuration persistence | As a VI Reader I want configuration changes to persist from one session to the next for a given score/input file. | 1. The toggling of part, stave, voice and metronome activation are persistent<br> 2. Note attributes added to a voice, stave or part and shown against each note are persistent. |  


## 8. Non-Functional Requirements 

| Ref # | Category | Requirement Statement | Acceptance Criteria |
| :--- | :--- | :--- | :--- |
| **NFR-01** | Cross-Platform Parity | As a Product Owner, I want the application to run natively on Windows and macOS with a unified user experience to minimize dual-platform development overhead. | • **AC-01.1:** Single Codebase: 100% of core logic, file parsing, and UI layout code executes on both Windows and macOS without OS-specific code forks (excluding platform audio API wrappers).<br>• **AC-01.2:** UI & Screen Reader Parity: Keyboard shortcuts, focus cycles, and navigation commands function identically across Windows (NVDA/JAWS) and macOS (VoiceOver).<br>• **AC-01.3:** OS Integration: Standard file dialogs and audio routing automatically conform to host OS conventions. |
| **NFR-02** | Installation & Distribution | As a Product Owner, I want installation to follow standard operating system packaging conventions so users can set up the app effortlessly. | • **AC-02.1:** Windows Packaging: Distributed as a standard installer (`.exe`/`.msi`) or self-contained binary requiring no command-line or Python setup.<br>• **AC-02.2:** macOS Packaging: Distributed as a signed `.dmg` image or `.app` bundle.<br>• **AC-02.3:** Bundled Runtime: Python runtimes and dependencies are embedded within the package so users never encounter terminal prompts during setup. |
| **NFR-03** | Maintainability & Support | As a Product Owner, I want an architecture that facilitates community development and long-term open-source support. | • **AC-03.1:** Modular Architecture: Decoupled domains (Score Model, Audio Engine, Screen Reader Interface, UI) with clear API boundaries.<br> **AC-03.3:** Test Coverage: High automated unit test coverage across core MusicXML parsing and navigation state logic. |
| **NFR-04** | Performance & Latency | As a visually impaired musician, I want real-time audio and metronome feedback so that timing and rhythmic auditioning are accurate. | • **AC-04.1:** Audition Latency: Minimal audio output latency from keypress to note generation.<br>• **AC-04.2:** Metronome Precision: Low timing jitter during metronome playback under standard application load. |
| **NFR-05** | Accessibility Responsiveness | As an NVDA/VoiceOver user, I want instant screen reader speech feedback when navigating rapidly through score elements. | • **AC-05.1:** Instant Dispatch: Speech output is triggered immediately upon changing selection between score elements.<br>• **AC-05.2:** Speech Interruption: Holding down navigation keys cancels active speech to prevent queuing stale audio announcements. |
| **NFR-06** | File Integrity & Error Handling | As a user loading external MusicXML files, I want robust file handling that prevents data loss or application crashes. | • **AC-06.1:** Graceful Error Handling: Corrupt or malformed files display an accessible error dialog without crashing the application.<br>• **AC-06.2:** Data Preservation: Unhandled custom MusicXML tags are preserved upon saving or exporting. |
| **NFR-07** | Offline Independence | As a user practicing in offline environments, I want full application functionality without requiring an internet connection. | • **AC-07.1:** Offline Operation: Core features (score navigation, editing, MIDI playback, soundfont rendering, screen reader output) operate with zero network calls. |

## Functional Specification

### General Layout

* Standard Windows / Mac desktop application layout including title bar, menu bar, no toolbar, status bar, and main application area.
* The top-level menu includes **File**, **Edit**, **View**, **Options**, and **Help**.
* The status bar displays the current measure and beat position.
* The main application area is divided into a 2x2 grid of four equal regions:
  * **Top-left (Score Information Region):** Lists score metadata including title, composer/artist, key signature, time signature, and initial tempo.
  * **Top-right (Parts List Region):** Represents the score hierarchy (Parts -> Staves -> Voices). Each entry can be toggled on or off to show or hide corresponding notes in the Note Region. Toggling off a parent node (e.g., a stave or part) automatically hides all nested child nodes (voices/staves).
  * **Bottom-left (Note Region):** Displays a list of notes present at the current score time position. Octave numbers are omitted, and accidentals are written out in full (e.g., `D flat` instead of `Db`) for clear screen reader pronunciation.
  * **Bottom-right (Note attributes Region):** Displays notation details for selected notes in the Note Region, such as step name, octave number, measure number, beat position, and duration. Includes tablature data (string, fret, fingering) if available in the source file.
* **Navigation:** Pressing `Tab` moves focus to the next region sequentially; `Shift+Tab` moves in reverse. Standard arrow keys navigate items within each region.

### Note and Note Properties Regions

* **Timeline Navigation:** Timeline navigation keystrokes only act when focus is in the Note Region; the same keys are inert (or perform the focused region's own native behaviour) elsewhere. `Left Arrow`/`Right Arrow` step to the next/previous active event. `Ctrl+Left`/`Ctrl+Right` jump by measure: right always jumps to the first active event of the next bar; left jumps to the first active event of the current bar, or the preceding bar (the pickup bar, if present, precedes bar 1) if already there. `Home`/`End` jump to the first/last active event in the timeline. Left/Right and Ctrl+Left/Right are bounded by the first and last active events in the timeline; attempting to move past either boundary leaves the position unchanged and plays a short boundary ("doh") sound. `Home`/`End` never play the boundary sound, since they jump to a known limit rather than attempting to move past it.
* **Vertical Navigation:** Pressing `Up Arrow` or `Down Arrow` moves through individual notes present at the active time position.
* **Selection & MIDI Playback:** 
  * Moving left or right selects all active notes at the new time position and triggers simultaneous MIDI playback using the patch defined in the source file (e.g., piano, classical guitar).
  * Moving up or down selects individual notes, playing each note via MIDI as it receives focus.
  * Audio playback re-triggers on file load, timeline movement, or when visibility changes in the Parts List.
* **Note Properties View:** The Note Properties Region dynamically displays details strictly for the currently selected note(s) in the Note Region.
* **Note Display Options:** Accessible via `Options` -> `Note Display`. Allows users to customize which properties from the Note Properties Region appear directly in the Note Region labels (e.g., `"C, string 5, fret 1"`). Customizations can be applied globally or scoped to specific parts, staves, or voices.

### Score Information Region

* Automatically populates when a score file (MusicXML, MIDI, Guitar Pro, or Braille Music Editor) is loaded.
* Allows linear keyboard navigation across score metadata fields so screen readers can announce each detail clearly.

### Parts Region

* Displays the structural hierarchy of parts, staves, and voices contained within the loaded score file.


## System Architecture

## Third-Party Libraries & Dependencies
* Initial development to use Python with PySide6.
* MusicXML parsing: music21 
* MIDI playback: fluidsynth with FluidR3_GM.sf2 soundfont file.
* Voice recognition: Windows Speech API (SAPI 5.4 / Windows.Media.SpeechRecognition).  Mac equivalent tTBC. 

## Key Strokes

Unless noted otherwise, the timeline navigation keystrokes below (left/right arrow, control+left/right, home, end) only take effect when focus is in the Note region. Pressing them while focus is in another region does nothing there; each other region uses its own native keys instead (e.g. plain Up/Down moves between rows in the Parts List).

| Action | Keystroke | 
| :--- | :--- | 
| Move left and right through timeline, one active event at a time | left/right arrow keys |
| Move left/right one measure at a time (jumps to the first active event of the bar) | control + left/right arrow keys |
| Move up.down notes when in the note region | Up/down arrow keys |
| Toggle metronome on/off | control + M |
| Toggle a part, stave, voice or metronome on/off when in the parts list | O |
| Toggle edit/read-only mode | control + shift + E |
| Play notes at current position | shift + spacebar |
| play/stop playback from the current position | spacebar |
| Pause playback | control + spacebar |
| 2 bar audition | Enter |
| Move to first active note | home |
| Move to last active note  | End |
| Toggle speech control on/off | control + shift + enter |

Attempting to move left/right or control+left/right past the first or last active event in the timeline leaves the position unchanged and plays a short boundary ("doh") sound. Home and End never play this sound, since they jump to a known limit rather than attempting to move past one.

"Active event" excludes rests present only to pad a bar out to a complete measure - e.g. a final bar left resting in every voice after the piece's last real note is not a further active event to step onto or land on with End. A rest occurring between two sounding notes remains its own active event as normal, since it is meaningful playing information (Ref 16), not padding.

## Discussion Points

Much of the contents of this document are based on good experience of application development but many details remain either undefined or uncertain.  The below table aims to track these unknowns in order to help discussion and avoid assumptions.  when development hits areas of uncertainty they should be flagged  and discussed and documented below.
| Item | Details |
| :--- | :--- |
| global navigation keystrokes (RESOLVED 2026-08-06) | Decided against making navigation keystrokes global. Firing arrow-key/Home/End navigation regardless of which region has focus would be confusing and is not standard Windows application behaviour - other regions use those same keys for their own native purposes (e.g. Up/Down moving between rows). Timeline navigation keystrokes are scoped to the Note region only, per the updated Ref 4. If this proves inefficient in practice (e.g. having to Tab back to the Note region too often), revisit. |
| UK or US terminology | There is a US and UK vocab in music (not sure if that is a totally fair way of defining it.) US measure, quarter note, eighth note are bar, crotchet and quaver in UK vocab.  There should be an option to toggle between these (and any others that exist) and defining where this surfaces needs working through. |
| Key signatures | If the key is set e.g. G major, and there is an F, should the note be displayed as just F since the musician should know an F is sharpened in G major, or written out in full? In both cases, it should defo sound F sharp.  Maybe this is a user preference? |
| Status bar | As well as position, the status bar should probably show the current time signature and key at the current position as it can change throughout the score. |
| Title bar | Probably should update the title bar with the score title when it is loaded. So NVDA+T reads out application name and current file loaded |
| Focus memory in regions | It would be more user friendly if tabbing away from and returning to a region maintained the last focused row.  This could be tricky conceptually though for note details if, whilst away, the row is filtered out. |

## Known bugs

* At least for Way To Go test file, the viola does not have a stave or voice in region 2.
* In the note region, hitting home or end can change the selected item but this is not played by the midi engine. 
* The application title bar is currently Score Reader and Editor.  If going with Recall Score as the product name, should change this.


