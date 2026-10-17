import { useEffect, useState } from "react";
import ReceivePanel from "./components/ReceivePanel";
import SendPanel from "./components/SendPanel";
import Trace from "./components/Trace";

type Tab = "send" | "receive";
const tabFromHash = (): Tab => (location.hash === "#receive" ? "receive" : "send");

const SOURCE_URL = "https://github.com/ygwyg/overwork/tree/claude/sonic-audio-transmission-qtmn57";

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
    <>
      <header className="top wrap">
        <a className="wordmark" href="/">
          Sonic
        </a>
        <nav>
          <a href="#how">How it works</a>
          <a href={SOURCE_URL}>Source</a>
        </nav>
      </header>

      <main>
        <section className="hero wrap">
          <h1>Send text and files through sound.</h1>
          <p className="lede">Play it on one device and listen on another. No pairing, nothing to install, and every byte is checked on arrival.</p>
        </section>

        <Trace active={sound} />

        <section className="app wrap" aria-label="Send or receive">
          <div className="tabs" role="tablist">
            {(["send", "receive"] as Tab[]).map((t) => (
              <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "is-on" : ""} onClick={() => choose(t)}>
                {t === "send" ? "Send" : "Receive"}
              </button>
            ))}
          </div>
          {tab === "send" ? <SendPanel onSound={setSound} /> : <ReceivePanel onSound={setSound} />}
          {tab === "send" && (
            <p className="quiet handoff">
              On the other device, open <span className="mono">{location.host}/#receive</span> and press Listen.
            </p>
          )}
        </section>

        <section id="how" className="how wrap">
          <h2>How it works</h2>
          <ol className="steps">
            <li>
              <h3>Pack</h3>
              <p>Your message is compressed and split into small packets, each with its own checksum.</p>
            </li>
            <li>
              <h3>Play</h3>
              <p>Every packet becomes hundreds of tones sounding at once between 2 and 10 kHz, the same technique Wi-Fi uses on radio.</p>
            </li>
            <li>
              <h3>Rebuild</h3>
              <p>The listener pulls the tones apart, corrects errors and compares the result with the sender’s SHA-256 fingerprint. It arrives exactly or not at all.</p>
            </li>
          </ol>
        </section>

        <section className="measured wrap">
          <h2>What we measured</h2>
          <p className="lede">A MacBook Pro and a phone in an ordinary room, Balanced speed unless noted.</p>
          <table>
            <thead>
              <tr>
                <th scope="col">Setup</th>
                <th scope="col">Result</th>
                <th scope="col">Signal quality</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Laptop speaker to its own microphone</td>
                <td>Received, even at 64-QAM</td>
                <td>36 dB</td>
              </tr>
              <tr>
                <td>Laptop to phone, half a metre</td>
                <td>Received</td>
                <td>21.5 dB</td>
              </tr>
              <tr>
                <td>Laptop to phone, two metres</td>
                <td>Not received</td>
                <td>3 dB after room echoes</td>
              </tr>
            </tbody>
          </table>
          <p className="note">Up close the signal is clean. Across a room, reflections off the walls arrive later than each tone can absorb and blur into the next one. That’s the next thing to solve.</p>
        </section>
      </main>

      <footer className="foot wrap">
        <p>Sonic is an open experiment in sending data as sound.</p>
        <a href={SOURCE_URL}>Source on GitHub</a>
      </footer>
    </>
  );
}
