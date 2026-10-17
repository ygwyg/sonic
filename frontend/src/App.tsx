import { useEffect, useState } from "react";
import ReceivePanel from "./components/ReceivePanel";
import SendPanel from "./components/SendPanel";
import Trace from "./components/Trace";

type Tab = "send" | "receive";
const tabFromHash = (): Tab => (location.hash === "#receive" ? "receive" : "send");

export default function App() {
  const [tab, setTab] = useState<Tab>(tabFromHash);
  const [sound, setSound] = useState(false);

  useEffect(() => {
    const on = () => setTab(tabFromHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  const choose = (t: Tab) => {
    history.replaceState(null, "", t === "receive" ? "#receive" : location.pathname);
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
        {(["send", "receive"] as Tab[]).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "is-on" : ""} onClick={() => choose(t)}>
            {t === "send" ? "Send" : "Receive"}
          </button>
        ))}
      </nav>

      <Trace active={sound} />

      {tab === "send" ? <SendPanel onSound={setSound} /> : <ReceivePanel onSound={setSound} />}
    </main>
  );
}
