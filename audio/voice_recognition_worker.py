# audio/voice_recognition_worker.py
"""Hands-free voice control (Ref 19): the actual Vosk + sounddevice worker,
run as a SEPARATE PROCESS from the main app - see audio/voice_recognition.py's
own module docstring for why. Confirmed by direct testing: vosk and the
vendored FluidSynth binaries (bin/) bundle mutually incompatible copies of
the same-named MinGW runtime DLLs (libstdc++-6.dll, libwinpthread-1.dll).
Windows resolves a same-named dependency to whichever copy loaded into the
process first, process-wide, with no way to isolate the two - reproduced
both ways (FluidSynth first breaks vosk; vosk first breaks FluidSynth; even
explicitly pre-loading vosk's own copies first still breaks FluidSynth).
Running Vosk in its own process is the only real fix: separate processes
get separate, independent sets of loaded DLLs.

Deliberately standalone: imports nothing from this project except the
stdlib (plus vosk/sounddevice once actually starting) - never PySide6, never
audio.synth_engine - so launching this process can never itself re-trigger
the collision it exists to avoid, and starts fast.

Protocol: newline-delimited JSON on stdin/stdout.
  Parent -> worker (stdin):
    {"cmd": "start", "device_name": str|null, "grammar": [str, ...], "model_dir": str}
    {"cmd": "rebuild_grammar", "grammar": [str, ...]}
    {"cmd": "stop"}
  Worker -> parent (stdout):
    {"event": "ready"}
    {"event": "error", "message": str}
    {"event": "result", "text": str, "words": [{"word": str, "conf": float}, ...]}

The worker never applies a confidence threshold or resolves text against the
command vocabulary itself - every final recognition result is reported
as-is. audio/voice_recognition.py's VoiceRecognitionManager (in the parent
process) does all of that, so there is only one copy of that logic to keep
correct, not two.

--list-devices: a one-shot mode - prints a JSON array of input device names
to stdout and exits, so VoiceRecognitionManager.list_input_devices() never
has to import sounddevice into the main app process either.
"""
import json
import queue
import sys
import threading

SAMPLE_RATE = 16000  # what vosk-model-small-en-us-0.15 (and Vosk models
# generally) are trained on - confirm against a different model's own
# metadata if one is ever substituted.
BLOCK_SIZE = 8000  # 0.5s of audio per callback at 16kHz mono int16 - small
# enough for responsive silence/end-of-utterance detection, large enough not
# to busy-loop the queue.


def _emit(message: dict) -> None:
    print(json.dumps(message), flush=True)


def list_devices() -> None:
    import sounddevice
    names = [d["name"] for d in sounddevice.query_devices() if d.get("max_input_channels", 0) > 0]
    print(json.dumps(names), flush=True)


def _find_device_index(sounddevice_module, device_name: str):
    for index, d in enumerate(sounddevice_module.query_devices()):
        if d.get("max_input_channels", 0) > 0 and d["name"] == device_name:
            return index
    return None


def run() -> None:
    first_line = sys.stdin.readline()
    if not first_line:
        return
    try:
        start_command = json.loads(first_line)
    except ValueError:
        return
    if start_command.get("cmd") != "start":
        return

    model_dir = start_command.get("model_dir")
    device_name = start_command.get("device_name")
    grammar = start_command.get("grammar") or []

    try:
        import sounddevice
        import vosk
    except Exception as e:
        _emit({"event": "error", "message": f"vosk/sounddevice import failed: {e}"})
        return

    vosk.SetLogLevel(-1)  # Vosk is very chatty on stdout/stderr by default
    try:
        model = vosk.Model(model_dir)
    except Exception as e:
        _emit({"event": "error", "message": f"failed to load model at {model_dir}: {e}"})
        return

    recognizer_lock = threading.Lock()
    recognizer = vosk.KaldiRecognizer(model, SAMPLE_RATE, json.dumps(grammar))
    recognizer.SetWords(True)

    device_index = None
    if device_name:
        device_index = _find_device_index(sounddevice, device_name)
        if device_index is None:
            _emit({"event": "error", "message": f"input device not found: {device_name}"})
            return

    audio_queue: "queue.Queue" = queue.Queue()

    def on_audio_block(indata, frames, time_info, status):
        """sounddevice's OWN internal audio thread (PortAudio) - does
        nothing but enqueue, a callback must never block/do real work."""
        audio_queue.put(bytes(indata))

    try:
        stream = sounddevice.RawInputStream(
            samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE, dtype="int16",
            channels=1, device=device_index, callback=on_audio_block,
        )
        stream.start()
    except Exception as e:
        _emit({"event": "error", "message": f"failed to open microphone: {e}"})
        return

    stop_event = threading.Event()

    def read_stdin_commands():
        """Runs until stdin closes (the parent process going away, e.g. a
        crash, ends this loop too - not just an explicit "stop") or an
        explicit stop command arrives. Either way, stop_event.set()
        afterward ensures the main loop below always exits and this worker
        never becomes orphaned."""
        nonlocal recognizer
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                command = json.loads(line)
            except ValueError:
                continue
            cmd = command.get("cmd")
            if cmd == "stop":
                break
            elif cmd == "rebuild_grammar":
                new_grammar = command.get("grammar") or []
                with recognizer_lock:
                    recognizer = vosk.KaldiRecognizer(model, SAMPLE_RATE, json.dumps(new_grammar))
                    recognizer.SetWords(True)
        stop_event.set()

    stdin_thread = threading.Thread(target=read_stdin_commands, daemon=True)
    stdin_thread.start()

    _emit({"event": "ready"})

    while not stop_event.is_set():
        try:
            data = audio_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        with recognizer_lock:
            current_recognizer = recognizer
        if current_recognizer.AcceptWaveform(data):
            try:
                result = json.loads(current_recognizer.Result())
            except ValueError:
                continue
            _emit({
                "event": "result",
                "text": result.get("text", ""),
                "words": result.get("result", []),
            })
        # Partial results (current_recognizer.PartialResult()) are
        # deliberately never read here - only a completed utterance is ever
        # reported, matching the SAPI attempt's own "act only on a final
        # result, never a hypothesis" choice.

    stream.stop()
    stream.close()


if __name__ == "__main__":
    if "--list-devices" in sys.argv:
        list_devices()
    else:
        run()
