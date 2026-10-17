# Sonic

Send text and files through sound. Play it on one device, listen on another,
and the data arrives byte-for-byte or not at all.

- **Send:** type a message or drop a file, press Play.
- **Receive:** press Listen. It picks up the transmission and decodes it on its own.
- **Explore:** see the sound itself: waveform, spectrum, spectrogram, the tones and how they separate.
- Every transfer is checked against a SHA-256 fingerprint.
- Works across a desk (tested laptop → phone at half a metre). Not yet across a room.

## Run it

Requires Python 3.12+ and Node 20+.

```bash
cd backend && pip install -e ".[all]" && sonic serve       # backend on :8000
cd frontend && npm install && npm run dev                  # app on http://localhost:5173
```

To receive on a phone on the same Wi-Fi, start the app with `SONIC_LAN=1 npm run dev`
and open `https://<your-computer's-ip>:5173/#receive` on the phone. Phones only allow
the microphone over HTTPS, so accept the self-signed certificate warning.

There is also a command line:

```bash
sonic encode notes.txt -o notes.wav     # file → sound
sonic decode notes.wav -o notes.txt     # sound → file
sonic play notes.wav                    # through the speakers
sonic record --seconds 10 -o rec.wav    # from the microphone
```

---

## How it works

```
data → compress → packets + checksums → error correction → tones → speaker
mic → find the start → separate the tones → correct errors → verify SHA-256 → data
```

1. **Pack.** The data is compressed, split into packets with a CRC-32 each, and
   protected with a convolutional error-correcting code.
2. **Play.** The bits are spread over hundreds of tones sounding at once between
   2 and 10 kHz (OFDM, the technique Wi-Fi uses on radio). Each tone carries a few
   bits per symbol (BPSK to 256-QAM). A short chirp marks the start, and a fixed,
   extra-robust header describes the rest.
3. **Rebuild.** The receiver finds the chirp, measures how the room and devices
   changed each tone, undoes it, corrects errors, and checks every packet and the
   final SHA-256. Anything that doesn't match is rejected.

### Speeds

| Speed | Encoding | Use it for |
|---|---|---|
| Fast | 16-QAM | Devices a hand's width apart |
| Balanced | QPSK | About half a metre (tested laptop → phone) |
| Reliable | BPSK, long symbols | Echoey rooms; slowest |

### What we measured

One MacBook Pro and one phone in an ordinary room:

| Setup | Result | Signal quality |
|---|---|---|
| Laptop speaker → its own mic | Received, even at 64-QAM | 36 dB |
| Laptop → phone, 0.5 m | Received | 21.5 dB |
| Laptop → phone, 2 m | Not received | 3 dB after room echoes |

At a distance, reflections off the walls arrive later than each symbol can absorb
and blur into the next one. Louder doesn't help. That's the main thing to solve next.

### Limits

- Audio carries only a few kilobits per second, so this suits messages, links and
  small files, not photos.
- Decoding runs in the Python backend, so the receiving page needs a connection to it.
- Low-bitrate voice codecs (e.g. a 32 kbit/s voice note) destroy the signal; MP3
  and AAC survive.
- No encryption: anyone in earshot can receive.

### More detail

- `docs/protocol.md`: frame format, header, packets
- `docs/architecture.md`: code layout
- `docs/research_log.md`: every experiment and measurement, including the failures
- `docs/limitations.md`: known limits

```
backend/    Python engine, CLI, API and tests (cd backend && pytest)
frontend/   web app
docs/       protocol, architecture, research log
```
