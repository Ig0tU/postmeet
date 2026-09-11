import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { execFile } from "child_process";
import { promisify } from "util";

const execFileAsync = promisify(execFile);

export async function POST(request: Request) {
  let body: Record<string, unknown> = {};
  try {
    const raw = await request.json();
    if (raw && typeof raw === "object") {
      body = raw as Record<string, unknown>;
    }
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const filePathStr = String(body.filePath || body.source || "").trim();
  const youtubeUrlStr = String(body.youtubeUrl || body.youtube_url || body.media_url || "").trim();
  const siteUrlStr = String(body.site_url || body.siteUrl || "").trim();

  const worker = process.env.POSTMEET_WORKER_URL?.replace(/\/$/, "");

  try {
    if (worker) {
      const headers: Record<string, string> = { "content-type": "application/json" };
      if (process.env.HF_TOKEN) {
        headers["authorization"] = `Bearer ${process.env.HF_TOKEN}`;
      }

      const payload = {
        filePath: filePathStr,
        source: filePathStr || youtubeUrlStr,
        youtubeUrl: youtubeUrlStr,
        site_url: siteUrlStr,
        ...body,
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
      return NextResponse.json(data, { status: response.status });
    }

    if (!filePathStr && !youtubeUrlStr) {
      return NextResponse.json({ error: "A filePath or youtubeUrl must be provided." }, { status: 400 });
    }

    const sourceArg = filePathStr || youtubeUrlStr;
    const outDir = path.join(process.cwd(), "upload", "tmp", `out-${Date.now()}`);

    const args = ["-m", "postmeet.cli", "run", sourceArg, "--output-dir", outDir];
    if (siteUrlStr) args.push("--site-url", siteUrlStr);
    if (youtubeUrlStr) args.push("--youtube-url", youtubeUrlStr);

    await execFileAsync("python3", args, { env: { ...process.env, PYTHONPATH: process.cwd() } });

    const layoutPath = path.join(outDir, "layout.json");
    const payloadPath = path.join(outDir, "payload.json");
    const htmlPath = path.join(outDir, "meeting.html");
    const valPath = path.join(outDir, "validation.json");

    let layoutObj = null;
    let payloadObj: Record<string, unknown> | null = null;
    let htmlContent = "";
    let valObj = null;

    if (fs.existsSync(layoutPath)) {
      layoutObj = JSON.parse(await fs.promises.readFile(layoutPath, "utf-8"));
    }
    if (fs.existsSync(payloadPath)) {
      payloadObj = JSON.parse(await fs.promises.readFile(payloadPath, "utf-8"));
    }
    if (fs.existsSync(htmlPath)) {
      htmlContent = await fs.promises.readFile(htmlPath, "utf-8");
    }
    if (fs.existsSync(valPath)) {
      valObj = JSON.parse(await fs.promises.readFile(valPath, "utf-8"));
    }

    const items = Array.isArray(payloadObj?.items) ? payloadObj.items : [];

    return NextResponse.json({
      ok: true,
      message: "Meeting processed successfully!",
      layout: layoutObj,
      payload: payloadObj,
      html: htmlContent,
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
    if (filePathStr) {
      const resolved = path.isAbsolute(filePathStr)
        ? filePathStr
        : path.join(process.cwd(), filePathStr);
      const tmpDir = path.join(process.cwd(), "upload", "tmp");

      if (resolved.startsWith(tmpDir) && fs.existsSync(resolved)) {
        try {
          await fs.promises.unlink(resolved);
        } catch {
          // Ignore unlink errors during cleanup
        }
      }
    }
  }
}
