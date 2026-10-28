import { NextResponse } from "next/server";

export async function GET() {
  // Prefer local Vercel processing. Only use an external worker if explicitly configured.
  const workerUrl =
    process.env.NEXT_PUBLIC_POSTMEET_WORKER_URL ||
    process.env.POSTMEET_WORKER_URL ||
    "";

  return NextResponse.json({
    workerUrl: workerUrl ? workerUrl.replace(/\/$/, "") : null,
    transcriptionProvider: process.env.GROQ_API_KEY ? "groq" : "local",
  });
}
