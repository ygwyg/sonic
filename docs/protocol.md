# Sonic transmission protocol (version 1)

This document specifies the on-air format. Byte order is **big-endian**
throughout. All sizes are in bytes unless stated otherwise.

## 1. Frame layout in time

```
| chirp | guard | header training | header data (2 copies) | payload training | payload data | tail guard |
```

| section          | duration (48 kHz)            | configuration                              |
|------------------|------------------------------|--------------------------------------------|
| chirp            | 100 ms, 1 → 7 kHz linear, Tukey window | fixed (`sonic.config.PREAMBLE_*`)  |
| guard            | 20 ms silence                | fixed                                      |
| header training  | 2 × 5120 samples             | fixed header config (`header_config()`)    |
| header data      | 2 copies × 4 symbols         | fixed header config                        |
| payload training | `n_training` symbols         | from header                                |
| payload data     | ⌈coded bits / bits per symbol⌉ symbols | from header                      |
| tail guard       | 20 ms silence                | fixed                                      |

The **fixed header configuration** is: `n_fft = 4096`, `cp_len = 1024`,
band 1000–7000 Hz, pilot spacing 8, BPSK, convolutional rate 1/2, two
training symbols. It depends only on the sample rate, which the receiver
knows from the WAV container or its capture device. Therefore the receiver
never needs information *from* the header in order to *read* the header.
The header is transmitted twice and the two copies' soft bits are summed
before Viterbi decoding (≈3 dB extra margin; a burst that destroys one copy
does not destroy the other).

## 2. Header (111 bytes, CRC-32 protected)

| offset | size | field                              | validation                                  |
|-------:|-----:|------------------------------------|---------------------------------------------|
| 0      | 4    | magic `SNC1`                        | must match                                  |
| 4      | 1    | protocol version                   | must be 1                                   |
| 5      | 4    | transmission id (random uint32)    | —                                           |
| 9      | 1    | payload type                       | 0 binary, 1 text, 2 json, 3 url, 4 contact, 5 code |
| 10     | 1    | compression                        | 0 none, 1 zlib, 2 lzma, 3 zstd, 4 codeaware |
| 11     | 4    | original length                    | ≤ 2³²−1                                     |
| 15     | 4    | transmitted (compressed) length    | ≤ 2³²−1                                     |
| 19     | 2    | packet payload size                | 1..4096                                     |
| 21     | 2    | packet count                       | must equal max(1, ⌈payload / packet size⌉)  |
| 23     | 32   | SHA-256 of the original data       | —                                           |
| 55     | 1    | FEC rate code                      | 1 = 1/2, 2 = 2/3, 3 = 3/4                   |
| 56     | 2    | payload `n_fft`                    | even, ≥ 16                                  |
| 58     | 2    | payload cyclic prefix length       | < n_fft                                     |
| 60     | 2    | payload `f_low` (Hz)               | 0 < f_low < f_high ≤ fs/2                   |
| 62     | 2    | payload `f_high` (Hz)              |                                             |
| 64     | 1    | payload pilot spacing              | ≥ 2                                         |
| 65     | 1    | payload default modulation code    | 1 bpsk, 2 qpsk, 3 16qam, 4 64qam, 5 256qam  |
| 66     | 1    | payload training symbol count      | 1..8                                        |
| 67     | 1    | number of adaptive bands           | 0..16 (0 = uniform)                         |
| 68     | 8    | 16 nibbles: per-band modulation    | 0 = band disabled, else modulation code     |
| 76     | 31   | file name (UTF-8, zero padded)     | —                                           |
| 107    | 4    | CRC-32 (IEEE) of bytes 0..106      | must match                                  |

Any failed check rejects the whole transmission ("invalid header: …").
The payload configuration is additionally validated by constructing an
`OFDMConfig`, so impossible geometries (e.g. no carriers in band) are
rejected before any payload processing.

## 3. Packets

```
| index (u16) | payload bytes | CRC-32 (u32) |
```

Packet payload sizes are fully determined by the header (all packets are
`packet_size` bytes except the last). An empty payload is sent as one
empty packet. The receiver reports, per packet: OK, CRC failed, index
mismatch, or missing (recording ended early). Any non-OK packet fails the
transmission; the data is never emitted.

## 4. Coding chain (per packet, and for the header)

```
bytes → bits → convolutional K=7 (171,133) rate 1/2 (+ puncturing 2/3, 3/4)
      → fixed pseudo-random interleaver (per length)
      → concatenate packets → pad to a whole OFDM symbol with random bits
      → scrambler (XOR with fixed PRBS) → modulation mapping (Gray)
```

The receiver reverses this with soft decisions: max-log LLRs per bit,
per-carrier and per-symbol noise weighting, de-scrambling (sign flips),
de-interleaving, and soft Viterbi decoding with tail termination.

## 5. Carrier plan

Active carriers are the FFT bins `k` with `f_low ≤ k·fs/n_fft ≤ f_high`,
excluding DC and Nyquist. Every `pilot_spacing`-th active carrier is a
pilot (known BPSK value from a fixed PRBS); the rest carry data. With
adaptive bands, data carriers are split into `n_bands` contiguous groups
and each group uses the modulation given in the header (or is disabled,
in which case the carrier is transmitted with zero amplitude). Bits are
consumed in carrier order: each carrier takes as many bits as its
modulation carries.

Training symbols are known BPSK sequences on all active carriers;
consecutive training symbols use *different* sequences so inter-symbol
interference from an insufficient cyclic prefix appears in the noise
estimate instead of masquerading as signal.

## 6. Channel-state feedback (simulation / future bidirectional link)

`ChannelStateReport`: `n_bands (u8)` followed by `n_bands` × `u8` band SNR
values in 0.5 dB steps. Overhead `1 + n_bands` bytes (9 bytes for 8
bands). The transmitter maps it onto a bit-loading plan whose band
modulations are then carried in the header, so the receiver needs no
further signalling.

## 7. Failure semantics

| situation                      | result                                                |
|--------------------------------|-------------------------------------------------------|
| no preamble                    | `no preamble found`                                   |
| header CRC / magic / version   | `invalid header: …`                                   |
| recording ends early           | `… packet(s) missing (recording truncated)`           |
| corrupted packets              | `… packet(s) failed CRC`                              |
| out-of-order packets           | `… packet(s) out of order`                            |
| decompression error / bomb     | `decompression failed: …`                             |
| SHA-256 mismatch               | `SHA-256 verification failed`                         |

In every failure case `DecodeResult.data is None`; partial information is
only available in `diagnostics`.
