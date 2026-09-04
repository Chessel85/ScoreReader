# Running Recall Score from source on macOS

You are helping test whether Recall Score works on macOS — above all, whether it
is usable with **VoiceOver**. This takes about 20 minutes. It changes nothing on
your Mac beyond installing Homebrew and one library, plus a self-contained Python
environment inside the project folder.

## 1. Check your Mac

Apple menu -> About This Mac. Note two things and send them back:

- The **Chip** line — "Apple M1/M2/M3/..." (Apple Silicon) or "Intel".
- The **macOS version** (e.g. "Sonoma 14.5"). macOS 12 or newer is required.

## 2. One-time tools

Open **Terminal** (Applications -> Utilities -> Terminal) and run:

```bash
xcode-select --install
```

Click through the dialog if it appears; if it says the tools are already
installed, carry on.

If you do not already have Homebrew, install it from https://brew.sh, then:

```bash
brew install fluid-synth python@3.13
```

## 3. Get the code

The repository is public.

```bash
git clone https://github.com/Chessel85/RecallScore.git
cd RecallScore
```

## 4. Python environment

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

If `pip` fails on a package called **vosk** (that is for voice control, which we
are not testing), install everything else without it and continue:

```bash
pip install PySide6==6.11.1 music21==10.5.0 pyfluidsynth==1.4.0 \
            python-rtmidi==1.5.8 numpy==2.5.1
```

## 5. The sound bank (needed to hear anything)

The app runs without this, but silently. To get audio:

1. Download **Airfont 380 Final** from https://musical-artifacts.com/artifacts/635
2. If the download is a `.zip` or archive, unpack it to get the `.sf2` file.
3. Move that file to exactly `soundfonts/Airfont_380_final.sf2` inside the
   `RecallScore` folder, renaming it if the download has a different name.

## 6. Run it

```bash
python main.py
```

The first time, macOS will ask for **microphone** permission — allow it (the
in-app tuner uses it). A window should open.

## 7. What to report back

Try navigating the app with your screen reader as you normally would, then tell
me:

1. Which Mac and macOS version (from step 1) — and did anything in steps 2-6
   fail, or throw up warnings?
2. Does the window open? Can you open a score with File -> Open, from the
   `examples/` folder inside the project?
3. Press Tab and Shift+Tab. Can you tell which of the five regions you have
   landed in?
4. In the note region, do the arrow keys move, and does it speak the note
   (something like "F sharp, quarter, beat 1")?
5. Tab to the parts region and press **O** on a row. Does it announce the new
   on/off state?
6. Do you hear audio when you move between notes? Is it clean, or does it
   crackle / drop out?
7. Does anything read as a wall of text, or get skipped over entirely?
8. Does any keyboard shortcut do something unexpected (macOS intercepting it)?
9. As a daily screen reader user: is this **usable**, **nearly usable**, or
   **not usable**?

Question 9 is the one that decides whether macOS is worth pursuing.

## Removing it afterwards

Delete the `RecallScore` folder. Optionally `brew uninstall fluid-synth`.
Anything the app saved lives in `~/Library/Application Support/Recall Score`
and `~/Library/Logs/Recall Score` — safe to delete.
