# audio/voice_recognition.py
"""Hands-free voice control (feature/voice-control-vosk, Ref 19): an offline
Vosk (Kaldi-based) speech recognizer, capturing the microphone via
sounddevice (PortAudio) - run in a SEPARATE CHILD PROCESS
(audio/voice_recognition_worker.py), not in-process.

GOTCHA, found via live testing: vosk and the vendored FluidSynth binaries
(bin/) bundle mutually incompatible copies of the same-named MinGW runtime
DLLs (libstdc++-6.dll, libwinpthread-1.dll). Windows resolves a same-named
DLL dependency to whichever copy loaded into the process first, process-
wide, and there is no way to isolate the two within one process - confirmed
by direct testing: importing audio.synth_engine (FluidSynth) before vosk
breaks vosk; importing vosk first breaks FluidSynth instead; even explicitly
pre-loading vosk's own runtime DLL copies first still breaks FluidSynth.
Running Vosk in its own process is the only real fix - separate processes
get separate, independent sets of loaded DLLs. This is why this module never
imports vosk or sounddevice directly - see audio/voice_recognition_worker.py,
which does, and is deliberately kept import-minimal (stdlib + vosk/
sounddevice only, never PySide6/audio.synth_engine) so launching it can
never itself re-trigger the collision.

This is the second attempt at this feature - the first (SAPI 5.4, via
pywin32) is preserved on branch feature/voice-control and documented in
CLAUDE.md's "Known gaps" section. It worked once several undocumented SAPI/
win32com quirks were fixed, but the underlying engine's own accuracy proved
inconsistent even for this app's small command vocabulary, and some of the
bugs found (an empty device-token registry, a broken per-device-selection
property) were specific to that one machine's own Windows configuration -
meaning a DIFFERENT set of SAPI quirks could plausibly hit a different user.
Vosk + sounddevice sidesteps that whole class of problem: both are self-
contained, mature, cross-platform libraries with no dependency on the local
machine's own speech-recognition configuration, so the feature behaves
identically for every user.

Grammar is a JSON phrase list (audio/voice_commands.py's COMMAND_PHRASES
plus the current score's go_to_bar_phrases, plus the fixed loop_length_
phrases and attribute_phrases, plus Vosk's own recommended "[unk]"
catch-all) sent to the worker,
which passes it straight into
KaldiRecognizer's constructor - a first-class Vosk feature, not a
workaround. This is still the main accuracy lever: a small closed vocabulary
gives Vosk's decoder nothing plausible to match the user's own instrument or
background speech against.

Deliberately Qt-free (no PySide6 import anywhere in this file), the same
reason audio/midi_input.py is Qt-free: models/music_data.py mirrors
VOICE_CONTROL_CUE_CHANNEL from audio/voice_confirmation_cue.py, and models/
must stay importable with zero Qt in the chain. Crossing to Qt's main thread
from this module's own background thread is the CALLER's job - controllers/
voice_control_controller.py is where that happens, via a Signal connected
with Qt.ConnectionType.QueuedConnection (mirrors LiveMidiInputController).

Threading/process model: start() launches the worker as a child process
(subprocess.Popen) and a single background thread in THIS process that reads
newline-delimited JSON events off the worker's stdout - a "ready"/"error"
handshake (mirrors the SAPI version's readiness Event) and one "result" event
per completed utterance. All the domain logic - confidence-threshold
filtering, resolving heard text against the command vocabulary - lives HERE,
in the parent, not in the worker; the worker only ever reports a raw Vosk
result. Stopping sends the worker a {"cmd": "stop"} line, gives it a brief
grace period to exit on the calling thread, then reaps it (wait/kill/join)
on a daemon thread so a hung worker can never block the Qt main thread - see
stop(); if the parent process ever dies without a clean stop, the worker's
own stdin-closed detection (see voice_recognition_worker.py) makes it exit
too, so a crash can't leave it orphaned.

Everything here degrades gracefully if vosk/sounddevice aren't installed, or
the model directory (vosk_model/ at the repo root - see .gitignore) is
missing - VOSK_AVAILABLE mirrors FLUIDSYNTH_AVAILABLE/RTMIDI_AVAILABLE
elsewhere in this app: a warning is printed and the feature is inert, never
a crash. Checked via importlib.util.find_spec rather than an actual import,
so this (parent) process never touches vosk/sounddevice's own native code at
all - only the worker does.
"""
import importlib.util
import json
import os
import subprocess
import sys
import threading
from typing import Callable, List, Optional

