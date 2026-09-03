"use client";

import { ChangeEvent, DragEvent, FormEvent, useState } from "react";

interface PipelineResult {
  ok?: boolean;
  message?: string;
  error?: string;
  layout?: Record<string, unknown>;
  payload?: Record<string, unknown>;
  html?: string;
  manifest?: Record<string, unknown>;
  validation?: Record<string, unknown>;
  counts?: { items?: number; chapters?: number; agenda?: number };
}

export default function Home() {
  const [mode, setMode] = useState<"upload" | "url">("upload");
  const [source, setSource] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [siteUrl, setSiteUrl] = useState("");
  const [isDragging, setIsDragging] = useState(false);

  const [status, setStatus] = useState("");
  const [statusType, setStatusType] = useState<"info" | "error" | "success">("info");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PipelineResult | null>(null);

  // Joomla Bridge state
  const [joomlaUrl, setJoomlaUrl] = useState("");
  const [bridgeToken, setBridgeToken] = useState("");
  const [joomlaStatus, setJoomlaStatus] = useState("");
  const [joomlaBusy, setJoomlaBusy] = useState(false);

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  }

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave() {
    setIsDragging(false);
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
      setMode("upload");
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (mode === "upload" && !file) {
      setStatus("Please select a file to upload.");
      setStatusType("error");
      return;
    }
    if (mode === "url" && !source.trim()) {
      setStatus("Please provide a recording URL.");
      setStatusType("error");
      return;
    }

    setBusy(true);
    setStatus("Transposing & processing meeting (ASR extraction, validation & hydration)...");
    setStatusType("info");
    setResult(null);

    try {
      let response: Response;

      if (mode === "upload" && file) {
        // Direct browser upload to Hugging Face worker completely bypasses Vercel 4.5MB serverless limits
        let targetUrl = "https://acecalisto3-postmeet.hf.space/upload";
        try {
          const cfg = await fetch("/api/config").then((r) => r.json());
          if (cfg?.workerUrl) {
            targetUrl = `${cfg.workerUrl}/upload`;
          }
        } catch {}

        const fd = new FormData();
        fd.append("file", file);
        if (siteUrl.trim()) fd.append("site_url", siteUrl.trim());
        response = await fetch(targetUrl, {
          method: "POST",
          body: fd,
        });
      } else {
        response = await fetch("/api/process", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ source: source.trim(), site_url: siteUrl.trim() }),
        });
      }

      const text = await response.text();
      let data: PipelineResult;
      try {
        data = JSON.parse(text);
      } catch {
        if (text.includes("500") || text.includes("<html")) {
          throw new Error("Worker temporarily timed out or rejected payload. Please ensure file is valid media/captions.");
        }
        throw new Error(text || "Server error");
      }
      if (!response.ok || !data.ok) {
        throw new Error(data.error || data.message || "Processing failed");
      }

      setResult(data);
      setStatus(data.message || "Meeting processed successfully!");
      setStatusType("success");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Something went wrong.");
      setStatusType("error");
    } finally {
      setBusy(false);
    }
  }

  function downloadJson(obj: unknown, filename: string) {
    if (!obj) return;
    const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function downloadHtml(htmlStr?: string) {
    if (!htmlStr) return;
    const blob = new Blob([htmlStr], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "meeting.html";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function copyLayoutJson() {
    if (!result?.layout) return;
    navigator.clipboard.writeText(JSON.stringify(result.layout, null, 2))
      .then(() => alert("Hydrated YOOtheme layout.json copied to clipboard!"))
      .catch(() => alert("Could not copy to clipboard."));
  }

  async function pushToJoomla() {
    if (!joomlaUrl.trim() || !bridgeToken.trim()) {
      setJoomlaStatus("Please enter both Joomla Site URL and Bridge Token.");
      return;
    }
    if (!result?.payload) {
      setJoomlaStatus("No meeting payload ready to push.");
      return;
    }

    setJoomlaBusy(true);
    setJoomlaStatus("Pushing meeting record to Joomla workflow registry...");

    try {
      const pushPayload = {
        ...result.payload,
        layout: result.layout,
      };

      const resp = await fetch("/api/push", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          joomla_url: joomlaUrl.trim(),
          bridge_token: bridgeToken.trim(),
          data: pushPayload,
        }),
      });

      const resData = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(resData.error || resData.message || "Push failed");
      }

      setJoomlaStatus("✅ Successfully pushed to Joomla! Key: " + (resData.key || "Saved"));
    } catch (err) {
      setJoomlaStatus("❌ Push failed: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setJoomlaBusy(false);
    }
  }

  return (
    <main className="shell">
      <nav className="nav">
        <div className="brand">
          <span className="mark" /> POSTMEET
        </div>
        <span className="badge">Evidence-bound meeting intelligence</span>
      </nav>

      <section className="hero">
        <div>
          <div className="eyebrow">Meeting → Evidence → YOOtheme Hydration</div>
          <h1>Turn meetings into records you can trust.</h1>
          <p className="lede">
            PostMeet transcribes audio/video or parses transcripts, extracts timestamped evidence and agenda motions, then outputs hydrated YOOtheme layout JSON and clean HTML.
          </p>
        </div>

        <form className="card" onSubmit={submit}>
          <h2>Process a meeting</h2>
          <p>Upload a media/transcript file or paste a video URL.</p>

          <div className="tabs">
            <button
              type="button"
              className={`tab-btn ${mode === "upload" ? "active" : ""}`}
              onClick={() => setMode("upload")}
            >
              📁 File Upload
            </button>
            <button
              type="button"
              className={`tab-btn ${mode === "url" ? "active" : ""}`}
              onClick={() => setMode("url")}
            >
              🌐 Video URL
            </button>
          </div>

          {mode === "upload" ? (
            <div
              className={`dropzone ${isDragging ? "dragover" : ""}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => document.getElementById("file-upload-input")?.click()}
            >
              <div className="dropzone-icon">📥</div>
              <div className="dropzone-label">
                {file ? (
                  <strong>{file.name} ({(file.size / (1024 * 1024)).toFixed(1)} MB)</strong>
                ) : (
                  <span>Click to browse or drop media / transcript</span>
                )}
              </div>
              <div className="dropzone-hint">
                Audio/Video (.mp4, .mp3, .wav, .m4a), Captions (.vtt, .srt, .txt), or Payload (.json)
              </div>
              <input
                id="file-upload-input"
                type="file"
                style={{ display: "none" }}
                onChange={handleFileChange}
                accept=".mp4,.mov,.mkv,.webm,.mp3,.m4a,.wav,.vtt,.srt,.txt,.json"
              />
            </div>
          ) : (
            <input
              className="input"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=... or .mp4 URL"
              type="url"
            />
          )}

          <div style={{ marginTop: "12px" }}>
            <input
              className="input"
              value={siteUrl}
              onChange={(e) => setSiteUrl(e.target.value)}
              placeholder="Optional Site URL for brand extraction (https://example.org)"
              type="url"
            />
          </div>

          <div className="actions">
            <button className="primary" disabled={busy} type="submit">
              {busy ? "Processing meeting…" : "Process meeting"}
            </button>
            <button
              className="secondary"
              type="button"
              onClick={() => {
                setSource("");
                setFile(null);
                setResult(null);
                setStatus("");
              }}
            >
              Clear
            </button>
          </div>

          {status && (
            <div className={`status ${statusType}`}>
              <strong>Status:</strong> {status}
            </div>
          )}

          {/* Results and Downloads */}
          {result && (
            <div className="results-panel">
              <div className="results-header">
                <h3>🎉 Meeting Artifacts Ready</h3>
                <span className="results-counts">
                  {result.counts?.items ?? 0} items · {result.counts?.chapters ?? 0} chapters · {result.counts?.agenda ?? 0} agenda outcomes
                </span>
              </div>

              <div className="download-grid">
                <button
                  type="button"
                  className="dl-btn primary"
                  onClick={() => downloadJson(result.layout, "layout.json")}
                >
                  📥 Download layout.json (YOOtheme)
                </button>
                <button
                  type="button"
                  className="dl-btn"
                  onClick={() => downloadJson(result.payload, "payload.json")}
                >
                  📥 Download payload.json
                </button>
                <button
                  type="button"
                  className="dl-btn"
                  onClick={() => downloadHtml(result.html)}
                >
                  📄 Download meeting.html
                </button>
                <button
                  type="button"
                  className="dl-btn"
                  onClick={copyLayoutJson}
                >
                  📋 Copy Layout JSON
                </button>
              </div>

              {/* Joomla Plugin Bridge Direct Push */}
              <div className="plugin-bridge">
                <h4>🔌 Direct Push to Joomla / YOOtheme Bridge (plg_system_figmatoyoo)</h4>
                <p className="bridge-desc">
                  Push this record directly into your Joomla site’s WorkflowRegistry for native YOOtheme builder rendering.
                </p>
                <div className="bridge-inputs">
                  <input
                    className="input"
                    value={joomlaUrl}
                    onChange={(e) => setJoomlaUrl(e.target.value)}
                    placeholder="Joomla Site URL (e.g. https://yoursite.com)"
                    type="url"
                  />
                  <input
                    className="input"
                    value={bridgeToken}
                    onChange={(e) => setBridgeToken(e.target.value)}
                    placeholder="Bridge Token (from com_figmatoyoo Options)"
                    type="text"
                  />
                  <button
                    type="button"
                    className="primary"
                    style={{ whiteSpace: "nowrap" }}
                    disabled={joomlaBusy}
                    onClick={pushToJoomla}
                  >
                    {joomlaBusy ? "Pushing…" : "Push to Joomla"}
                  </button>
                </div>
                {joomlaStatus && (
                  <div className="status" style={{ marginTop: "8px" }}>{joomlaStatus}</div>
                )}
              </div>
            </div>
          )}
        </form>
      </section>

      <section className="pipeline" aria-label="PostMeet pipeline">
        <div className="step">
          <b>01 · Ingest</b>
          <span>Direct file upload (.mp4, .mp3, .vtt, .srt, .txt, .json) or remote URL.</span>
        </div>
        <div className="step">
          <b>02 · Transcribe & Extract</b>
          <span>Whisper ASR or caption alignment with evidence timestamp preservation.</span>
        </div>
        <div className="step">
          <b>03 · Validate & Hydrate</b>
          <span>Validation gate checks evidence before chunking into YOOtheme layout JSON.</span>
        </div>
        <div className="step">
          <b>04 · Publish & Export</b>
          <span>Downloadable layout.json or direct push into Joomla plg_system_figmatoyoo.</span>
        </div>
      </section>

      <footer className="footer">
        PostMeet 1.1 · Evidence-bound meeting intelligence · SignalMesh & FigmaToYoo compatible.
      </footer>
    </main>
  );
}
