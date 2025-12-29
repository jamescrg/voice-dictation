# Voice Dictation

Push-to-talk voice dictation using Groq's Whisper API.

## Installation

```bash
./install.sh
cp .env.example .env
# Edit .env and add your Groq API key from https://console.groq.com/keys
```

## Usage

```bash
./start-dictate.sh
```

## Controls

| Action | Key |
|--------|-----|
| Record | Hold **Pause** or **backtick** |
| Type backtick | Tap backtick |
| Undo last transcription | Double-tap backtick |

## Systemd Service (Optional)

To run on login:

```bash
mkdir -p ~/.config/systemd/user
cp dictate.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable dictate
systemctl --user start dictate
```
