/**
 * Groq Whisper transcription helper for PostMeet.
 * Uses whisper-large-v3-turbo for fast, high-quality timestamped transcripts.
 */

export type TranscriptCue = {
  start: number;
  end?: number;
  text: string;
};

export type TranscriptResult = {
  text: string;
  cues: TranscriptCue[];
  source: "groq" | "captions" | "none";
  duration?: number;
  error?: string;
};

function formatStamp(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/**
 * Transcribe an audio/video file using Groq Whisper.
 * Accepts a File or Blob.
 */
export async function transcribeWithGroq(
  file: File | Blob,
  filename = "audio.mp3"
): Promise<TranscriptResult> {
  const apiKey = process.env.GROQ_API_KEY;
  if (!apiKey) {
    return {
      text: "",
      cues: [],
      source: "none",
      error: "GROQ_API_KEY is not configured.",
    };
  }

  try {
    const form = new FormData();
    form.append("file", file, filename);
    form.append("model", "whisper-large-v3-turbo");
    form.append("response_format", "verbose_json");
    form.append("timestamp_granularities[]", "segment");

    const response = await fetch(
      "https://api.groq.com/openai/v1/audio/transcriptions",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey}`,
        },
        body: form,
      }
    );

    if (!response.ok) {
      const errText = await response.text();
      return {
        text: "",
        cues: [],
        source: "none",
        error: `Groq transcription failed (${response.status}): ${errText.slice(0, 300)}`,
      };
    }

    const data = await response.json();

    const segments: Array<{ start: number; end?: number; text?: string }> =
      Array.isArray(data.segments) ? data.segments : [];

    const cues: TranscriptCue[] = segments
      .map((seg) => ({
        start: Number(seg.start) || 0,
        end: seg.end !== undefined ? Number(seg.end) : undefined,
        text: (seg.text || "").trim(),
      }))
      .filter((c) => c.text.length > 0);

    const text =
      cues.length > 0
        ? cues.map((c) => `${formatStamp(c.start)} - ${c.text}`).join("\n")
        : (data.text || "").trim();

    return {
      text,
      cues,
      source: "groq",
      duration: data.duration ? Number(data.duration) : undefined,
    };
  } catch (err) {
    return {
      text: "",
      cues: [],
      source: "none",
      error: err instanceof Error ? err.message : String(err),
    };
  }
}
