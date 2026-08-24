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
plus the current score's go_to_bar_phrases, plus Vosk's own recommended
"[unk]" catch-all) sent to the worker, which passes it straight into
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
result. Stopping sends the worker a {"cmd": "stop"} line and waits for it to
exit; if the parent process ever dies without a clean stop, the worker's own
stdin-closed detection (see voice_recognition_worker.py) makes it exit too,
so a crash can't leave it orphaned.

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

VOSK_AVAILABLE = (
    importlib.util.find_spec("vosk") is not None
    and importlib.util.find_spec("sounddevice") is not None
)

# The model this feature was built and tested against (vosk-model-small-en-
# us-0.15, ~40MB, Apache-2.0) - not pip-installable, not tracked in git (see
# .gitignore's own comment). A different/larger model can be dropped in at
# this same path with no code change; Vosk's own grammar-constraint feature
# (see _build_grammar_phrases) means the small model's narrower general
# vocabulary matters far less here than it would for open dictation.
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vosk_model")

WORKER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice_recognition_worker.py")

# Vosk's own recommended catch-all - documented as letting the decoder say
# "none of these phrases" instead of forcing the nearest wrong match.
# GOTCHA, found via live testing on vosk-model-small-en-us-0.15: including
# "[unk]" in the grammar list passed to KaldiRecognizer breaks finalization
# completely - every result comes back as empty text, even for a clearly
# spoken, otherwise-correctly-recognized command (confirmed by isolating a
# grammar of just ["stop"] vs ["stop", "[unk]"] against the same speech: the
# first recognizes "stop" at high confidence, the second returns nothing at
# all, reproducibly). NOT included in _build_grammar_phrases below because
# of this - the confidence threshold is this feature's only false-accept
# safeguard here, not a grammar-level catch-all. UNKNOWN_TOKEN itself is
# still checked for in _handle_final_result as a defensive no-op (in case a
# future/different model ever does emit it), it's just never offered to the
# decoder as a real option.
UNKNOWN_TOKEN = "[unk]"

# (command_name, confidence_percent 0-100, measure_number) - the normalised
# shape this module hands to its callback, mirroring audio/midi_input.py's
# own "(status, pitch, velocity)" normalised-tuple convention. measure_number
# is only meaningful (non-None) for voice_commands.GO_TO_BAR.
RecognitionCallback = Callable[[str, float, Optional[int]], None]


def list_input_devices() -> List[str]:
    """Fresh enumeration every call - never cached, mirroring
    audio/midi_input.py's list_input_ports(). Returns [] (never raises) if
    vosk/sounddevice aren't importable or enumeration fails - the "warn and
    no-op" handling this app gives every optional resource. Runs the worker
    script in a one-shot --list-devices mode rather than importing
    sounddevice directly here - see module docstring on why this process
    must never import it."""
    if not VOSK_AVAILABLE:
        return []
    try:
        result = subprocess.run(
            [sys.executable, WORKER_SCRIPT, "--list-devices"],
            capture_output=True, text=True, timeout=10,
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
    "go to measure N" phrases - the phrase list sent to the worker to
    restrict Vosk's recognition to just this vocabulary. Deliberately does
    NOT include UNKNOWN_TOKEN - see that constant's own comment on why.
    Sent wholesale (never incrementally patched) whenever the vocabulary
    needs to change - cheap for Vosk (a fresh KaldiRecognizer), unlike the
    SAPI version's file-round-trip workaround."""
    phrases = list(voice_commands.COMMAND_PHRASES.keys())
    phrases.extend(phrase for phrase, _ in voice_commands.go_to_bar_phrases(total_measures))
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

    def list_devices(self) -> List[str]:
        """Instance wrapper around the module-level list_input_devices(), so
        a test can override per-instance (a NullVoiceRecognizer) without
        monkeypatching the module function - mirrors MidiInputManager.
        list_ports()."""
        return list_input_devices()

    def start(self, device_name: Optional[str], confidence_threshold: float) -> bool:
        """Starts the worker child process and its stdout-reader thread.
        Returns False (never raises) if vosk/sounddevice aren't available,
        the model directory is missing, or the process fails to start - the
        "degrade silently" behaviour every other optional resource in this
        app already has."""
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
                [sys.executable, "-u", WORKER_SCRIPT],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, bufsize=1,
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
        self._ready_event.wait(timeout=10.0)
        return self._started_ok

    def stop(self) -> None:
        if self._process is None:
            return
        self._send({"cmd": "stop"})
        try:
            self._process.wait(timeout=3.0)
        except Exception:
            self._process.kill()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=3.0)
        self._process = None
        self._reader_thread = None

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
            elif event == "error":
                print(f"[WARN] Voice control worker error: {message.get('message')}")
                self._started_ok = False
                self._ready_event.set()
            elif event == "result":
                self._handle_final_result(message)

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
                heard_text, voice_commands.go_to_bar_reverse_lookup(self._total_measures)
            )
        accepted = parsed is not None

        if self._diagnostic_callback is not None:
            self._diagnostic_callback(heard_text, confidence, accepted)

        if not accepted:
            if confidence < self._confidence_threshold:
                print(
                    f"[INFO] Voice control: rejected '{heard_text}' "
                    f"(confidence {confidence:.0f} < threshold {self._confidence_threshold:.0f})"
                )
            else:
                print(f"[INFO] Voice control: recognized text did not match a known command: '{heard_text}'")
            return

        if self._callback is None:
            return
        command_name, measure_number = parsed
        self._callback(command_name, confidence, measure_number)
