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
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import Gtk, AyatanaAppIndicator3 as AppIndicator3, GLib
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

# Custom icon paths
SCRIPT_DIR = Path(__file__).parent
ICON_DIR = str(SCRIPT_DIR / "icons")
ICON_IDLE = "mic-idle"
ICON_RECORDING = "mic-recording"
ICON_TRANSCRIBING = "mic-transcribing"

indicator = None


def set_tray_status(icon_name):
    """Update the tray icon."""
    global indicator
    if indicator:
        GLib.idle_add(indicator.set_icon_full, icon_name, "Voice Dictation")


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
    set_tray_status(ICON_RECORDING)


def stop_recording():
    """Stop recording and process audio."""
    global recording
    recording = False

    # Collect all audio data from queue
    while not audio_queue.empty():
        audio_data.append(audio_queue.get())

    if not audio_data:
        set_tray_status(ICON_IDLE)
        return

    # Combine audio chunks
    audio = np.concatenate(audio_data)
    set_tray_status(ICON_TRANSCRIBING)
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
            )

        text = transcription.text.strip()
        if text:
            text += " "  # Add trailing space
            transcription_stack.append(text)
            # Type using xdotool
            subprocess.run(["xdotool", "type", "--clearmodifiers", "--", text], check=True)

    except Exception as e:
        pass

    finally:
        os.unlink(temp_path)
        set_tray_status(ICON_IDLE)


HOTKEY = keyboard.Key.pause
BACKTICK_HOLD_THRESHOLD = 0.3  # seconds - hold longer than this to record
DOUBLE_TAP_THRESHOLD = 0.3  # seconds - tap twice within this to undo

# Backtick state
backtick_press_time = None
backtick_timer = None
last_backtick_tap_time = None

# Apostrophe state
apostrophe_press_time = None
apostrophe_timer = None
last_apostrophe_tap_time = None

transcription_stack = []


def on_press(key):
    """Handle key press."""
    global recording, backtick_press_time, backtick_timer
    global apostrophe_press_time, apostrophe_timer

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

    # Apostrophe - start timer for hold detection
    if getattr(key, 'char', None) == "'" and not recording:
        apostrophe_press_time = time.time()
        # Start a timer to begin recording after threshold
        apostrophe_timer = threading.Timer(BACKTICK_HOLD_THRESHOLD, start_recording_from_apostrophe)
        apostrophe_timer.start()


def start_recording_from_backtick():
    """Called when backtick is held long enough."""
    global backtick_press_time
    if backtick_press_time is not None:
        # Delete the backtick that was typed
        subprocess.run(["xdotool", "key", "BackSpace"], check=True)
        start_recording()


def start_recording_from_apostrophe():
    """Called when apostrophe is held long enough."""
    global apostrophe_press_time
    if apostrophe_press_time is not None:
        # Delete the apostrophe that was typed
        subprocess.run(["xdotool", "key", "BackSpace"], check=True)
        start_recording()


def undo_last_transcription():
    """Delete the last transcription by sending backspaces."""
    if transcription_stack:
        text = transcription_stack.pop()
        # Send backspaces to delete the text
        for _ in range(len(text)):
            subprocess.run(["xdotool", "key", "BackSpace"], check=True)


def on_release(key):
    """Handle key release."""
    global recording, backtick_press_time, backtick_timer, last_backtick_tap_time
    global apostrophe_press_time, apostrophe_timer, last_apostrophe_tap_time

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

    # Apostrophe release
    if getattr(key, 'char', None) == "'":
        # Cancel the timer if still running
        if apostrophe_timer is not None:
            apostrophe_timer.cancel()
            apostrophe_timer = None

        if apostrophe_press_time is not None:
            held_duration = time.time() - apostrophe_press_time
            apostrophe_press_time = None

            if recording:
                # Was held long enough, stop recording
                stop_recording()
            elif held_duration < BACKTICK_HOLD_THRESHOLD:
                # Quick tap - check for double-tap
                now = time.time()
                if last_apostrophe_tap_time and (now - last_apostrophe_tap_time) < DOUBLE_TAP_THRESHOLD:
                    # Double-tap detected - delete both apostrophes and undo
                    subprocess.run(["xdotool", "key", "BackSpace", "BackSpace"], check=True)
                    undo_last_transcription()
                    last_apostrophe_tap_time = None
                else:
                    # Single tap - record time for potential double-tap
                    last_apostrophe_tap_time = now


def run_dictation():
    """Run the dictation logic."""
    # Start audio stream
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                        callback=audio_callback, dtype=np.float32):
        # Start keyboard listener
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()


def on_quit(source):
    """Quit the application."""
    Gtk.main_quit()


def main():
    global indicator

    print(f"Voice dictation ready!")
    print(f"Hold Pause, backtick (`), or apostrophe (') to record")
    print(f"Tap backtick/apostrophe = types the character")
    print(f"Double-tap backtick/apostrophe = undo last transcription")
    print("Press Ctrl+C to exit")
    print("-" * 40)

    # Create AppIndicator with custom icon path
    indicator = AppIndicator3.Indicator.new(
        "voice-dictation",
        ICON_IDLE,
        AppIndicator3.IndicatorCategory.APPLICATION_STATUS
    )
    indicator.set_icon_theme_path(ICON_DIR)
    indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

    # Create menu
    menu = Gtk.Menu()
    quit_item = Gtk.MenuItem(label="Quit")
    quit_item.connect("activate", on_quit)
    menu.append(quit_item)
    menu.show_all()
    indicator.set_menu(menu)

    # Run dictation in a separate thread
    dictation_thread = threading.Thread(target=run_dictation, daemon=True)
    dictation_thread.start()

    # Run GTK main loop
    Gtk.main()


if __name__ == "__main__":
    main()
