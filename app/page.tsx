"use client";

import { FormEvent, useState } from "react";

export default function Home() {
  const [source, setSource] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!source.trim()) return;
    setBusy(true);
    setStatus("Submitting to the PostMeet worker…");
    try {
      const response = await fetch("/api/process", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ source: source.trim() }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "Worker request failed");
      setStatus(data.message || "Job accepted. The worker is processing your meeting.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <nav className="nav">
        <div className="brand"><span className="mark" /> POSTMEET</div>
        <span className="badge">Evidence-bound meeting intelligence</span>
      </nav>

      <section className="hero">
        <div>
          <div className="eyebrow">Meeting → evidence → publication</div>
          <h1>Turn meetings into records you can trust.</h1>
          <p className="lede">
            PostMeet extracts timestamped evidence, agendas, motions and outcomes from recordings or transcripts—then produces a validated meeting page and YOOtheme layout.
          </p>
        </div>

        <form className="card" onSubmit={submit}>
          <h2>Process a meeting</h2>
          <p>Paste a YouTube/Vimeo URL or a worker-accessible media/transcript URL.</p>
          <input
            className="input"
            value={source}
            onChange={(event) => setSource(event.target.value)}
            placeholder="https://www.youtube.com/watch?v=…"
            type="url"
            required
          />
          <div className="actions">
            <button className="primary" disabled={busy} type="submit">{busy ? "Processing…" : "Process meeting"}</button>
            <button className="secondary" type="button" onClick={() => setSource("")}>Clear</button>
          </div>
          {status && <div className="status"><strong>Status:</strong> {status}</div>}
        </form>
      </section>

      <section className="pipeline" aria-label="PostMeet pipeline">
        <div className="step"><b>01 · Acquire</b><span>Captions first, local Whisper fallback, timestamp preservation.</span></div>
        <div className="step"><b>02 · Extract</b><span>Agenda, chapters, motions, seconds and votes from observed evidence.</span></div>
        <div className="step"><b>03 · Validate</b><span>Fail closed when evidence or publication metadata is insufficient.</span></div>
        <div className="step"><b>04 · Publish</b><span>Read-only HTML plus hydrated YOOtheme layout JSON.</span></div>
      </section>

      <footer className="footer">PostMeet 1.0 · SignalMesh-compatible, provider-independent core.</footer>
    </main>
  );
}
