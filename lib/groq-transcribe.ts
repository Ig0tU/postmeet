/**
 * Groq Whisper transcription helper for PostMeet.
 * Uses whisper-large-v3-turbo. Automatically chunks files larger than
 * the Groq free-tier limit so long meetings still transcribe.
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

const GROQ_MAX_BYTES = 18 * 1024 * 1024; // stay under 25 MB free-tier limit

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

async function transcribeOne(
  apiKey: string,
  blob: Blob,
  filename: string
): Promise<TranscriptResult> {
  const form = new FormData();
  form.append("file", blob, filename);
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
}

/**
 * Transcribe an audio/video file using Groq Whisper.
 * Files over ~18 MB are split into chunks, transcribed sequentially,
 * and stitched with approximate time offsets.
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
    if (file.size <= GROQ_MAX_BYTES) {
      return await transcribeOne(apiKey, file, filename);
    }

    // Chunk large files
    const chunks: Blob[] = [];
    for (let offset = 0; offset < file.size; offset += GROQ_MAX_BYTES) {
      chunks.push(file.slice(offset, offset + GROQ_MAX_BYTES));
    }

    const allCues: TranscriptCue[] = [];
    const allTexts: string[] = [];
    let timeOffset = 0;

    for (let i = 0; i < chunks.length; i++) {
      const chunkName = `${filename.replace(/\.[^.]+$/, "")}-part${i + 1}${filename.match(/\.[^.]+$/)?.[0] || ".mp3"}`;
      const result = await transcribeOne(apiKey, chunks[i], chunkName);

      if (result.error || result.source === "none") {
        return {
          text: "",
          cues: [],
          source: "none",
          error: `Chunk ${i + 1}/${chunks.length} failed: ${result.error || "unknown"}`,
        };
      }

      for (const cue of result.cues) {
        allCues.push({
          start: cue.start + timeOffset,
          end: cue.end !== undefined ? cue.end + timeOffset : undefined,
          text: cue.text,
        });
      }

      if (result.text) {
        allTexts.push(result.text);
      }

      // Advance offset by the reported duration of this chunk (or a rough estimate)
      const chunkDuration =
        result.duration ||
        (result.cues.length
          ? Math.max(...result.cues.map((c) => c.end || c.start))
          : 0);
      timeOffset += chunkDuration || 0;
    }

    const text =
      allCues.length > 0
        ? allCues.map((c) => `${formatStamp(c.start)} - ${c.text}`).join("\n")
        : allTexts.join("\n\n");

    return {
      text,
      cues: allCues,
      source: "groq",
      duration: timeOffset || undefined,
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
