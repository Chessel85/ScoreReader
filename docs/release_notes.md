# Recall Score Release Notes

## 2026.1.50

* Introduced looping mode in playback settings (control+L) to allow play to end, play loop once, play loop until stopped 
* Fixed a looping playback restart that could clip the last note short at slow tempos with long loops: the restart is now driven by the sequencer actually reaching the end of the loop rather than a timer predicted a whole iteration ahead
* Changed performance report to control+shift+F to allow playback settings to be control+shift+P. Removed duplicate control+T shortcut.
* Added a Bar Line Indicator (Options menu, above Toggle Metronome, control+B): a high metronome beep when arrow-key navigation crosses a bar line. Saved per score in its preferences file, defaults off, spoken on toggle, and silent while the metronome is already on.

## 2026.1.49

* Brought the readme.md up to date
* Reintroduced letter R opening the recents submenu within the file menu
* Added a version number to the user guidw which it was written against

## 2026.1.48

** Introduced extra feature for playback to allow the user to define how looping around repeats and endings works.

## 2026.1.47

* Attempts to permit importing of Ultimate Guitar pages when viewing tablature 

## 2026.1.46

* Revised Ultimate Guitar imports, and revaped the strumming tool.

## 2026.1.43

* Created Parts menu and moved entries into it from other menus as a tidy up 

## 2026.1.41

* Ability to play just the metronome

## 2026.1.40

* Significant rework to move preview functionality into just playback and playback settings

## 2026.1.39

* Another go at improving the performance report and dynamics over extended regions but still unsatisfactory

## 2026.1.38

* Performance Report and Performance region now report crescendo/diminuendo hairpins accurately: collected from every part (not just the first), overlapping and nested hairpins each shown with their own range, and a hairpin with a missing start or end stated as such rather than dropped.
* Plain-text "cresc.", "dim.", "rall." and similar instructions now appear in the Dynamics / Tempo instruction lists and are reachable with Find.

## 2026.1.37

* Added synonyms of left and right on voice control for back and forward / left arrow key and right arrow key.

## 2026.1.36

* Converted tuner to autodetect pitch and moved settings to a dialogue accessed from the tuner.

## 2026.1.36

** Tidied up user experience for reorder attributes and reorder parts dialogues so buttons have correct shortcuts announced and focus is generally more sticky.

## 2026.1.35

* Stopped the metronome click sounding when moving up and down a chord 

## 2026.1.34

* Implemented comprehensive find feature

## 2026.1.33

* More code refinements
* Added File > Close to revert the app back to a state when first run
* Changed disabled menu behaviour away from the menu item being skipped to being announced us unavailable 
* Fixed a looping Preview of a bar of triplets restarting slightly out of time
* Slower, default and faster keystrokes now cause the new tempo to be announced
* Typing a bar number then Enter to jump to it now works from any region or the status bar, not just the Note region

## 2026.1.32

* Code review and appropriate code updates

## 2026.1.31

* Improved menu layout and shortcuts.

## 2026.1.30

* Attribute quick lookup feature by pressing control and a digit when in the note region to announce from the attribute list without moving focus 

## 2026.1.29

* Introduced concept of stave text as a peer to voices 

## 2026.1.28

* Added a tuner in a new tools menu supporting multiple instruments

## 2026.1.27

* Whenever moving to a new measure with control left/right arrow keys, the go to dialogue, typed numbers and enter, home and end, the new bar number is announced.

## 2026.1.26

* Fixed a bug where the preview loop prematurely restarted the lead in when looping at higher temporary tempos.

## 2026.1.25

* Support for speech control of playback and some navigation commands to allow hands free operation whilst practising.
* Fixed bugs where, with Preview looping on, the last note of the previewed passage could be cut short before its full duration had played, a repeat inside the passage could drift out of time at a different tempo, and the loop restart could drift out of time if the tempo was changed while it was already looping.

## 2026.1.24

* Added a find feature for attributes and performance indicators.  Use control+F to set up the find and then alt plus left and right arrow keys to find subsequent next and previous occurances.
* Added an Add/Remove button to the reorder attributes dialogue so attributes can be more easily added or removed from the notes region.
* Both these features aid adding attributes that occur sparsly in a score to the note region.

## 2026.1.23

* Title bar now appends the open score file rather than having it first
* Recall Score now remembers last location in timeline when re-opening a score file.

## 2026.1.22

* Changed shortcuts for the regions in the main app area to Z, X, C, V, and B.
* Converted the information and attribute regions to lists rather than tables so whole line is read out in one go by screen reader.

## 2026.1.21

* 
grace notes and similar ornaments are now sounded and marked up in the noet region 

## 2026.1.20

* When playing or previewing, repeats, endings and codas are respected.  Movement with cursor keys along the timeline do not.
* Codas tested with made up scores and not real world examples.

## 2026.1.19

* Added playing attached MIDI devices directly within application including instrument selection, volume and pan.

## 2026.1.18

* MIDI conflict between Recall Score MIDI and other MIDI devices fixed.
* Added alt page up and alt page down shortcut keys when in the note region to reduce and increase the preview bar length.

## 2026.1.17

- Preview settings dialogue added to Playback menu