from audio import voice_commands

# Frozen builds (packaging/RecallScore.spec) never bundle vosk/sounddevice
# into the MAIN app process at all - only into the separate worker
# executable (packaging/VoiceWorker.spec, see that spec's own comment on
# why). find_spec("vosk") would therefore always report unavailable in a
# packaged build even when voice control is fully installed - so frozen
# availability is instead just "does the worker exe exist", checked below
# once WORKER_EXE is known.
FROZEN = getattr(sys, "frozen", False)

# The model this feature was built and tested against (vosk-model-small-en-
# us-0.15, ~40MB, Apache-2.0) - not pip-installable, not tracked in git (see
# .gitignore's own comment). A different/larger model can be dropped in at
# this same path with no code change; Vosk's own grammar-constraint feature
# (see _build_grammar_phrases) means the small model's narrower general
# vocabulary matters far less here than it would for open dictation.
#
# TEMPORARY, under live A/B test (2026-08-24): pointed at vosk_model_large/
# (vosk-model-en-us-0.22-lgraph, ~205MB - NOT the plain -0.22, which silently
# ignores the grammar constraint entirely, confirmed live: it decoded random
# noise as an open-vocabulary word instead of respecting the phrase list).
# Only an "-lgraph" variant supports runtime/grammar graphs. Revert to
# "vosk_model" if live mic testing doesn't show better false-accept rejection
# than the small model - see git commit 7275d19 for the pre-large-model
# checkpoint.
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vosk_model_large")

# Dev-only launch target: sys.executable <this script>, a real python.exe
# interpreting a real .py file. Neither exists once frozen - see WORKER_EXE.
WORKER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice_recognition_worker.py")

# Frozen-only launch target: packaging/VoiceWorker.spec's own build, bundled
# into this app's own bundle at voice_worker/ by packaging/RecallScore.spec
# (Tree(..., prefix="voice_worker")) - sys._MEIPASS is this app's own bundle
# root here (the same __file__-faking trick RecallScore.spec's header
# comment documents for audio/synth_engine.py's PROJECT_ROOT, which is also
# how MODEL_DIR above resolves correctly with no frozen-specific code).
WORKER_EXE = os.path.join(
    getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "voice_worker", "RecallScoreVoiceWorker.exe",
)

if FROZEN:
    VOSK_AVAILABLE = os.path.isfile(WORKER_EXE)
else:
    VOSK_AVAILABLE = (
        importlib.util.find_spec("vosk") is not None
        and importlib.util.find_spec("sounddevice") is not None
    )


def _worker_command() -> List[str]:
    """The subprocess.Popen argv for launching the worker - a real python.exe
    running the worker script in dev, the worker's own standalone executable
    once frozen (see WORKER_EXE/WORKER_SCRIPT above)."""
    if FROZEN:
        return [WORKER_EXE]
    return [sys.executable, "-u", WORKER_SCRIPT]


# CREATE_NO_WINDOW (Windows-only subprocess.Popen creationflags): the worker
# is built console=True (see VoiceWorker.spec) so it gets real stdin/stdout
# pipes once frozen, which would otherwise flash a console window on screen
# every time voice control starts - this suppresses that window without
# affecting the pipes themselves. Harmless to pass in dev too (python.exe
# spawned from an already-console-attached parent doesn't open a new window
# either way), so it's applied unconditionally rather than only when FROZEN.
_POPEN_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW

