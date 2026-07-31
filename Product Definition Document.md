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
| **VI Reader** | Visually Impaired Score Learner | A visually impaired musician using a screen reader to explore, study, analyze, and memorize musical arrangements from score files. |
| **VI Editor** | Visually Impaired Composer / Transcriber | A visually impaired user entering new musical notation or tablature, or editing existing files to correct, transpose, or compose musical arrangements. |
| **Hands-Free Reader** | Instrument-Bound Performer | A musician operating the application while holding or playing a musical instrument, e.g. Guitar or piano, requiring hands-free navigation and control without taking hands off the instrument. |
| **Tab Reader** | Fretted Instrument Player | A musician practicing guitar, bass, or another fretted instrument using tablature defined by string, fret, and finger positions. |
| **Partially Sighted User** | User with Limited Vision | A user with some useful vision who wants to maximize the use of their remaining sight alongside screen-reader and audio feedback. |
| **Application Configurer** | App configurer | A user tailoring application preferences and options to match individual workflows. |
| **Product Owner** | Key stakeholder concerned with the application's overall lifecycle, maintenance, distribution, and community adoption. | 

### 2. Functional Requirements 

The following table lists requirements for each role along with acceptance criteria.

| Ref | Category | User Story | Acceptance Criteria |
| :--- | :--- | :--- | :--- |
| 1 | Navigation | As a VI Reader I want the application organized into discrete regions each providing a different level of detail about the music piece so that I can quickly access all levels of music information. | 1. The interface features distinct structural content regions.<br> 2. Focus transitions sequentially through the regions in a cyclic loop when pressing the forward region navigation control.<br> 3. Focus transitions in reverse order when pressing the reverse region navigation control.<br> 4. The assistive interface announces the newly focused region name immediately upon region change. |
| 2 | Navigation | As a VI Reader I want to step forward and backward through the timeline event-by-event so that I can navigate through a piece of music sequentially. | 1. Triggering step-forward moves focus to the next active musical event.<br> 2. Triggering step-backward moves focus to the previous active musical event.<br> 3. When arriving at an event, the regions are updated with all musical information occurring at that position in the score.<br> 4. Reaching the beginning or end of the score triggers an auditory boundary notification. |
| 3 | Navigation | As a VI Reader I want to skip the timeline forward and backward by complete bars so that I can quickly jump across larger sections of a score. | 1. Triggering measure-forward jumps focus directly to the first active event of the next bar.<br> 2. Triggering measure-backward jumps focus directly to the first active event of the current measure, or preceding measure if already at the first event.<br> 3. The new measure number is announced by the screen reader upon arrival. |
| 4 | Navigation | As a VI Reader I want navigation controls to work whichever region has the current focus. | 1. Pressing navigation controls including next event, previous event, next measure and previous measure work from each region.<br> 2. Navigation controls keep focus in the current region. |
| 5 | Navigation | As a VI Reader I want to be able to jump to the start and end of the piece. | 1. Activating start moves to the first measure of the piece along with a sound notification or announcement of the measure number.<br> 2. Activating end moves to the last event of the last measure and gives an audible notification or announcement of the measure number. |
| 6 | Navigation | As a VI Reader I want to be able to jump to any measure in the piece. | 1. Typing a number in Read-Only mode inputs the target bar number without needing to open a dialog window.<br> 2. Pressing Enter moves focus immediately to the first event of the typed bar number.<br> 3. Moving to the requested bar announces the new bar number and plays its first note or chord.<br> 4. Typing a bar number that does not exist plays an error sound and leaves the current focus position unchanged.<br> 5. Pressing Escape before pressing Enter clears the typed input and keeps focus at the current position. |
| 7 | Configuration | As a VI Reader I want to filter which notes appear in the timeline based on selected score, voice or instrument, so that I can study individual parts in isolation or together. | 1. Selecting one or more scores in the Score List region restricts the events displayed in the Note region to those parts.<br> 2. Deselecting a score immediately removes its associated events from the active timeline view.<br> 3. Toggling score selection retains the current timeline position. |
| 8 | Auditioning | As a VI Reader I want all displayed notes to play audibly as navigation controls move through the timeline. | 1. Moving with any navigation control plays all displayed notes at the new position.<br> 2. Moving through the timeline stops all notes currently sounding before playing new notes. |
| 9 | Auditioning | As a VI Reader I want selected notes to play audibly as I navigate up and down the note list, so that I receive immediate audio feedback of pitch and duration. | 1. Moving focus to a note in the Note region triggers audio playback of that note.<br> 2. Audio playback matches the note pitch, duration and instrument.<br> 3. Audio playback latency from navigation input to sound generation does not exceed 25 milliseconds. |
| 10 | Auditioning | As a VI Reader I want to be able to play the piece from the current position with pause and stop controls. | 1. Pressing the play control starts MIDI playback from the current position.<br> 2. Playback stops when the end of the piece is reached.<br> 3. Pressing the pause control stops playback and the last music event sounded is the position to restart playback.<br> 4. Pausing refreshes the regions to reflect the new position.<br> 5. Stopping reverts the start position to the original position. |
| 11 | Auditioning | As a VI Reader I want to trigger short phrase audio playback of the current and next bar, so that I can hear the local musical context. | 1. Triggering phrase playback initiates audio generation from beat 1 of the current measure through the end of the next measure.<br> 2. Playback stops when reaching the end of the second measure.<br> 3. Initiating playback when playback is already active stops playback. |
| 12 | Auditioning | As a VI Reader I want to vary the tempo of audio playback. | 1. Playback tempo changes do not change tempo definitions within the piece.<br> 2. Minimum and maximum tempo boundaries are enforced, e.g. 30bpm and 300bpm.<br> 3. Tempo can be changed by controls in 10bpm increments.<br> 4. A control resets the tempo to its original value. |
| 13 | Auditioning | As a VI Reader I want to play only the active note or chord at the cursor position, so that I can check the harmony without moving through the timeline. | 1. Triggering chord audition plays all notes sounding at the current time position together.<br> 2. Notes hold for their marked length or until the audition key is released or pressed again. |
| 14 | Auditioning | As a VI Reader I want an optional metronome click during playback and step navigation, so that I can keep track of my position in the bar. | 1. When metronome mode is on, phrase playback plays a click sound on every beat.<br> 2. Beat 1 of every bar plays a distinct accented click.<br> 3. Moving step-by-step onto a beat position plays a metronome tick sound.<br> 4. When metronome is on, it counts as a musical event that is stopped at when moving through the timeline even if there is no note at the position. |
| 15 | Configuration | As an Application Configurer I want to choose which note details are automatically spoken when browsing notes, so that I am not overwhelmed by unnecessary speech output. | 1. Users can turn individual property announcements on or off, e.g. beat position, bar number, duration, string, fret.<br> 2. Navigating between notes in the Note region joins active details into a single concise screen reader announcement.<br> 3. The ordering of additional information can be configured and is reflected when announcing details.<br> 4. Settings are saved when closing the application to the user's profile. |
| 16 | Voice Input | As a Hands-Free Reader I want to control main navigation and playback controls using spoken voice commands, so that I can operate the score while holding an instrument, e.g. guitar, piano. | 1. Spoken voice commands, e.g. Tab, Next, Previous, Next Bar, Previous Bar, Play Bar, perform the same actions as matching keyboard shortcuts.<br> 2. The voice command engine runs continuously when toggled on without interfering with screen reader speech.<br> 3. Successful commands are actioned as soon as possible triggering the same behaviour, screen reader announcements and sound notifications as if carried out by keystrokes. |
| 17 | Tablature | As a Tab Reader I want to check fretted instrument details for selected notes, so that I can learn exact fingerings on the fretboard. | 1. Configuration allows details of String Number, Fret Number, Voice, left finger and right finger assignments to be added to note announcements when present in the score file. |
| 18 | Tablature | As a Tab Reader I want capo information catered for in playback and fingering. | 1. Setting a capo position increases the pitch of notes on playback accordingly.<br> 2. Note names and fret positions are displayed relative to the capo position. |
| 19 | Tablature | As a Tab Reader I want chords automatically analyzed into chord names, so that I can understand the chord structure. | 1. The system identifies notes sounding at the current position and determines the chord name, e.g. G Major.<br> 2. For fretted music, the system turns fretboard positions into clear text descriptions, e.g. Barred G chord at 3rd fret.<br> 3. Chord names are added to the details region and can be configured to be read in the Note region. |
| 20 | Editing | As a VI Editor I want to switch explicitly between Read-Only mode and Edit mode, so that I do not accidentally change scores while browsing. | 1. A global two-key combination switches the application between Read-Only and Edit modes.<br> 2. Mode changes trigger an immediate screen reader announcement, e.g. Edit mode.<br> 3. Editing controls are locked while in Read-Only mode. |
| 21 | Editing | As a VI Editor I want to change note parameters by typing over values or using step controls, so that I can transcribe or edit scores quickly. | 1. When focused on an editable number field like String or Fret, typing a number replaces the current value immediately.<br> 2. Triggering step up or step down controls changes the value by 1.<br> 3. Changing a note value plays the updated note sound immediately to confirm the change. |
| 22 | File I/O | As a VI Reader I want to open files of types MusicXML, MIDI (types 1 and 2), Guitar Pro and Braille Music Editor, so that I can access a wide range of existing music. | 1. The application provides an accessible file open dialog supporting the required file types.<br> 2. Opening a valid file loads all tracks, bar structures, key signatures, time signatures, and notes into the application regions.<br> 3. Corrupt or invalid files show an accessible error message explaining the issue. |
| 23 | File I/O | As a VI Editor I want to save edited or new scores to standard formats for MusicXML, MIDI, Guitar Pro and Braille Music Editor, so that I can save my work or share it with others. | 1. System provides Save and Save As options exporting the score into valid MusicXML, MIDI, Guitar Pro or Braille Music Editor formats.<br> 2. Saved files keep all score information, bars, notes, and fretboard details such as string and fret numbers. |


