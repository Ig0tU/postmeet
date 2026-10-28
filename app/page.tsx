"use client";

import { ChangeEvent, DragEvent, FormEvent, useState } from "react";

type Speaker = {
  id: string;
  label: string;
  sample: string;
  count: number;
  customName: string;
};

type TranscriptResult = {
  ok: boolean;
  message?: string;
  error?: string;
  text?: string;
  cues?: Array<{ start: number; text: string }>;
  duration?: number;
  speakers?: Array<{ id: string; label: string; sample: string; count: number }>;
};

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [statusType, setStatusType] = useState<"info" | "error" | "success">("info");
  const [step, setStep] = useState<"upload" | "review" | "done">("upload");

  const [transcript, setTranscript] = useState<TranscriptResult | null>(null);
  const [speakers, setSpeakers] = useState<Speaker[]>([]);

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    if (e.target.files?.[0]) {
      setFile(e.target.files[0]);
      setStatus("");
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
    if (e.dataTransfer.files?.[0]) {
      setFile(e.dataTransfer.files[0]);
      setStatus("");
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setStatus("Please choose a meeting recording first.");
      setStatusType("error");
      return;
    }

    setBusy(true);
    setStatus("Uploading your recording and turning speech into text…");
    setStatusType("info");
    setTranscript(null);
    setSpeakers([]);
    setStep("upload");

    try {
      const fd = new FormData();
      fd.append("file", file);

      const response = await fetch("/api/transcribe", {
        method: "POST",
        body: fd,
      });

      const data: TranscriptResult = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.error || "We could not process that recording.");
      }

      setTranscript(data);

      const mapped: Speaker[] = (data.speakers || []).map((s) => ({
        id: s.id,
        label: s.label,
        sample: s.sample,
        count: s.count,
        customName: s.label,
      }));
      setSpeakers(mapped);

      setStatus("Transcript is ready. Please review the speakers below.");
      setStatusType("success");
      setStep("review");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Something went wrong. Please try again.");
      setStatusType("error");
    } finally {
      setBusy(false);
    }
  }

  function handleSpeakerNameChange(id: string, name: string) {
    setSpeakers((prev) =>
      prev.map((s) => (s.id === id ? { ...s, customName: name } : s))
    );
  }

  function finishWithSpeakers() {
    setStep("done");
    setStatus("Meeting record is ready. You can download the transcript below.");
    setStatusType("success");
  }

  function downloadTranscript() {
    if (!transcript?.text) return;

    // Apply any renamed speakers into the text for the download
    let finalText = transcript.text;
    speakers.forEach((s) => {
      const name = (s.customName || "").trim();
      if (name && name !== s.label) {
        finalText = finalText.split(s.label).join(name);
      }
    });

    const blob = new Blob([finalText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "meeting-transcript.txt";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function reset() {
    setFile(null);
    setTranscript(null);
    setSpeakers([]);
    setStatus("");
    setStep("upload");
  }

  return (
    <main className="shell">
      <nav className="nav">
        <div className="brand">
          <span className="mark" /> PostMeet
        </div>
        <span className="badge">Meeting records you can trust</span>
      </nav>

      <section className="hero">
        <div>
          <div className="eyebrow">For school boards & public meetings</div>
          <h1>Turn a meeting recording into a clear, trustworthy record.</h1>
          <p className="lede">
            Upload the audio or video of your meeting. PostMeet creates a timestamped
            transcript and helps you label who is speaking — so parents, staff, and the
            public get an accurate record.
          </p>
        </div>

        <form className="card" onSubmit={submit}>
          <h2>Upload your meeting</h2>
          <p>Choose the recording from your computer. We handle the rest.</p>

          <div
            className={`dropzone ${isDragging ? "dragover" : ""}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => document.getElementById("file-upload-input")?.click()}
          >
            <div className="dropzone-icon">📁</div>
            <div className="dropzone-label">
              {file ? (
                <strong>
                  {file.name} ({(file.size / (1024 * 1024)).toFixed(1)} MB)
                </strong>
              ) : (
                <span>Click here or drop your meeting file</span>
              )}
            </div>
            <div className="dropzone-hint">
              Works with MP3, MP4, M4A, WAV and most common audio/video formats
            </div>
            <input
              id="file-upload-input"
              type="file"
              style={{ display: "none" }}
              onChange={handleFileChange}
              accept="audio/*,video/*,.mp3,.mp4,.m4a,.wav,.webm,.mov"
            />
          </div>

          <div className="actions">
            <button className="primary" disabled={busy || !file} type="submit">
              {busy ? "Working on your meeting…" : "Create transcript"}
            </button>
            <button className="secondary" type="button" onClick={reset}>
              Start over
            </button>
          </div>

          {status && (
            <div className={`status ${statusType}`}>
              {status}
            </div>
          )}

          {/* Speaker review step */}
          {step === "review" && speakers.length > 0 && (
            <div className="results-panel">
              <div className="results-header">
                <h3>Who is speaking?</h3>
              </div>
              <p style={{ margin: "0 0 12px", color: "#64748b", fontSize: "14px" }}>
                We detected these speakers. You can rename them (for example “Board
                President” or “Dr. Ramirez”). Leave a name as-is if you’re not sure.
              </p>

              <div className="speaker-grid">
                {speakers.map((s) => (
                  <div key={s.id} className="speaker-card">
                    <label htmlFor={s.id}>{s.label}</label>
                    <input
                      id={s.id}
                      className="input"
                      value={s.customName}
                      onChange={(e) => handleSpeakerNameChange(s.id, e.target.value)}
                      placeholder="Type the correct name"
                    />
                    {s.sample && (
                      <div className="speaker-sample">“{s.sample}…”</div>
                    )}
                  </div>
                ))}
              </div>

              <div className="actions">
                <button
                  className="primary"
                  type="button"
                  onClick={finishWithSpeakers}
                >
                  Save names & finish
                </button>
              </div>
            </div>
          )}

          {/* Done state */}
          {step === "done" && transcript && (
            <div className="results-panel">
              <div className="results-header">
                <h3>Your meeting transcript is ready</h3>
              </div>
              <p style={{ margin: "0 0 16px", color: "#64748b", fontSize: "14px" }}>
                Download the timestamped transcript below. Speaker names you entered
                have been applied.
              </p>
              <div className="download-grid">
                <button
                  className="dl-btn primary"
                  type="button"
                  onClick={downloadTranscript}
                >
                  Download transcript
                </button>
              </div>
            </div>
          )}
        </form>
      </section>

      <section className="pipeline">
        <div className="step">
          <b>1. Upload</b>
          <span>Drop the recording of your board meeting.</span>
        </div>
        <div className="step">
          <b>2. Transcript</b>
          <span>We turn speech into clear, timestamped text.</span>
        </div>
        <div className="step">
          <b>3. Speakers</b>
          <span>You review and name who is speaking.</span>
        </div>
        <div className="step">
          <b>4. Record</b>
          <span>Download a trustworthy meeting record.</span>
        </div>
      </section>

      <footer className="footer">
        PostMeet · Evidence-bound meeting records for schools and public bodies
      </footer>
    </main>
  );
}
