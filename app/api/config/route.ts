import { NextResponse } from "next/server";

export async function GET() {
  const workerUrl =
    process.env.NEXT_PUBLIC_POSTMEET_WORKER_URL ||
    process.env.POSTMEET_WORKER_URL ||
    "https://acecalisto3-postmeet.hf.space";
  return NextResponse.json({
    workerUrl: workerUrl.replace(/\/$/, ""),
  });
}
