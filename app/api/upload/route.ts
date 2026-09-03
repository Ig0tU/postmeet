import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const worker = process.env.POSTMEET_WORKER_URL?.replace(/\/$/, "");
  if (!worker) {
    return NextResponse.json({ error: "POSTMEET_WORKER_URL is not configured." }, { status: 503 });
  }

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