## 8. Non-Functional Requirements 

| Ref # | Category | Requirement Statement | Acceptance Criteria |
| :--- | :--- | :--- | :--- |
| **NFR-01** | Cross-Platform Parity | As a Product Owner, I want the application to run natively on Windows and macOS with a unified user experience to minimize dual-platform development overhead. | • **AC-01.1:** Single Codebase: 100% of core logic, file parsing, and UI layout code executes on both Windows and macOS without OS-specific code forks (excluding platform audio API wrappers).<br>• **AC-01.2:** UI & Screen Reader Parity: Keyboard shortcuts, focus cycles, and navigation commands function identically across Windows (NVDA/JAWS) and macOS (VoiceOver).<br>• **AC-01.3:** OS Integration: Standard file dialogs and audio routing automatically conform to host OS conventions. |
| **NFR-02** | Installation & Distribution | As a Product Owner, I want installation to follow standard operating system packaging conventions so users can set up the app effortlessly. | • **AC-02.1:** Windows Packaging: Distributed as a standard installer (`.exe`/`.msi`) or self-contained binary requiring no command-line or Python setup.<br>• **AC-02.2:** macOS Packaging: Distributed as a signed `.dmg` image or `.app` bundle.<br>• **AC-02.3:** Bundled Runtime: Python runtimes and dependencies are embedded within the package so users never encounter terminal prompts during setup. |
| **NFR-03** | Maintainability & Support | As a Product Owner, I want an architecture that facilitates community development and long-term open-source support. | • **AC-03.1:** Modular Architecture: Decoupled domains (Score Model, Audio Engine, Screen Reader Interface, UI) with clear API boundaries.<br>• **AC-03.2:** Developer Onboarding: A new contributor can clone the repository and execute the full test suite in under three commands.<br>• **AC-03.3:** Test Coverage: High automated unit test coverage across core MusicXML parsing and navigation state logic. |
| **NFR-04** | Performance & Latency | As a visually impaired musician, I want real-time audio and metronome feedback so that timing and rhythmic auditioning are accurate. | • **AC-04.1:** Audition Latency: Minimal audio output latency from keypress to note generation.<br>• **AC-04.2:** Metronome Precision: Low timing jitter during metronome playback under standard application load. |
| **NFR-05** | Accessibility Responsiveness | As an NVDA/VoiceOver user, I want instant screen reader speech feedback when navigating rapidly through score elements. | • **AC-05.1:** Instant Dispatch: Speech output is triggered immediately upon changing selection between score elements.<br>• **AC-05.2:** Speech Interruption: Holding down navigation keys cancels active speech to prevent queuing stale audio announcements. |
| **NFR-06** | File Integrity & Error Handling | As a user loading external MusicXML files, I want robust file handling that prevents data loss or application crashes. | • **AC-06.1:** Graceful Error Handling: Corrupt or malformed files display an accessible error dialog without crashing the application.<br>• **AC-06.2:** Data Preservation: Unhandled custom MusicXML tags are preserved upon saving or exporting. |
| **NFR-07** | Offline Independence | As a user practicing in offline environments, I want full application functionality without requiring an internet connection. | • **AC-07.1:** Offline Operation: Core features (score navigation, editing, MIDI playback, soundfont rendering, screen reader output) operate with zero network calls. |

