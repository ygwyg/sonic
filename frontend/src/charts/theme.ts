/* Shared chart constants. Series colors follow a fixed categorical order
 * (validated for the dark surface); never cycle beyond the eight slots. */

export const SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"] as const;

export const INK = "#e8ebef";
export const INK2 = "#b4bcc8";
export const MUTED = "#7a8595";
export const GRID = "#262d38";
export const PANEL = "#12161c";

/** Section colors for the transmission layout (fixed by role). */
export const SECTION_COLORS: Record<string, string> = {
  preamble: "#c98500",
  guard: "#7a8595",
  header_training: "#9085e9",
  header_data: "#3987e5",
  payload_training: "#d55181",
  payload_data: "#199e70",
  tail_guard: "#7a8595",
};

/** Carrier role colors (pilot / modulation / disabled). */
export const ROLE_COLORS: Record<string, string> = {
  pilot: "#c98500",
  disabled: "#3a4350",
  bpsk: "#199e70",
  qpsk: "#3987e5",
  "16qam": "#9085e9",
  "64qam": "#d55181",
  "256qam": "#d95926",
};

export function roleColor(role: string): string {
  return ROLE_COLORS[role] ?? "#e66767";
}

export const MODULATION_ORDER = ["bpsk", "qpsk", "16qam", "64qam", "256qam"];

export function modulationColor(m: string): string {
  const i = MODULATION_ORDER.indexOf(m);
  return i >= 0 ? SERIES[i] : SERIES[7];
}

export const TOOLTIP_STYLE = {
  contentStyle: { background: "#181d25", border: "1px solid #262d38", borderRadius: 6, fontSize: 12, fontFamily: "ui-monospace, monospace" },
  labelStyle: { color: "#b4bcc8" },
  itemStyle: { color: "#e8ebef" },
};

/** Viridis-like colormap, t in [0,1]. */
export function viridis(t: number): [number, number, number] {
  const stops: [number, number, number][] = [
    [68, 1, 84],
    [72, 35, 116],
    [64, 67, 135],
    [52, 94, 141],
    [41, 120, 142],
    [32, 144, 140],
    [34, 167, 132],
    [68, 190, 112],
    [121, 209, 81],
    [189, 222, 38],
    [253, 231, 37],
  ];
  const x = Math.max(0, Math.min(1, t)) * (stops.length - 1);
  const i = Math.floor(x);
  const f = x - i;
  const a = stops[i];
  const b = stops[Math.min(stops.length - 1, i + 1)];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}
