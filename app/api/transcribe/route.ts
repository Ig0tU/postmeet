import { NextResponse } from "next/server";
import { transcribeWithGroq } from "../../../lib/groq-transcribe";

export const maxDuration = 300; // Allow longer meetings on Vercel Pro / Fluid

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const file = formData.get("file");

    if (!file || !(file instanceof Blob)) {
      return NextResponse.json(
        { error: "Please upload an audio or video file." },
        { status: 400 }
      );
    }

    // Basic size guard (Groq free tier is generous but we keep a safety limit)
    const maxBytes = 100 * 1024 * 1024; // 100 MB
    if (file.size > maxBytes) {
      return NextResponse.json(
        { error: "File is too large. Please upload a file under 100 MB." },
        { status: 400 }
      );
    }

    const filename =
      file instanceof File && file.name
        ? file.name
        : "meeting-audio.mp3";

    const result = await transcribeWithGroq(file, filename);

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