# Vosk's own recommended catch-all - documented as letting the decoder say
# "none of these phrases" instead of forcing the nearest wrong match.
# GOTCHA, found via live testing on vosk-model-small-en-us-0.15: including
# "[unk]" in the grammar list passed to KaldiRecognizer broke finalization
# completely in that test - every result came back as empty text, even for a
# clearly spoken command. NOT reproduced afterward in isolated testing
# (clean synthesized-speech WAVs, both the small model and vosk_model_large,
# with this exact grammar) - "[unk]" correctly absorbed out-of-vocabulary
# words there instead of forcing a false match or breaking. Re-enabled
# (2026-08-24) for live A/B testing against the large model; if real
# microphone testing reproduces the original breakage, remove "[unk]" from
# _build_grammar_phrases again and fall back to confidence-threshold-only
# filtering. UNKNOWN_TOKEN is checked for in _handle_final_result either way,
# since a model may emit it even when not offered as a grammar option.
UNKNOWN_TOKEN = "[unk]"

# (command_name, confidence_percent 0-100, number_value) - the normalised
# shape this module hands to its callback, mirroring audio/midi_input.py's
# own "(status, pitch, velocity)" normalised-tuple convention. number_value
# is only meaningful (non-None) for the two parameterized commands,
# voice_commands.GO_TO_BAR (a measure number) and voice_commands.LOOP_LENGTH
# (a bar count).
RecognitionCallback = Callable[[str, float, Optional[int]], None]


def list_input_devices() -> List[str]:
    """Fresh enumeration every call - never cached, mirroring
    audio/midi_input.py's list_input_ports(). Returns [] (never raises) if
    vosk/sounddevice aren't importable or enumeration fails - the "warn and
    no-op" handling this app gives every optional resource. Runs the worker
    script in a one-shot --list-devices mode rather than importing
    sounddevice directly here - see module docstring on why this process
    must never import it.

    This spawns a whole Python subprocess, so it must not be called on the
    Qt main thread - main_window._scan_devices_async runs it on a
    DeviceEnumerationThread (P1). The timeout is 5s rather than 10: long
    enough for a cold PortAudio init in the worker, short enough that a
    wedged scan doesn't strand the settings dialog on "Scanning…"."""
    if not VOSK_AVAILABLE:
        return []
    try:
        result = subprocess.run(
            _worker_command() + ["--list-devices"],
            capture_output=True, text=True, timeout=5,
            creationflags=_POPEN_CREATIONFLAGS,
        )
        if result.returncode != 0:
            print(f"[WARN] Failed to enumerate voice control input devices: {result.stderr.strip()}")
            return []
        return json.loads(result.stdout)
    except Exception as e:
        print(f"[WARN] Failed to enumerate voice control input devices: {e}")
        return []


def _build_grammar_phrases(total_measures: int) -> List[str]:
    """Every fixed command phrase plus the current score's "go to bar N"/
    "go to measure N" phrases plus the fixed "loop length N" and
    "attribute N" phrases - the phrase list sent to the worker to restrict
    Vosk's recognition to just this vocabulary. Includes UNKNOWN_TOKEN - see
    that constant's own comment for the live-testing history behind this.
    Sent wholesale (never incrementally patched) whenever the vocabulary
    needs to change - cheap for Vosk (a fresh KaldiRecognizer), unlike the
    SAPI version's file-round-trip workaround."""
    phrases = list(voice_commands.COMMAND_PHRASES.keys())
    phrases.extend(phrase for phrase, _ in voice_commands.go_to_bar_phrases(total_measures))
    phrases.extend(phrase for phrase, _ in voice_commands.loop_length_phrases())
    phrases.extend(phrase for phrase, _ in voice_commands.attribute_phrases())
    phrases.append(UNKNOWN_TOKEN)
    return phrases


