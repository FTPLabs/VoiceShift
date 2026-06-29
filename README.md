# VoiceShift

Lightweight real-time voice changer. Single portable `.exe`, runs in system tray, zero installer.

## Features

- **Pitch shift** ±12 semitones
- **Formant shift** (gender / size feel)
- **Robotic / vocoder** effect
- **Noise gate** — silence background hiss
- **Per-app bypass** — e.g. disable voice change in Discord
- **Presets** — save / switch profiles instantly
- **Autostart** — Windows registry integration
- **System tray** — invisible, always running

## Requirements

| Item | Notes |
|------|-------|
| Windows 10 / 11 x64 | Required |
| [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) | **Free** — lets other apps receive your processed voice |

> VB-Cable creates a virtual microphone. Set **VoiceShift Output → CABLE Input** and in Discord/game set microphone to **CABLE Output**.

## Quick Start

1. Install VB-Audio Virtual Cable (one-time, free)
2. Download `VoiceShift.exe` from [Releases](../../releases)
3. Run it — icon appears in system tray
4. Set **Input** = your real microphone, **Output** = CABLE Input (VB-Audio)
5. Adjust sliders, save a preset
6. Enable **Autostart** so it runs on boot

## Per-App Bypass

In each preset's **"Bypass for apps"** field, add process names separated by commas:

```
discord.exe, chrome.exe, spotify.exe
```

When that process is in the foreground, VoiceShift mutes the modified output and passes audio through normally.

## Building from Source

```bash
git clone <your-repo>
cd voice-changer
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python src/main.py
```

### Build .exe locally

```bash
pip install pyinstaller==6.9.0
pyinstaller VoiceShift.spec --noconfirm --clean
# Output: dist/VoiceShift.exe
```

### Automated release via GitHub Actions

Push a tag to trigger a full build + GitHub Release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The workflow (`.github/workflows/build.yml`) runs on Windows, builds the `.exe`, and attaches it to the release automatically.

## Architecture

```
src/
  main.py          — entry point, Qt app bootstrap
  audio_engine.py  — WASAPI capture → DSP → virtual output
  gui.py           — PyQt6 tray UI (320px compact panel)
  config.py        — JSON config + preset management
  app_monitor.py   — foreground window poller for per-app rules
```

## Memory Footprint

| State | Approx. RAM |
|-------|------------|
| Idle (tray) | ~35 MB |
| Processing audio | ~45 MB |

Optimised for Windows WASAPI (lowest-latency audio path).
