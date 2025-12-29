#!/usr/bin/env python3
"""
Voice dictation using Groq's Whisper API.
Hold the hotkey to record, release to transcribe and type.
"""

import subprocess
import tempfile
import threading
import queue
import os
import sys
import time
from pathlib import Path

# Load .env file
def load_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())

load_env()

try:
    import numpy as np
    import sounddevice as sd
    from groq import Groq
    from pynput import keyboard
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: ./install.sh")
    sys.exit(1)

if not os.environ.get("GROQ_API_KEY"):
    print("Error: GROQ_API_KEY not set")
    print("Copy .env.example to .env and add your API key")
    sys.exit(1)

# Configuration
SAMPLE_RATE = 16000
CHANNELS = 1

# Initialize Groq client
client = Groq()

# Recording state
recording = False
audio_queue = queue.Queue()
audio_data = []


def audio_callback(indata, frames, time, status):
    """Callback for audio recording."""
    if recording:
        audio_queue.put(indata.copy())


def start_recording():
    """Start recording audio."""
    global recording, audio_data
    audio_data = []
    recording = True
    print("Recording... (release key to stop)")


def stop_recording():
    """Stop recording and process audio."""
    global recording
    recording = False

    # Collect all audio data from queue
    while not audio_queue.empty():
        audio_data.append(audio_queue.get())

    if not audio_data:
        print("No audio recorded")
        return

    # Combine audio chunks
    audio = np.concatenate(audio_data)

    print("Transcribing...")
    transcribe_and_type(audio)


def transcribe_and_type(audio: np.ndarray):
    """Send audio to Groq and type the result."""
    # Save to temporary WAV file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_path = f.name
        import wave
        with wave.open(f.name, 'wb') as wav:
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes((audio * 32767).astype(np.int16).tobytes())

    try:
        # Send to Groq
        with open(temp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file,
                language="en",
            )

        text = transcription.text.strip()
        if text:
            global last_transcription
            last_transcription = text
            print(f"Transcribed: {text}")
            # Type using xdotool
            subprocess.run(["xdotool", "type", "--clearmodifiers", "--", text], check=True)
        else:
            print("No speech detected")

    except Exception as e:
        print(f"Error: {e}")

    finally:
        os.unlink(temp_path)


HOTKEY = keyboard.Key.pause
BACKTICK_HOLD_THRESHOLD = 0.3  # seconds - hold longer than this to record
DOUBLE_TAP_THRESHOLD = 0.3  # seconds - tap twice within this to undo

# Backtick state
backtick_press_time = None
backtick_timer = None
last_backtick_tap_time = None
last_transcription = None


def on_press(key):
    """Handle key press."""
    global recording, backtick_press_time, backtick_timer

    # Pause key - immediate recording
    if key == HOTKEY and not recording:
        start_recording()
        return

    # Backtick - start timer for hold detection
    if getattr(key, 'char', None) == '`' and not recording:
        backtick_press_time = time.time()
        # Start a timer to begin recording after threshold
        backtick_timer = threading.Timer(BACKTICK_HOLD_THRESHOLD, start_recording_from_backtick)
        backtick_timer.start()


def start_recording_from_backtick():
    """Called when backtick is held long enough."""
    global backtick_press_time
    if backtick_press_time is not None:
        # Delete the backtick that was typed
        subprocess.run(["xdotool", "key", "BackSpace"], check=True)
        start_recording()


def undo_last_transcription():
    """Delete the last transcription by sending backspaces."""
    global last_transcription
    if last_transcription:
        print(f"Undoing: {last_transcription}")
        # Send backspaces to delete the text
        for _ in range(len(last_transcription)):
            subprocess.run(["xdotool", "key", "BackSpace"], check=True)
        last_transcription = None
    else:
        print("Nothing to undo")


def on_release(key):
    """Handle key release."""
    global recording, backtick_press_time, backtick_timer, last_backtick_tap_time

    # Pause key release
    if key == HOTKEY and recording:
        stop_recording()
        return

    # Backtick release
    if getattr(key, 'char', None) == '`':
        # Cancel the timer if still running
        if backtick_timer is not None:
            backtick_timer.cancel()
            backtick_timer = None

        if backtick_press_time is not None:
            held_duration = time.time() - backtick_press_time
            backtick_press_time = None

            if recording:
                # Was held long enough, stop recording
                stop_recording()
            elif held_duration < BACKTICK_HOLD_THRESHOLD:
                # Quick tap - check for double-tap
                now = time.time()
                if last_backtick_tap_time and (now - last_backtick_tap_time) < DOUBLE_TAP_THRESHOLD:
                    # Double-tap detected - delete both backticks and undo
                    subprocess.run(["xdotool", "key", "BackSpace", "BackSpace"], check=True)
                    undo_last_transcription()
                    last_backtick_tap_time = None
                else:
                    # Single tap - record time for potential double-tap
                    last_backtick_tap_time = now


def main():
    print(f"Voice dictation ready!")
    print(f"Hold Pause or backtick (`) to record, release to transcribe")
    print(f"Tap backtick = types backtick")
    print(f"Double-tap backtick = undo last transcription")
    print("Press Ctrl+C to exit")
    print("-" * 40)

    # Start audio stream
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                        callback=audio_callback, dtype=np.float32):
        # Start keyboard listener
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()


if __name__ == "__main__":
    main()