## 2. Core Architectural Principles
* **Screen Reader First:** Every UI widget must map cleanly to Windows UI Automation (UIA). Focus movement must trigger precise, non-verbose screen reader announcements.
* **Instant Sonification:** Structural movement (moving between notes, beats, or bars) must produce immediate, ultra-low-latency MIDI playback reflecting exact pitch, velocity, and duration.
* **Deterministic Navigation:** Focus wraps strictly through a 4-zone loop. Arrow keys operate on a single shared timeline across zones.
* **Hands-Free Parity:** Every essential hotkey navigation action must have an equivalent SAPI voice command.

---

## 3. System Architecture
+-------------------------------------------------------------------+
|                        User Interfaces                            |
|  [ Qt 6 Window / Screen Reader (UIA) ]   [ SAPI Voice Input ]     |
+-------------------------------------------------------------------+
|
v
+-------------------------------------------------------------------+
|                      Application Core Layer                       |
|  +---------------------+  +-------------------+  +-------------+  |
|  | Navigation Controller|  | Edit/State Manager|  | Chord Engine|  |
|  +---------------------+  +-------------------+  +-------------+  |
+-------------------------------------------------------------------+
|
v
+-------------------------------------------------------------------+
|                     Domain & Engine Layer                         |
|  +--------------------+  +-------------------+  +--------------+  |
|  | Score Data Model   |  | Audio/MIDI Synth  |  | SAPI Engine  |  |
|  | (MusicXML Parsing) |  | (RtMidi/Synth)    |  | (Win Speech) |  |
|  +--------------------+  +-------------------+  +--------------+  |
+-------------------------------------------------------------------+

