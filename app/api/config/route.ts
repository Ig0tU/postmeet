import { NextResponse } from "next/server";

export async function GET() {
  // Preserve the existing worker destination. Its output is finalized through
  // the canonical publication boundary before download links become available.
  const workerUrl =
    process.env.NEXT_PUBLIC_POSTMEET_WORKER_URL ||
    process.env.POSTMEET_WORKER_URL ||
    "https://acecalisto3-postmeet.hf.space";
  return NextResponse.json({
    workerUrl: workerUrl.replace(/\/$/, ""),
  });
}
