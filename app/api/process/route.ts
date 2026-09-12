import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { execFile } from "child_process";
import { promisify } from "util";
import { finalizePublication } from "../../publication";
import { normalizeProcessRequest, pipelineArguments } from "./request";

const execFileAsync = promisify(execFile);

export async function POST(request: Request) {
  let body: Record<string, unknown> = {};
  try {
    const raw = await request.json();
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      return NextResponse.json({ error: "Request body must be a JSON object." }, { status: 400 });
    }
    body = raw as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const input = normalizeProcessRequest(body);

  const worker = process.env.POSTMEET_WORKER_URL?.replace(/\/$/, "");

  try {
    if (worker) {
      const headers: Record<string, string> = { "content-type": "application/json" };
      if (process.env.HF_TOKEN) {
        headers["authorization"] = `Bearer ${process.env.HF_TOKEN}`;
      }

      const payload = {
        ...body,
        filePath: input.filePath,
        source: input.source,
        youtubeUrl: input.youtubeUrl,
        youtube_url: input.youtubeUrl,
        media_url: input.mediaUrl,
        site_url: input.siteUrl,
      };

      const response = await fetch(`${worker}/process`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
        cache: "no-store",
      });
      const text = await response.text();
      let data: unknown;
      try { data = JSON.parse(text); } catch { data = { message: text }; }
      return NextResponse.json(response.ok ? await finalizePublication(data, payload) : data, { status: response.status });
    }

    if (!input.source) {
      return NextResponse.json({ error: "A filePath, source, youtubeUrl or media_url must be provided." }, { status: 400 });
    }

    const tmpDir = path.join(process.cwd(), "upload", "tmp");
    await fs.promises.mkdir(tmpDir, { recursive: true });
    const outDir = await fs.promises.mkdtemp(path.join(tmpDir, "out-"));

    // Every artifact is produced together by the canonical Python pipeline.
    // Do not independently reconstruct players, URLs or titles in TypeScript.
    await execFileAsync("python3", pipelineArguments(input, outDir), {
      env: { ...process.env, PYTHONPATH: process.cwd() },
    });

    const layoutPath = path.join(outDir, "layout.json");
    const payloadPath = path.join(outDir, "payload.json");
    const htmlPath = path.join(outDir, "meeting.html");
    const valPath = path.join(outDir, "validation.json");

    const manifestPath = path.join(outDir, "manifest.json");
    const [layoutText, payloadText, htmlContent, validationText, manifestText] = await Promise.all(
      [layoutPath, payloadPath, htmlPath, valPath, manifestPath].map((file) => fs.promises.readFile(file, "utf-8")),
    );
    const layoutObj = JSON.parse(layoutText);
    const payloadObj: Record<string, unknown> = JSON.parse(payloadText);
    const valObj = JSON.parse(validationText);
    const manifestObj = JSON.parse(manifestText);
    if (!valObj?.ok || !htmlContent.trim()) {
      throw new Error("The Python pipeline did not produce validated meeting artifacts.");
    }

    const items = Array.isArray(payloadObj?.items) ? payloadObj.items : [];

    return NextResponse.json({
      ok: true,
      message: "Meeting processed successfully!",
      layout: layoutObj,
      payload: payloadObj,
      html: htmlContent,
      manifest: manifestObj,
      validation: valObj,
      counts: {
        items: items.length,
        chapters: (valObj as Record<string, unknown>)?.chapter_count ?? 0,
        agenda: (valObj as Record<string, unknown>)?.agenda_count ?? 0,
      },
    });
  } catch (err) {
    return NextResponse.json(
      { error: "Processing failed: " + (err instanceof Error ? err.message : String(err)) },
      { status: 500 }
    );
  } finally {
    const processingFile = input.filePath || input.source;
    if (processingFile) {
      const resolved = path.resolve(process.cwd(), processingFile);
      const tmpDir = path.join(process.cwd(), "upload", "tmp");
      const relative = path.relative(tmpDir, resolved);

      if (relative && !relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative) && fs.existsSync(resolved)) {
        try {
          await fs.promises.unlink(resolved);
        } catch {
          // Ignore unlink errors during cleanup
        }
      }
    }
  }
}
