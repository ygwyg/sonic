export function bytes(n: number): string {
  if (n < 1024) return `${n} bytes`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function seconds(s: number): string {
  return s < 10 ? `${s.toFixed(1)} s` : `${Math.round(s)} s`;
}

export function bitrate(bps: number | null | undefined): string {
  if (bps == null) return "–";
  return bps >= 1000 ? `${(bps / 1000).toFixed(1)} kbit/s` : `${Math.round(bps)} bit/s`;
}

const MOD: Record<string, string> = { bpsk: "BPSK", qpsk: "QPSK", "16qam": "16-QAM", "64qam": "64-QAM", "256qam": "256-QAM" };
export function modulation(m: string, rate: string): string {
  return `${MOD[m] ?? m}, rate ${rate}`;
}
