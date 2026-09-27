"use client";

import { useEffect, useRef, useState } from "react";

type SpeechRecognitionLike = new () => {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  onresult: ((event: { results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
};

declare global { interface Window { SpeechRecognition?: SpeechRecognitionLike; webkitSpeechRecognition?: SpeechRecognitionLike } }

export default function Home() {
  const [listening, setListening] = useState(false);
  const [busy, setBusy] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [reply, setReply] = useState("Ready when you are.");
  const [history, setHistory] = useState<Array<{ role: "you" | "agent"; text: string }>>([]);
  const [context, setContext] = useState<Record<string, string>>({});
  const recognition = useRef<{ start(): void; stop(): void } | null>(null);

  const send = async (text: string) => {
    const value = text.trim();
    if (!value || busy) return;
    setBusy(true);
    setTranscript(value);
    setHistory((items) => [...items, { role: "you", text: value }]);
    try {
      const response = await fetch("/api/assistant", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: value }) });
      const data = await response.json();
      fetch("/api/context").then((item) => item.json()).then(setContext).catch(() => undefined);
      const message = data.response || data.error || "I couldn't complete that.";
      setReply(message);
      setHistory((items) => [...items, { role: "agent", text: message }]);
      if ("speechSynthesis" in window) { window.speechSynthesis.cancel(); window.speechSynthesis.speak(new SpeechSynthesisUtterance(message)); }
    } catch {
      setReply("The local assistant API is unavailable. Start it with python run.py --api --voice.");
    } finally { setBusy(false); }
  };

  const toggleVoice = () => {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) { setReply("This browser does not provide speech recognition. Use the local voice loop instead."); return; }
    if (listening) { recognition.current?.stop(); setListening(false); return; }
    const instance = new Recognition();
    instance.continuous = false; instance.interimResults = false; instance.lang = "en-US";
    instance.onresult = (event) => send(event.results[0][0].transcript);
    instance.onend = () => setListening(false); instance.onerror = () => { setListening(false); setReply("I didn't catch that. Please try again."); };
    recognition.current = instance; setListening(true); instance.start();
  };

  useEffect(() => () => recognition.current?.stop(), []);

  return (
    <main className="console-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">◉</span><span>ORBITAL</span></div>
        <p className="eyebrow">PERSONAL COMPUTER AGENT</p>
        <nav><a className="active">Voice console</a><a>Activity</a><a>Capabilities</a></nav>
        <div className="status-card"><span className="status-dot" /> Local agent online<div className="muted">Voice-first control enabled</div></div>
      </aside>
      <section className="workspace">
        <header className="topbar"><div><p className="eyebrow">CONTROL ROOM / SESSION 01</p><h1>Your computer, in conversation.</h1></div><div className="live-pill"><span className="status-dot" /> READY</div></header>
        <div className="content-grid">
          <section className="voice-panel">
            <div className="panel-kicker">LISTENING INTERFACE <span>MICROPHONE</span></div>
            <div className={`orb ${listening ? "orb-live" : ""}`}><div className="orb-core">{listening ? "LISTENING" : "SPEAK"}<small>{listening ? "release to process" : "tap to talk"}</small></div></div>
            <button className={`talk-button ${listening ? "active" : ""}`} onClick={toggleVoice}>{listening ? "Stop listening" : "Talk to your computer"}</button>
            <p className="hint">Try “Open Chrome”, “Run diagnostics”, or “Find my latest PDF”.</p>
            <div className="heard"><span>HEARD</span><strong>{transcript || "—"}</strong></div>
          </section>
          <section className="response-panel"><div className="panel-kicker">ASSISTANT RESPONSE <span>{busy ? "WORKING" : "VERIFIED"}</span></div><div className="response-copy"><span className="quote-mark">“</span><p>{reply}</p></div><div className="context-row"><div><span>TASK</span><strong>{context.task_status || (busy ? "EXECUTING" : "IDLE")}</strong></div><div><span>APP</span><strong>{context.active_application || context.active_editor || "—"}</strong></div><div><span>URL / PROFILE</span><strong>{context.active_url || context.active_chrome_profile || "—"}</strong></div></div></section>
        </div>
        <section className="activity-panel"><div className="panel-kicker">CONVERSATION <span>{history.length} EVENTS</span></div>{history.length === 0 ? <p className="empty">Your commands and verified results will appear here.</p> : <div className="history">{history.slice(-6).map((item, i) => <div className={`message ${item.role}`} key={`${item.role}-${i}`}><span>{item.role === "you" ? "YOU" : "AGENT"}</span><p>{item.text}</p></div>)}</div>}</section>
      </section>
    </main>
  );
}
