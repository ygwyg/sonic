# Sonic dashboard (frontend)

React 18 + TypeScript + Vite 5 + Tailwind CSS 3 + Recharts front end for the
Sonic OFDM acoustic data-transmission engine. It talks to the FastAPI backend in
`../backend` (package `sonic`) over `/api`.

## Run

```bash
# 1. backend (from ../backend)
python3 -m uvicorn sonic.api.app:app --port 8000

# 2. frontend (from this directory)
npm install
npm run dev          # http://localhost:5173 — /api (HTTP + WebSocket) is proxied to 127.0.0.1:8000
```

## Build

```bash
npm run typecheck    # tsc --noEmit
npm run build        # tsc --noEmit && vite build  → dist/
npm run preview      # serve dist/ locally
```

The backend serves `frontend/dist` at `/` automatically when the directory
exists (see `sonic/api/app.py`), so after `npm run build` the whole app is
available from the uvicorn port alone.

## Pages

| Route          | Page                 | What it does                                                                 |
| -------------- | -------------------- | ---------------------------------------------------------------------------- |
| `/transmitter` | Transmitter          | Text/file → OFDM WAV; live estimate; waveform, compression table, player, optional synthetic-channel decode; "Send to Explorer". |
| `/receiver`    | Receiver             | Upload WAV or record from the microphone → `/api/decode`; full diagnostics (sync, SNR per carrier, channel magnitude, constellation, timing drift, packets). |
| `/explorer`    | Waveform Explorer    | Envelope with frame sections, spectrum, spectrogram, carrier allocation, overlapping-carrier demo, FFT separation, constellations, power distribution. |
| `/benchmark`   | Benchmark Laboratory | Start experiments, follow them over WebSocket, chart the summary, export CSV/JSON; browse stored results and PNG plots. |
| `/qr`          | Audio QR Studio      | Friendly send/listen flow built on `/api/qr/encode` and `/api/qr/decode`. |

## Layout

```
src/
  services/   api.ts (typed client + response types), audio.ts (WAV, playback, recorder), format.ts
  state/      AppState.tsx (presets cache, last EncodeResponse shared with the Explorer)
  components/ Layout, Card, NumberStat, FileDrop, ConfigForm, ChannelForm, AudioPlayer, Recorder,
              ErrorBanner, DataTable, JsonView, DecodeReport, PageHeader
  charts/     EnvelopeChart, SpectrumChart, SpectrogramCanvas, CarrierAllocationChart,
              ConstellationScatter, LineSeriesChart, GroupedBarChart, theme.ts
  pages/      TransmitterPage, ReceiverPage, ExplorerPage, BenchmarkPage, QrStudioPage
public/       favicon.svg
```

## Notes

- Audio never autoplays; the volume slider defaults to 0.5 and is clamped to 1.0.
- Microphone access is requested only when a Start/Listen button is pressed. Raw
  Float32 PCM is captured with an AudioWorklet (ScriptProcessorNode fallback) and
  encoded client-side as 16-bit mono WAV at the AudioContext sample rate.
- Channel models in the UI are synthetic simulations, not acoustic measurements.
- Every number shown comes from an API response; missing values render as "—".
