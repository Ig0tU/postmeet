import { NextResponse } from "next/server";
import { transcribeWithGroq } from "../../../lib/groq-transcribe";
import { extractYoutubeId } from "../../../lib/youtube";
import { Innertube, Platform } from "youtubei.js";

export const maxDuration = 300; // Allow longer meetings on Vercel Pro / Fluid

// Enable JS evaluation for signature deciphering (required for some streams)
// Signature matches the type expected by youtubei.js Platform.shim.eval
Platform.shim.eval = (code: string, _env?: Record<string, unknown>) => {
  // eslint-disable-next-line no-new-func
  return new Function(code)();
};

async function downloadYoutubeAudio(
  videoId: string
): Promise<{ buffer: Buffer; filename: string }> {
  const yt = await Innertube.create({
    generate_session_locally: true,
  });

  const info = await yt.getInfo(videoId);
  const formats = info.streaming_data?.adaptive_formats || [];

  // Prefer highest bitrate audio-only format
  const audioFormats = formats
    .filter((f) => f.mime_type?.startsWith("audio/"))
    .sort((a, b) => (b.bitrate || 0) - (a.bitrate || 0));

  const best = audioFormats[0];
  if (!best?.url) {
    throw new Error("No downloadable audio stream found for this video");
  }

  const response = await fetch(best.url);
  if (!response.ok) {
    throw new Error(`Failed to fetch audio stream (${response.status})`);
  }

  const arrayBuffer = await response.arrayBuffer();
  const buffer = Buffer.from(arrayBuffer);

  const ext = best.mime_type?.includes("mp4") ? "m4a" : "webm";
  return {
    buffer,
    filename: `youtube-${videoId}.${ext}`,
  };
}

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const file = formData.get("file");
    const youtubeUrl = String(formData.get("youtube_url") || "").trim();
    const youtubeId = youtubeUrl ? extractYoutubeId(youtubeUrl) : null;

    let audioBlob: Blob | File | null = null;
    let filename = "meeting-audio.mp3";

    if (file && file instanceof Blob) {
      // Local file path (existing behavior)
      const maxBytes = 100 * 1024 * 1024; // 100 MB
      if (file.size > maxBytes) {
        return NextResponse.json(
          { error: "File is too large. Please upload a file under 100 MB." },
          { status: 400 }
        );
      }
      audioBlob = file;
      filename =
        file instanceof File && file.name ? file.name : filename;
    } else if (youtubeId) {
      // YouTube-only path: pure JS fetch via youtubei.js (works on Vercel)
      try {
        const { buffer, filename: dlName } = await downloadYoutubeAudio(youtubeId);
        if (buffer.length > 100 * 1024 * 1024) {
          return NextResponse.json(
            {
              error:
                "Downloaded audio is too large. Please try a shorter video or upload a local file.",
            },
            { status: 400 }
          );
        }
        // Cast to satisfy BlobPart typing (Buffer is a Uint8Array under the hood)
        audioBlob = new Blob([buffer as unknown as BlobPart], {
          type: "audio/mpeg",
        });
        filename = dlName || `youtube-${youtubeId}.mp3`;
      } catch (dlErr) {
        console.error("YouTube audio download failed:", dlErr);
        return NextResponse.json(
          {
            ok: false,
            error:
              "Could not download audio from YouTube. The video may be restricted, private, or unavailable. Try a different link or upload a local file.",
          },
          { status: 422 }
        );
      }
    } else {
      return NextResponse.json(
        {
          error:
            "Please upload an audio or video file, or provide a valid YouTube link.",
        },
        { status: 400 }
      );
    }

    const result = await transcribeWithGroq(audioBlob, filename);

    if (result.error || result.source === "none") {
      return NextResponse.json(
        {
          ok: false,
          error:
            result.error ||
            "We could not create a transcript from that file. Please try a different audio or video file.",
        },
        { status: 422 }
      );
    }

    // Simple speaker clustering heuristic for the review step
    // (Real diarization can be layered later; this gives users something useful to approve/rename)
    const speakers = inferSpeakers(result.cues);

    return NextResponse.json({
      ok: true,
      message: "Transcript ready",
      text: result.text,
      cues: result.cues,
      duration: result.duration,
      source: result.source,
      speakers,
    });
  } catch (err) {
    console.error("Transcribe error:", err);
    return NextResponse.json(
      {
        ok: false,
        error:
          "Something went wrong while processing your recording. Please try again.",
      },
      { status: 500 }
    );
  }
}

/** Very lightweight speaker inference so the UI can offer rename/approve. */
function inferSpeakers(cues: Array<{ start: number; text: string }>) {
  // Group roughly every 45–90 seconds of continuous speech as a potential speaker turn
  // This is a placeholder until full diarization is added.
  const groups: Array<{ id: string; label: string; sample: string; count: number }> = [];
  let current: { texts: string[]; start: number } | null = null;
  let speakerIndex = 1;

  for (const cue of cues) {
    if (!current) {
      current = { texts: [cue.text], start: cue.start };
      continue;
    }

    const gap = cue.start - current.start;
    if (gap > 55 || current.texts.length > 12) {
      // Close previous group
      const sample = current.texts.slice(0, 2).join(" ").slice(0, 140);
      groups.push({
        id: `spk-${speakerIndex}`,
        label: `Speaker ${speakerIndex}`,
        sample,
        count: current.texts.length,
      });
      speakerIndex += 1;
      current = { texts: [cue.text], start: cue.start };
    } else {
      current.texts.push(cue.text);
    }
  }

  if (current && current.texts.length) {
    groups.push({
      id: `spk-${speakerIndex}`,
      label: `Speaker ${speakerIndex}`,
      sample: current.texts.slice(0, 2).join(" ").slice(0, 140),
      count: current.texts.length,
    });
  }

  // Cap at a reasonable number for the review UI
  return groups.slice(0, 12);
}
