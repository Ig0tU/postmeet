import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

export async function POST(request: Request) {
  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return NextResponse.json({ error: "Request must be multipart/form-data." }, { status: 400 });
  }

  const file = formData.get("file");
  if (!file || !(file instanceof Blob)) {
    return NextResponse.json({ error: "A valid file is required in the 'file' field." }, { status: 400 });
  }

  const worker = process.env.POSTMEET_WORKER_URL?.replace(/\/$/, "");
  if (worker) {
    try {
      const headers: Record<string, string> = {};
      if (process.env.HF_TOKEN) {
        headers["authorization"] = `Bearer ${process.env.HF_TOKEN}`;
      }

      const response = await fetch(`${worker}/upload`, {
        method: "POST",
        headers,
        body: formData,
        cache: "no-store",
      });

      const text = await response.text();
      let data: unknown;
      try {
        data = JSON.parse(text);
      } catch {
        data = { message: text };
      }
      return NextResponse.json(data, { status: response.status });
    } catch (error) {
      return NextResponse.json(
        { error: "Unable to reach the PostMeet worker for file upload: " + (error instanceof Error ? error.message : String(error)) },
        { status: 502 }
      );
    }
  }

  try {
    const tmpDir = path.join(process.cwd(), "upload", "tmp");
    await fs.promises.mkdir(tmpDir, { recursive: true });

    const fileName = file instanceof File ? file.name : "upload.media";
    const safeName = `${Date.now()}-${fileName.replace(/[^a-zA-Z0-9_.-]/g, "_")}`;
    const filePath = path.join(tmpDir, safeName);

    const buffer = Buffer.from(await file.arrayBuffer());
    await fs.promises.writeFile(filePath, buffer);

    const relativePath = path.relative(process.cwd(), filePath);
    return NextResponse.json({ ok: true, filePath: relativePath });
  } catch (err) {
    return NextResponse.json(
      { error: "Failed to save uploaded file locally: " + (err instanceof Error ? err.message : String(err)) },
      { status: 500 }
    );
  }
}
