import { NextResponse } from "next/server";
import { finalizePublication } from "../../publication";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    return NextResponse.json(await finalizePublication(body.result, body.request || {}));
  } catch (error) {
    return NextResponse.json({ ok: false, error: error instanceof Error ? error.message : String(error) }, { status: 502 });
  }
}
