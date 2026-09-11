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
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [siteUrl, setSiteUrl] = useState("");
  const [isDragging, setIsDragging] = useState(false);

  const [status, setStatus] = useState("");
  const [statusType, setStatusType] = useState<"info" | "error" | "success">("info");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PipelineResult | null>(null);

  // Speaker mapping state
  const [speakers, setSpeakers] = useState<Array<{ id: string; label: string; count: number; sample: string; customName: string }>>([]);
  const [speakersApplied, setSpeakersApplied] = useState(false);

  // Joomla Bridge state
  const [joomlaUrl, setJoomlaUrl] = useState("");
  const [bridgeToken, setBridgeToken] = useState("");
  const [joomlaStatus, setJoomlaStatus] = useState("");
  const [joomlaBusy, setJoomlaBusy] = useState(false);

  function handleSpeakerNameChange(id: string, name: string) {
    setSpeakers((prev) =>
      prev.map((s) => (s.id === id ? { ...s, customName: name } : s))
    );
  }

  function applySpeakerNames() {
    if (!result?.payload) return;
    const payloadCopy = JSON.parse(JSON.stringify(result.payload));
    const nameMap: Record<string, string> = {};

    speakers.forEach((s) => {
      const target = (s.customName || "").trim();
      if (target && target !== s.label) {
        nameMap[s.label] = target;
        nameMap[s.id] = target;
      }
    });

    if (Object.keys(nameMap).length === 0) {
      alert("Please enter at least one new speaker name to apply.");
      return;
    }

    // Replace speaker names across agenda items, chapters, presenter, and transcript
    if (Array.isArray(payloadCopy.items)) {
      payloadCopy.items.forEach((item: Record<string, any>) => {
        if (item.presenter && nameMap[item.presenter]) {
          item.presenter = nameMap[item.presenter];
        }
        if (item.speaker && nameMap[item.speaker]) {
          item.speaker = nameMap[item.speaker];
        }
        Object.entries(nameMap).forEach(([oldName, newName]) => {
          if (item.title && typeof item.title === "string") {
            item.title = item.title.replaceAll(oldName, newName);
          }
          if (item.description && typeof item.description === "string") {
            item.description = item.description.replaceAll(oldName, newName);
          }
          if (item.motion_text && typeof item.motion_text === "string") {
            item.motion_text = item.motion_text.replaceAll(oldName, newName);
          }
          if (item.second_text && typeof item.second_text === "string") {
            item.second_text = item.second_text.replaceAll(oldName, newName);
          }
          if (item.vote_text && typeof item.vote_text === "string") {
            item.vote_text = item.vote_text.replaceAll(oldName, newName);
          }
        });
      });
    }

    if (typeof payloadCopy.transcript_text === "string") {
      let tr = payloadCopy.transcript_text;
      Object.entries(nameMap).forEach(([oldName, newName]) => {
        tr = tr.replaceAll(oldName, newName);
      });
      payloadCopy.transcript_text = tr;
    }

    if (Array.isArray(payloadCopy.speakers)) {
      payloadCopy.speakers.forEach((s: Record<string, any>) => {
        if (nameMap[s.label]) s.label = nameMap[s.label];
        if (nameMap[s.id]) s.label = nameMap[s.id];
      });
    }

    setResult({
      ...result,
      payload: payloadCopy,
    });
    setSpeakersApplied(true);
    alert("✅ Speaker names successfully applied across all agenda items, chapters, and transcript!");
  }

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
      setStatus("Please select a downloaded media file to upload for processing.");
      setStatusType("error");
      return;
    }
    if (mode === "url" && !source.trim() && !youtubeUrl.trim()) {
      setStatus("Please provide a recording or YouTube URL.");
      setStatusType("error");
      return;
    }

    setBusy(true);
    setStatus("Transposing & processing meeting (ASR extraction, validation & hydration)...");
    setStatusType("info");
    setResult(null);

    try {
      let response: Response;

      const effectiveYoutubeUrl = (youtubeUrl.trim() || (mode === "url" ? source.trim() : "")).trim();

      if (file) {
        // Step 1: Upload file ephemerally
        let uploadTarget = "/api/upload";
        try {
          const cfg = await fetch("/api/config").then((r) => r.json());
          if (cfg?.workerUrl) {
            uploadTarget = `${cfg.workerUrl}/upload`;
          }
        } catch {}

        const fd = new FormData();
        fd.append("file", file);
        if (siteUrl.trim()) fd.append("site_url", siteUrl.trim());
        if (effectiveYoutubeUrl) fd.append("youtube_url", effectiveYoutubeUrl);

        const uploadResp = await fetch(uploadTarget, {
          method: "POST",
          body: fd,
        });

        const uploadText = await uploadResp.text();
        let uploadData: any;
        try {
          uploadData = JSON.parse(uploadText);
        } catch {
          throw new Error("Upload failed: " + uploadText);
        }

        if (!uploadResp.ok || uploadData.error) {
          throw new Error(uploadData.error || "Upload failed");
        }

        // If upload endpoint directly processed and returned final result
        if (uploadData.ok && uploadData.layout) {
          response = new Response(JSON.stringify(uploadData), { status: 200 });
        } else {
          // Step 2: Trigger process endpoint with uploaded filePath & youtubeUrl
          let processTarget = "/api/process";
          try {
            const cfg = await fetch("/api/config").then((r) => r.json());
            if (cfg?.workerUrl) {
              processTarget = `${cfg.workerUrl}/process`;
            }
          } catch {}

          response = await fetch(processTarget, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              filePath: uploadData.filePath || uploadData.source,
              youtubeUrl: effectiveYoutubeUrl,
              site_url: siteUrl.trim(),
            }),
          });
        }
      } else {
        response = await fetch("/api/process", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            source: source.trim(),
            youtubeUrl: effectiveYoutubeUrl,
            site_url: siteUrl.trim(),
          }),
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
      if (Array.isArray((data.payload as any)?.speakers)) {
        setSpeakers(
          ((data.payload as any).speakers as Array<any>).map((s) => ({
            id: s.id || `spk-${Math.random()}`,
            label: s.label || "Speaker",
            count: s.count || 1,
            sample: s.sample || "",
            customName: s.label || "",
          }))
        );
      } else {
        setSpeakers([]);
      }
      setSpeakersApplied(false);
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
          <p>Upload a media/transcript file or paste a YouTube / video URL.</p>

          {/* YouTube Video Link Input */}
          <div style={{ marginBottom: "16px" }}>
            <label style={{ display: "block", marginBottom: "6px", fontSize: "0.88rem", fontWeight: 600 }}>
              YouTube Video Link (Optional)
            </label>
            <input
              className="input"
              value={youtubeUrl}
              onChange={(e) => setYoutubeUrl(e.target.value)}
              placeholder="e.g. https://www.youtube.com/watch?v=... or https://youtu.be/..."
              type="url"
            />
            {youtubeUrl.trim() && (
              <div style={{
                marginTop: "8px",
                padding: "10px 12px",
                borderRadius: "8px",
                background: "rgba(255, 255, 255, 0.06)",
                border: "1px solid rgba(255, 255, 255, 0.15)",
                fontSize: "0.84rem",
                lineHeight: "1.4"
              }}>
                ℹ️ <strong>YouTube Stream Integration:</strong> Speech extraction runs on your uploaded local media file, while the final output embeds and syncs directly to this YouTube stream.
                <div style={{ marginTop: "6px" }}>
                  💡 Need to download the YouTube audio/video first? Use an external tool like{" "}
                  <a
                    href={`https://cobalt.tools/?url=${encodeURIComponent(youtubeUrl.trim())}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: "#60a5fa", textDecoration: "underline" }}
                  >
                    Cobalt Downloader
                  </a>{" "}
                  or <code style={{ background: "rgba(0,0,0,0.3)", padding: "2px 4px", borderRadius: "4px" }}>yt-dlp</code> to pull the media file to your device.
                </div>
              </div>
            )}
          </div>

          <div className="tabs">
            <button
              type="button"
              className={`tab-btn ${mode === "upload" ? "active" : ""}`}
              onClick={() => setMode("upload")}
            >
              📁 File Upload (Processing Target)
            </button>
            <button
              type="button"
              className={`tab-btn ${mode === "url" ? "active" : ""}`}
              onClick={() => setMode("url")}
            >
              🌐 Direct Media URL
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
                  <span>Click to browse or drop Downloaded Media / Transcript File</span>
                )}
              </div>
              <div className="dropzone-hint">
                Audio/Video (.mp4, .mp3, .wav, .m4a), Captions (.vtt, .srt, .txt), or Payload (.json). File is deleted after processing.
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
              placeholder="https://example.org/meeting.mp4 or transcript URL"
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
                setYoutubeUrl("");
                setFile(null);
                setResult(null);
                setStatus("");
                setSpeakers([]);
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

          {/* Results, Speakers, and Downloads */}
          {result && (
            <div className="results-panel">
              <div className="results-header">
                <h3>🎉 Meeting Artifacts Ready</h3>
                <span className="results-counts">
                  {result.counts?.items ?? 0} items · {result.counts?.chapters ?? 0} chapters · {result.counts?.agenda ?? 0} agenda outcomes · {speakers.length} distinct speakers
                </span>
              </div>

              {/* Speaker Entity Distinction Panel */}
              {speakers.length > 0 && (
                <div className="speaker-panel" style={{
                  margin: "16px 0",
                  padding: "16px",
                  borderRadius: "10px",
                  background: "rgba(255, 255, 255, 0.05)",
                  border: "1px solid rgba(255, 255, 255, 0.15)"
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                    <h4 style={{ margin: 0, fontSize: "1rem", color: "#fff" }}>
                      👥 Speaker Entity Distinction ({speakers.length} Distinct Speakers Detected)
                    </h4>
                    <span style={{ fontSize: "0.8rem", opacity: 0.8 }}>Assign real names & titles to update the record</span>
                  </div>

                  <div style={{ display: "grid", gap: "10px", maxHeight: "280px", overflowY: "auto", paddingRight: "4px" }}>
                    {speakers.map((spk) => (
                      <div key={spk.id} style={{
                        display: "grid",
                        gridTemplateColumns: "140px 1fr 1fr",
                        gap: "10px",
                        alignItems: "center",
                        background: "rgba(0, 0, 0, 0.2)",
                        padding: "8px 12px",
                        borderRadius: "6px"
                      }}>
                        <div>
                          <strong style={{ display: "block", fontSize: "0.88rem" }}>{spk.label}</strong>
                          <span style={{ fontSize: "0.75rem", opacity: 0.7 }}>{spk.count} speaking turns</span>
                        </div>
                        <div style={{ fontSize: "0.8rem", opacity: 0.8, fontStyle: "italic", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          &ldquo;{spk.sample}&rdquo;
                        </div>
                        <input
                          className="input"
                          style={{ margin: 0, padding: "6px 10px", fontSize: "0.88rem" }}
                          value={spk.customName}
                          onChange={(e) => handleSpeakerNameChange(spk.id, e.target.value)}
                          placeholder="e.g. Jordan Lee (Chair)"
                        />
                      </div>
                    ))}
                  </div>

                  <button
                    type="button"
                    className="primary"
                    style={{ marginTop: "12px", width: "100%" }}
                    onClick={applySpeakerNames}
                  >
                    ✨ Apply Speaker Names to Agenda, Motions &amp; Transcripts
                  </button>
                </div>
              )}

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
