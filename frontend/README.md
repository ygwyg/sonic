# Sonic web app (frontend)

React 18 + TypeScript + Vite. One page with two actions, Send and Receive,
talking to the FastAPI backend in `../backend` over `/api`. No CSS framework
or chart library: styles are plain CSS (`src/index.css`) and the two figures
are hand-drawn SVG.

## Run

```bash
# 1. backend (from ../backend)
sonic serve --port 8000

# 2. frontend (from this directory)
npm install
npm run dev                  # http://localhost:5173, proxies /api (HTTP + WebSocket) to :8000
SONIC_LAN=1 npm run dev      # https on all interfaces, so a phone on the same Wi-Fi can use its mic
```

Open `/#receive` to land directly on the Receive tab (handy on a phone).

## Build

```bash
npm run build                # tsc --noEmit && vite build → dist/
```

The backend serves `frontend/dist` at `/` when the directory exists, so
after a build the whole app runs from the uvicorn port alone.

## How it works

- **Send** encodes with `/api/encode` (text) or `/api/encode/file` and plays
  the WAV through Web Audio. Speeds map to presets: Fast = default band with
  16-QAM 1/2, Balanced = `default`, Reliable = `robust`.
- **Receive** opens a WebSocket to `/api/listen`, sends the sample rate, then
  streams the microphone as 16-bit PCM frames (AudioWorklet, echo
  cancellation / noise suppression / auto gain off). The server answers with
  `listening`, `receiving` (with progress), `received` or `failed` events and
  stops after one successful transmission.
- **Trace** (`components/Trace.tsx`) reads a shared AnalyserNode, so the same
  line shows outgoing and incoming sound.

## Layout

```
src/
  App.tsx                  page: hero, trace, send/receive, how it works, measurements
  lib/        api.ts (client + types), audio.ts (context, playback, mic stream), format.ts
  components/ SendPanel, ReceivePanel, ModePicker, Result, Figures, Trace
```
