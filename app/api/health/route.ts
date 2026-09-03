import { NextResponse } from "next/server";

export function GET() {
  return NextResponse.json({ ok: true, service: "postmeet-web", workerConfigured: Boolean(process.env.POSTMEET_WORKER_URL) });
}