---

## 4. Third-Party Libraries & Dependencies
* **GUI & Accessibility:** Qt 6 (Core, Widgets, Gui) configured with native UIA backend.
* **MusicXML Parsing:** `libmusicxml` or `MusicXML` C++ parser for structured DOM representation.
* **MIDI Processing & Synthesis:** `RtMidi` for cross-platform MIDI I/O; `FluidSynth` or `Windows MS Synth` for soundfont playback.
* **Voice Recognition:** Windows Speech API (SAPI 5.4 / Windows.Media.SpeechRecognition) via C++/WinRT or COM interfaces.
* **Build System:** CMake using MSVC 2022 (C++20 standard).

---

## 5. UI Definition & Navigation Paradigms

### 5.1 The 4-Zone View Architecture
The main window consists of 4 primary focus zones. Pressing `Tab` cycles focus sequentially: `Zone 1 -> Zone 2 -> Zone 3 -> Zone 4 -> Zone 1`.

1. **Piece Info Zone (`QAccessibleWidget`):** 
   * Read-only summary: Title, Composer, Key Signature, Time Signature, Tempo.
2. **Scores / Staves Zone (`QListWidget`):** 
   * List of parts/instruments (e.g., "Guitar 1", "Piano Left Hand"). Toggling item selection filters active notes in Zone 3.