def _confidence_percent(result: dict) -> float:
    """0-100 confidence for a final Vosk result (the worker's own "result"
    event dict, {"text": ..., "words": [{"conf": 0.0-1.0, "word": ...}]}) -
    averaged across the words in this result. Defensive: an unexpected shape
    (e.g. no "words", an empty utterance) fails toward rejecting (0.0)
    rather than toward falsely accepting a command."""
    words = result.get("words") or []
    if not words:
        return 0.0
    total = sum(w.get("conf", 0.0) for w in words)
    return max(0.0, min(100.0, (total / len(words)) * 100.0))


class VoiceRecognitionManager:
    """Owns at most one running voice_recognition_worker.py child process +
    a background thread reading its stdout. NOT a QObject - takes a plain
    Python callback, not a Signal (see module docstring). The callback fires
    on this module's OWN background thread, never the caller's - marshaling
    onto Qt's main thread is the caller's job."""

    def __init__(self):
        self._callback: Optional[RecognitionCallback] = None
        self._diagnostic_callback: Optional[Callable[[str, float, bool], None]] = None
        self._ready_callback: Optional[Callable[[bool], None]] = None
        self._confidence_threshold: float = 0.0
        self._process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._ready_event = threading.Event()
        self._started_ok = False
        self._total_measures = 0

    def set_callback(self, callback: Optional[RecognitionCallback]) -> None:
        """Must be called before start() - mirrors MidiInputManager's own
        set_callback contract. Fires only for a final result that both
        passed the confidence threshold AND resolved to a real command - the
        real VoiceControlController's dispatch path. See
        set_diagnostic_callback for the practice/test dialog's "show every
        attempt" needs."""
        self._callback = callback

    def set_diagnostic_callback(self, callback: Optional[Callable[[str, float, bool], None]]) -> None:
        """(heard_text, confidence_percent, accepted) for EVERY final
        result, before the command-dispatch filtering set_callback's
        callback only sees - what the practice/test dialog needs to show
        the user what would and wouldn't have been accepted."""
        self._diagnostic_callback = callback

    def set_ready_callback(self, callback: Optional[Callable[[bool], None]]) -> None:
        """Fires exactly once per start() call, from this module's OWN
        background thread (see class docstring) - True once the worker has
        actually finished loading the model and opened the microphone,
        False if it failed or the process exited before doing so. Exists so
        start() itself can return immediately instead of blocking the
        caller's thread on Vosk's own model-load time - reported live:
        loading the ~200MB lgraph model took close to a second, and
        start() used to block the whole Qt UI thread for that entire
        duration (see start()'s own note)."""
        self._ready_callback = callback

    def list_devices(self) -> List[str]:
        """Instance wrapper around the module-level list_input_devices(), so
        a test can override per-instance (a NullVoiceRecognizer) without
        monkeypatching the module function - mirrors MidiInputManager.
        list_ports()."""
        return list_input_devices()

    def start(self, device_name: Optional[str], confidence_threshold: float) -> bool:
        """Launches the worker child process and its stdout-reader thread,
        then returns immediately - it does NOT wait for the worker to
        actually finish loading the model and open the microphone (see
        set_ready_callback for that). Returns False (never raises) only for
        preconditions checkable without the worker at all: vosk/sounddevice
        not available, the model directory missing, or the process itself
        failing to spawn.

        GOTCHA, reported live: this used to block here on self._ready_event.
        wait(timeout=10.0), synchronously, on the CALLER's thread - which is
        always the Qt main thread (VoiceControlController.toggle_enabled).
        Loading vosk-model-en-us-0.22-lgraph (~200MB) from disk took close
        to a second, during which the entire UI was frozen and the "started"
        confirmation tone was delayed by exactly that long. A watchdog
        thread below still reports failure via the ready callback if the
        worker never becomes ready within 10s, mirroring the old timeout
        without blocking anyone on it."""
        if not VOSK_AVAILABLE:
            print("[WARN] vosk/sounddevice not available; voice control disabled.")
            return False
        if not os.path.isdir(MODEL_DIR):
            print(
                f"[WARN] Voice control model not found at {MODEL_DIR} - "
                "see .gitignore's own note on where to get one."
            )
            return False
        if self.is_running:
            self.stop()

        self._confidence_threshold = confidence_threshold
        self._ready_event.clear()
        self._started_ok = False
        try:
            self._process = subprocess.Popen(
                _worker_command(),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, bufsize=1, creationflags=_POPEN_CREATIONFLAGS,
            )
        except Exception as e:
            print(f"[WARN] Failed to start voice control worker process: {e}")
            self._process = None
            return False

        self._reader_thread = threading.Thread(
            target=self._read_worker_output, daemon=True, name="VoiceRecognitionManagerReader",
        )
        self._reader_thread.start()
        self._send({
            "cmd": "start", "device_name": device_name,
            "grammar": _build_grammar_phrases(self._total_measures), "model_dir": MODEL_DIR,
        })
        threading.Thread(
            target=self._watch_for_ready_timeout, daemon=True, name="VoiceRecognitionManagerWatchdog",
        ).start()
        return True

    def _watch_for_ready_timeout(self) -> None:
        """Own background thread. If _read_worker_output never sees a
        ready/error event (or the process exits without one) within 10s,
        reports failure via the ready callback - this thread's wait()
        returns True (doing nothing further) the moment that happens
        normally, well under 10s in practice."""
        if not self._ready_event.wait(timeout=10.0):
            print("[WARN] Voice control worker did not become ready within 10s")
            self._started_ok = False
            self._ready_event.set()
            if self._ready_callback is not None:
                self._ready_callback(False)

    def stop(self) -> None:
        """Ask the worker to exit, then return almost immediately - the
        wait/kill/join is handed to a daemon thread so a wedged worker can
        never freeze the caller. This is reached from the Qt main thread
        (VoiceControlController._disconnect / .close, and start()'s own
        restart path), and a frozen GUI takes NVDA down with it.

        GOTCHA, S4: this used to do process.wait(timeout=3.0) then
        reader_thread.join(timeout=3.0) inline - up to 6s of blocked UI if
        the worker hung. Now self._process / self._reader_thread are
        detached synchronously (so is_running goes False at once and a
        following start() builds a fresh process rather than adopting this
        one), the worker is given a short ~200ms grace period to exit
        cleanly on the calling thread - it almost always does, having no
        model to unload, just a PortAudio input stream to close, which the
        Test... dialog flow wants released before it opens its own
        recognizer - and anything slower than that is left to _reap_worker
        on a background thread."""
        if self._process is None:
            return
        self._send({"cmd": "stop"})
        process, reader_thread = self._process, self._reader_thread
        self._process = None
        self._reader_thread = None
        try:
            process.wait(timeout=0.2)
        except Exception:
            threading.Thread(
                target=self._reap_worker, args=(process, reader_thread),
                daemon=True, name="VoiceRecognitionManagerReaper",
            ).start()
        # On a clean, prompt exit the stdout-reader thread ends by itself
        # the moment the worker's pipe closes; it's a daemon and nothing
        # waits on its result, so it is not joined here - that join was the
        # other half of the up-to-6s block.

    @staticmethod
    def _reap_worker(process: subprocess.Popen, reader_thread: Optional[threading.Thread]) -> None:
        """Off the calling thread: wait out a worker that didn't exit
        within stop()'s short grace period, kill it if it never does, then
        join the stdout-reader thread. Daemon thread - it cannot keep the
        app alive and its result is not observed."""
        try:
            process.wait(timeout=3.0)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        if reader_thread is not None:
            reader_thread.join(timeout=3.0)

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def rebuild_grammar(self, total_measures: int) -> None:
        """Sends the current score's total_measures (Ref 17 pickup bar
        included via voice_commands.go_to_bar_phrases) to the running
        worker, which rebuilds its KaldiRecognizer - cheap with Vosk, no
        file round-trip needed (that was a SAPI-specific workaround). A
        no-op if the worker isn't running - the next start() call picks up
        whatever total_measures was last set."""
        self._total_measures = total_measures
        if self.is_running:
            self._send({"cmd": "rebuild_grammar", "grammar": _build_grammar_phrases(total_measures)})

    def set_confidence_threshold(self, confidence_threshold: float) -> None:
        self._confidence_threshold = confidence_threshold

    # --- worker process I/O --------------------------------------------

    def _send(self, message: dict) -> None:
        if self._process is None or self._process.stdin is None:
            return
        try:
            self._process.stdin.write(json.dumps(message) + "\n")
            self._process.stdin.flush()
        except Exception as e:
            print(f"[WARN] Failed to send message to voice control worker: {e}")

    def _read_worker_output(self) -> None:
        """This module's own background thread - reads the worker's stdout
        until it closes (a clean stop, or the worker process dying), never
        touches Qt/a controller directly."""
        process = self._process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                continue
            event = message.get("event")
            if event == "ready":
                self._started_ok = True
                self._ready_event.set()
                if self._ready_callback is not None:
                    self._ready_callback(True)
            elif event == "error":
                print(f"[WARN] Voice control worker error: {message.get('message')}")
                self._started_ok = False
                self._ready_event.set()
                if self._ready_callback is not None:
                    self._ready_callback(False)
            elif event == "result":
                self._handle_final_result(message)
        # stdout closed - a clean stop() already sets _ready_event itself via
        # the "error"/"ready" path or was never waiting; but a worker that
        # CRASHED before ever reporting either must still be reported as a
        # failure, not leave the caller waiting forever.
        #
        # `process is self._process` guards the restart race S4's stop()
        # widened: stop() nulls self._process and a following start() has
        # already cleared _ready_event for the NEW worker, so a late EOF
        # from the OLD worker's pipe must not fire the ready callback here
        # and report the new worker as failed. On a deliberate stop the
        # same check simply skips this block (self._process is None), which
        # is correct - the controller reports the disconnect itself.
        if process is self._process and not self._ready_event.is_set():
            self._started_ok = False
            self._ready_event.set()
            if self._ready_callback is not None:
                self._ready_callback(False)

    def _handle_final_result(self, result: dict) -> None:
        """Drops anything below the configured confidence threshold,
        resolves the heard text against the fixed command vocabulary and the
        current score's go-to-bar phrases, and forwards only a real match to
        set_callback's callback - never touches Qt/a controller directly.
        Every attempt (accepted or not) also reaches set_diagnostic_
        callback's callback, for the practice/test dialog.

        Confidence is checked BEFORE parsing: a low-confidence result is
        rejected regardless of whether its text happens to match a real
        phrase, since a garbled recognition landing coincidentally on a real
        command's text is exactly the false-accept this feature exists to
        avoid."""
        heard_text = (result.get("text") or "").strip()
        if not heard_text or heard_text == UNKNOWN_TOKEN:
            if self._diagnostic_callback is not None:
                self._diagnostic_callback(heard_text or "(silence)", 0.0, False)
            return

        confidence = _confidence_percent(result)
        parsed = None
        if confidence >= self._confidence_threshold:
            parsed = voice_commands.parse_command(
                heard_text,
                voice_commands.go_to_bar_reverse_lookup(self._total_measures),
                voice_commands.loop_length_reverse_lookup(),
                voice_commands.attribute_reverse_lookup(),
            )
        accepted = parsed is not None

        if self._diagnostic_callback is not None:
            self._diagnostic_callback(heard_text, confidence, accepted)

        if not accepted:
            if confidence < self._confidence_threshold:
                # .1f, not .0f: two genuinely different values (e.g. 49.6 vs
                # 50.0) can both round to the same whole number, which read
                # as "50 < 50" - a real number rejected correctly, printed
                # as a message that looked like nonsense (reported live).
                print(
                    f"[INFO] Voice control: rejected '{heard_text}' "
                    f"(confidence {confidence:.1f} < threshold {self._confidence_threshold:.1f})"
                )
            else:
                print(f"[INFO] Voice control: recognized text did not match a known command: '{heard_text}'")
            return

        if self._callback is None:
            return
        command_name, number_value = parsed
        self._callback(command_name, confidence, number_value)
