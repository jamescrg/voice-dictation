# Voice Dictation

Push-to-talk voice dictation using Groq's Whisper API.

## Installation

```bash
git clone <repo-url> ~/.local/opt/voice-dictation
cd ~/.local/opt/voice-dictation
cp .env.example .env
# Edit .env and add your Groq API key from https://console.groq.com/keys
./install.sh
```

The installer sets up a systemd user service (starts on login), a `dictate` CLI command, and a desktop entry for your application menu.

## Controls

| Action | Key |
|--------|-----|
| Record | Hold **Pause** or **backtick** |
| Type backtick | Tap backtick |
| Undo last transcription | Double-tap backtick |

## CLI Usage

```
dictate              Show status, or start if not running
dictate start        Start the service
dictate stop         Stop the service
dictate restart      Restart the service
dictate status       Show service status
dictate log          Show recent logs
dictate follow       Follow logs in real time
```
