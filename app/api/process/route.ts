import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const worker = process.env.POSTMEET_WORKER_URL?.replace(/\/$/, "");
  if (!worker) {
    return NextResponse.json({ error: "POSTMEET_WORKER_URL is not configured." }, { status: 503 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  try {
    const headers: Record<string, string> = { "content-type": "application/json" };
    if (process.env.HF_TOKEN) {
      headers["authorization"] = `Bearer ${process.env.HF_TOKEN}`;
    }

    const response = await fetch(`${worker}/process`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const text = await response.text();
    let data: unknown;
    try { data = JSON.parse(text); } catch { data = { message: text }; }
    return NextResponse.json(data, { status: response.status });
  } catch {
    return NextResponse.json({ error: "Unable to reach the PostMeet worker." }, { status: 502 });
  }
}
