import { useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useAppState } from "../state/AppState";

const NAV: { to: string; label: string; hint: string; glyph: string }[] = [
  { to: "/transmitter", label: "Transmitter", hint: "Encode data to sound", glyph: "TX" },
  { to: "/receiver", label: "Receiver", hint: "Decode a recording", glyph: "RX" },
  { to: "/explorer", label: "Waveform Explorer", hint: "Inspect the OFDM signal", glyph: "FX" },
  { to: "/benchmark", label: "Benchmark Lab", hint: "Experiments and results", glyph: "BM" },
  { to: "/qr", label: "Audio QR Studio", hint: "Share text by sound", glyph: "QR" },
];

export default function Layout({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const { backendOk, backendVersion, lastEncode } = useAppState();

  const nav = (
    <nav className="flex flex-col gap-1">
      {NAV.map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          onClick={() => setOpen(false)}
          className={({ isActive }) =>
            `group flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${
              isActive ? "bg-panel2 text-ink" : "text-ink2 hover:bg-panel2/60 hover:text-ink"
            }`
          }
        >
          <span className="num w-7 shrink-0 rounded border border-line bg-bg px-1 text-center text-[10px] text-muted group-[.active]:border-accent group-[.active]:text-accent">
            {n.glyph}
          </span>
          <span className="flex flex-col leading-tight">
            <span>{n.label}</span>
            <span className="text-[11px] text-muted">{n.hint}</span>
          </span>
        </NavLink>
      ))}
    </nav>
  );

  return (
    <div className="flex min-h-full w-full">
      {/* Sidebar (desktop) */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-line bg-panel p-4 md:flex">
        <Brand />
        <div className="mt-6">{nav}</div>
        <div className="mt-auto space-y-2 pt-6 text-[11px] text-muted">
          <StatusRow ok={backendOk} version={backendVersion} />
          <div>
            Explorer buffer:{" "}
            <span className="num text-ink2">{lastEncode ? `${lastEncode.info.duration_s.toFixed(2)} s` : "empty"}</span>
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-line bg-panel px-4 py-2 md:hidden">
          <button className="btn px-2 py-1" onClick={() => setOpen((o) => !o)} aria-label="Toggle navigation">
            ☰
          </button>
          <Brand compact />
          <div className="ml-auto">
            <StatusRow ok={backendOk} version={backendVersion} />
          </div>
        </header>
        {open && (
          <div className="border-b border-line bg-panel p-3 md:hidden">
            {nav}
          </div>
        )}
        <main className="min-w-0 flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden>
        <rect width="32" height="32" rx="6" fill="#0b0e12" stroke="#262d38" />
        <path
          d="M4 16h3l2-6 3 12 3-16 3 20 3-14 2 4h5"
          fill="none"
          stroke="#3987e5"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <div className="leading-tight">
        <div className="text-sm font-semibold tracking-wide">SONIC</div>
        {!compact && <div className="text-[11px] text-muted">OFDM acoustic data link</div>}
      </div>
    </div>
  );
}

function StatusRow({ ok, version }: { ok: boolean | null; version: string | null }) {
  const color = ok === null ? "bg-muted" : ok ? "bg-good" : "bg-bad";
  const text = ok === null ? "connecting…" : ok ? `backend v${version ?? "?"}` : "backend offline";
  return (
    <div className="flex items-center gap-2 text-[11px] text-muted">
      <span className={`inline-block h-2 w-2 rounded-full ${color}`} />
      <span>{text}</span>
    </div>
  );
}
