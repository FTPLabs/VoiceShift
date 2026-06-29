# VoiceShift

Real-time voice processing — browser-based audio processor. No install required, works in any modern browser.

## Features

- **Pitch Shift** — ±12 semitones
- **Formant Shift** — gender / size feel (0.5× to 2.0×)
- **Robotic / Comb Effect** — 0–100%
- **Noise Gate** — hard silence gate (-80 to -10 dB)
- **High-Pass Filter** — remove low-freq rumble (20–500 Hz)
- **Low-Pass Filter** — remove high-freq hiss (2000–20000 Hz)
- **Dynamics Compressor** — threshold and ratio control
- **Output Gain** — 0–200%
- **Real-time VU Meters** — input and output levels
- **Frequency Spectrum Analyzer** — live canvas visualization
- **Self-monitoring** — hear your processed voice through headphones
- **Preset Management** — save, load, delete named presets (synced to server)
- **Device Selection** — choose any connected microphone

## Quick Start (Web App)

1. Open the app in your browser
2. Allow microphone access when prompted
3. Press **START** to begin processing
4. Adjust sliders to taste — changes apply in real time
5. Save your settings as a preset for later

## Architecture

```
Browser (Web Audio API)
  getUserMedia() → AudioContext
    → GainNode (noise gate)
    → AnalyserNode (input VU)
    → BiquadFilter (highpass)
    → BiquadFilter (lowpass)
    → DynamicsCompressor
    → DryGain + DelayNode→DelayGain (robotic comb)
    → OutputGain
    → AnalyserNode (output VU + spectrum)
    → MediaStreamDestination (self-monitor)

Server (Express + PostgreSQL)
  GET    /api/presets       — list all presets
  POST   /api/presets       — create preset
  GET    /api/presets/:id   — get preset
  PATCH  /api/presets/:id   — update preset
  DELETE /api/presets/:id   — delete preset
```

## Stack

- Frontend: React 19 + Vite 7 + TypeScript + Tailwind CSS + shadcn/ui
- Audio: Web Audio API (BiquadFilterNode, DynamicsCompressorNode, AnalyserNode, GainNode, DelayNode)
- Backend: Node.js + Express 5
- Database: PostgreSQL + Drizzle ORM
- Validation: Zod v4 + Orval codegen from OpenAPI spec

## Default Presets

| Preset | Pitch | Formant | Robotic | Gate |
|--------|-------|---------|---------|------|
| Default | 0 st | 1.0× | 0% | -50 dB |
| Deep Voice | -4 st | 0.85× | 0% | -45 dB |
| High Voice | +5 st | 1.20× | 0% | -50 dB |
| Robot | +2 st | 1.0× | 70% | -50 dB |

## Memory / CPU

All processing runs in the browser audio thread. CPU usage is minimal (< 1% on a modern machine). No audio is sent to the server — only preset configurations are stored.

## Source Layout

```
artifacts/voiceshift/src/
  audio/VoiceProcessor.ts     — Web Audio API engine
  pages/VoiceShiftApp.tsx     — main app page
  components/
    VUMeter.tsx               — real-time level bar
    SpectrumAnalyzer.tsx      — canvas frequency display
    ParamSlider.tsx           — labeled slider control
    PresetPanel.tsx           — preset management UI

artifacts/api-server/src/
  routes/presets.ts           — CRUD REST API

lib/
  api-spec/openapi.yaml       — OpenAPI contract
  db/src/schema/presets.ts    — Drizzle schema
  api-client-react/           — generated React Query hooks
  api-zod/                    — generated Zod validators
```
