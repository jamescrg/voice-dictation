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
ICON_ERROR = "mic-error"

indicator = None


def set_tray_status(icon_name):
    """Update the tray icon."""
    global indicator
    if indicator:
        GLib.idle_add(indicator.set_icon_full, icon_name, "Voice Dictation")


# Recording state
recording = False
typing_transcription = False  # True while xdotool is typing output
audio_queue = queue.Queue()
audio_data = []
device_error = threading.Event()  # Signals device disconnection/error


def audio_callback(indata, frames, time, status):
    """Callback for audio recording."""
    if status:
        # Device error detected (disconnection, overflow, etc.)
        print(f"Audio device error: {status}")
        device_error.set()
        return
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
    global typing_transcription
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
            # Type using xdotool (ignore synthetic key events during this)
            typing_transcription = True
            subprocess.run(["xdotool", "type", "--clearmodifiers", "--", text], check=True)
            typing_transcription = False

    except Exception as e:
        pass

    finally:
        typing_transcription = False
        os.unlink(temp_path)
        set_tray_status(ICON_IDLE)


HOTKEY = keyboard.Key.pause
BACKTICK_HOLD_THRESHOLD = 0.3  # seconds - hold longer than this to record
DOUBLE_TAP_THRESHOLD = 0.3  # seconds - tap twice within this to undo

# Backtick state
backtick_press_time = None
backtick_timer = None
last_backtick_tap_time = None

transcription_stack = []


def on_press(key):
    """Handle key press."""
    global recording, backtick_press_time, backtick_timer

    # Ignore synthetic key events from xdotool typing transcription
    if typing_transcription:
        return

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
    if transcription_stack:
        text = transcription_stack.pop()
        # Send backspaces to delete the text
        for _ in range(len(text)):
            subprocess.run(["xdotool", "key", "BackSpace"], check=True)


def on_release(key):
    """Handle key release."""
    global recording, backtick_press_time, backtick_timer, last_backtick_tap_time

    # Ignore synthetic key events from xdotool typing transcription
    if typing_transcription:
        return

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


def run_dictation():
    """Run the dictation logic with automatic device reconnection."""
    global recording
    RECONNECT_DELAY = 2.0  # seconds to wait before reconnecting

    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        while listener.running:
            device_error.clear()
            try:
                print("Opening audio device...")
                with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                                    callback=audio_callback, dtype=np.float32):
                    print("Audio device ready")
                    set_tray_status(ICON_IDLE)
                    # Wait for device error or listener to stop
                    while listener.running and not device_error.is_set():
                        device_error.wait(timeout=0.5)

                    if device_error.is_set():
                        print("Device error detected, will reconnect...")
                        # Reset recording state
                        recording = False
                        # Clear any stale audio data
                        while not audio_queue.empty():
                            audio_queue.get()
            except sd.PortAudioError as e:
                print(f"Audio device error: {e}")
            except Exception as e:
                print(f"Unexpected audio error: {e}")

            # If we get here, either device errored or listener stopped
            if listener.running:
                set_tray_status(ICON_ERROR)
                print(f"Reconnecting in {RECONNECT_DELAY} seconds...")
                time.sleep(RECONNECT_DELAY)


def on_reload(source):
    """Reload the application."""
    Gtk.main_quit()
    os.execv(sys.executable, [sys.executable] + sys.argv)


def on_quit(source):
    """Quit the application."""
    Gtk.main_quit()


def main():
    global indicator

    print(f"Voice dictation ready!")
    print(f"Hold Pause or backtick (`) to record")
    print(f"Tap backtick = types the character")
    print(f"Double-tap backtick = undo last transcription")
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
    reload_item = Gtk.MenuItem(label="Reload")
    reload_item.connect("activate", on_reload)
    menu.append(reload_item)
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