3. **Notes / Event Stream Zone (`QListWidget`):**
   * List of musical events present at the *current active time position*.
   * Navigating up/down through this list plays the selected note/chord pitch instantly.
4. **Note Details Zone (`QFormLayout` / Custom List):**
   * Displays full context of the active note: Measure #, Beat #, Duration (e.g., Quarter), Voice, String, Fret, Fingering.

### 5.2 Timeline & Playback Hotkeys (Global)
* `Left / Right Arrow`: Jump to Previous / Next musical event timestamp.
* `Ctrl + Left / Right Arrow`: Jump to Previous / Next Measure (Bar).
* `Spacebar`: Audition context segment (Current Bar + Next Bar) with active metronome.
* `Shift + Spacebar`: Audition current isolated note or chord.
* `Ctrl + E`: Toggle between **Read-Only Mode** and **Edit Mode**.

---

## 6. Functional Requirements & Logic

### 6.1 View Mode & Navigation Logic
* When moving timeline positions (`Left/Right`), Zone 3 updates its list automatically.
* **Configurable Announcement Overlays:** Users can configure Zone 3 so that navigating notes automatically append specific Zone 4 properties to the screen-reader output (e.g., *"G4, Quarter Note, String 3, Fret 0, Beat 2"*).

### 6.2 Edit Mode Operations
* **Direct Value Overwrite:** When focused on a editable field in Zone 4 (e.g., Fret or String), typing a digit updates the value immediately.
* **Nudge Adjustment:** `Ctrl + Up Arrow` / `Ctrl + Down Arrow` increments/decrements pitch, fret value, or duration step.
* Changes update the underlying Score Model in memory and trigger an immediate MIDI re-audition of the modified note.

### 6.3 Algorithmic Helpers
* **Chord Detection:** An internal analyzer checks pitch classes active at the current timestamp, evaluating root notes and intervals to output a best-guess chord name (e.g., "G Major", "C7/E").
* **Guitar Tab Textual Diagrams:** Convert fretboard positions into standardized text representations for screen readers (e.g., *"Barred G Chord at 3rd Fret: 3-5-5-4-3-3"* or *"Open G Chord"*).

### 6.4 Metronome & Sonification
* Integrated high-precision audio timer.
* Emits a synthesized click track (distinct high pitch for Beat 1, low pitch for sub-beats) during Spacebar playback or step-by-step beat navigation.

### 6.5 SAPI Voice Control (Hands-Free)
Continuous background listening maps incoming speech tokens directly to navigation events:
* *"Tab"* / *"Back"* $\rightarrow$ Focus switching.
* *"Next"* / *"Previous"* $\rightarrow$ Timeline event navigation.
* *"Next Bar"* / *"Previous Bar"* $\rightarrow$ Measure navigation.
* *"Play"* / *"Play Bar"* $\rightarrow$ Trigger audition playback.

---

## 7. Key Class Structure (C++)

* **`ScoreModel`:** Data container representing the imported score, containing tracks, measures, voices, and note events.
* **`AudioEngine`:** Manages MIDI output streams, SoundFont loading, note auditioning, and metronome tick generation.
* **`AccessibilityManager`:** Interfaces with `QAccessible` to dispatch custom UIA notifications to Windows screen readers without disrupting focus states.
* **`ChordAnalyzer`:** Utility class performing harmonic analysis on pitch sets to output textual chord names and guitar position strings.
* **`VoiceCommandHandler`:** Wraps Windows SAPI to parse spoken phrases asynchronously and emit application signals.
* **`MainWindow`:** Central coordinator handling key events, focus cycling across the 4 primary UI widgets, and mode switching.

---

## 8. Testing Strategy
* **Accessibility Auditing:** Test all navigation flows using **NVDA** and **JAWS** with the display turned off to verify context clarity and avoid speech overlap.
* **Audio Latency Profiling:** Measure keypress-to-sound latency using high-resolution performance counters (target: $<25\text{ ms}$).
* **Parser Verification:** Unit test suite covering diverse MusicXML and MIDI score structures (tuplets, multi-voice, variable time signatures).
* **Voice Command Accuracy:** Integration test verifying SAPI command parsing under simulated ambient background noise.
