# ScoreReader

ScoreReader is an accessible desktop application designed to render MusicXML scores into structured, screen-reader-friendly text representations paired with real-time, low-latency MIDI playback. 

Built with PySide6 (Qt) and PyFluidSynth, ScoreReader provides a clear, multi-region navigation grid optimized for keyboard and screen reader accessibility (such as NVDA).

---

## Features

* Multi-Region Structured Grid:
  * Region 1: Score metadata (Title, Composer, Key, Time Signature, Tempo).
  * Region 2: Part, Staff, and Voice structural view with toggleable mute states.
  * Region 3: Interactive note and event timeline navigation.
  * Region 4: Detailed properties and notation inspect view for selected notes.
* Screen Reader Navigation: Clean focus management, explicit tabular layouts, and standard keyboard navigation (Tab, Shift+Tab, Arrow keys, Spacebar toggles).
* Low-Latency Audio Output: Direct MIDI audio feedback via FluidSynth using low-latency audio drivers (such as WASAPI on Windows).
* MusicXML Support: Parses standard MusicXML 4.0 score files (.xml, .musicxml).

---

## Prerequisites

Before setting up ScoreReader locally, ensure your system meets the following requirements:

1. Python 3.10 or higher: [https://www.python.org/downloads/](https://www.python.org/downloads/)
2. System Audio Drivers: 
   * On Windows, ensure the Microsoft Visual C++ Redistributable is installed (required for native FluidSynth DLLs).
3. SoundFont File:
   * ScoreReader uses FluidSynth for MIDI synthesis and requires a .sf2 SoundFont file (e.g., FluidR3_GM.sf2 or similar) placed inside the soundfonts/ directory.

---

## Getting Started (Local Development Setup)

Follow these steps to clone the repository and run ScoreReader on your machine.

### 1. Clone the Repository

Open your terminal or command prompt and clone the repository:

git clone [https://github.com/Chessel85/ScoreReader.git](https://github.com/Chessel85/ScoreReader.git)
cd ScoreReader

### 2. Create and Activate a Virtual Environment

It is recommended to use a Python virtual environment to manage dependencies cleanly.

On Windows (Command Prompt):
python -m venv venv
venv\Scripts\activate

On Windows (PowerShell):
python -m venv venv
.\venv\Scripts\Activate.ps1

On macOS / Linux:
python3 -m venv venv
source venv/bin/activate

### 3. Install Dependencies

Install PySide6 and the required Python modules:

pip install --upgrade pip
pip install PySide6 pyfluidsynth

(Note: If a requirements.txt file is present in the repository, you can also run pip install -r requirements.txt.)

### 4. Verify Binaries and SoundFont Placement

Ensure the following files are present in your project directory:
* bin/: Contains system-specific FluidSynth shared libraries (.dll files on Windows).
* soundfonts/: Contains at least one standard SoundFont file (e.g., FluidR3_GM.sf2).

### 5. Launch the Application

Run main.py from the root directory:

python main.py

---

## Keyboard Controls Overview

Tab / Shift+Tab: Move focus between UI regions
Up / Down Arrow: Move between rows/items within a region
Spacebar: Toggle mute/filter state of a Part, Staff, or Voice in Region 2
Left / Right Arrow: Navigate horizontal note sequences / time positions

---

## License

Distributed under the MIT License. See LICENSE for more information.