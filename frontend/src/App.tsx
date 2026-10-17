import { useEffect, useState } from "react";
import Explore from "./components/Explore";
import ReceivePanel from "./components/ReceivePanel";
import SendPanel from "./components/SendPanel";
import Trace from "./components/Trace";
import type { EncodeResult } from "./lib/api";

type Tab = "send" | "receive" | "explore";
const TABS: [Tab, string][] = [
  ["send", "Send"],
  ["receive", "Receive"],
  ["explore", "Explore"],
];
const tabFromHash = (): Tab => (location.hash === "#receive" ? "receive" : location.hash === "#explore" ? "explore" : "send");

export default function App() {
  const [tab, setTab] = useState<Tab>(tabFromHash);
  const [sound, setSound] = useState(false);
  const [sent, setSent] = useState<EncodeResult | null>(null);

  useEffect(() => {
    const on = () => setTab(tabFromHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  const choose = (t: Tab) => {
    history.replaceState(null, "", t === "send" ? location.pathname : `#${t}`);
    setTab(t);
  };

  return (
    <main className="page">
      <header className="head">
        <h1>Sonic</h1>
        <a className="muted" href="https://github.com/ygwyg/sonic">
          GitHub
        </a>
      </header>
      <p className="muted">Send text and files through sound.</p>

      <nav className="tabs" role="tablist">
        {TABS.map(([t, label]) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "is-on" : ""} onClick={() => choose(t)}>
            {label}
          </button>
        ))}
      </nav>

      <Trace active={sound} />

      {tab === "send" && <SendPanel onSound={setSound} onEncoded={setSent} />}
      {tab === "receive" && <ReceivePanel onSound={setSound} />}
      {tab === "explore" && <Explore sent={sent} />}
    </main>
  );
}
