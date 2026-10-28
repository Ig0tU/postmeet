import { NextResponse } from "next/server";

export async function POST(request: Request) {
  try {
    const body = await request.json().catch(() => ({}));
    const provided =
      typeof body?.key === "string" ? body.key.trim() : "";

    const ownerKey = process.env.POSTMEET_OWNER_KEY || "";

    if (!ownerKey) {
      return NextResponse.json(
        { ok: false, error: "Owner access is not configured." },
        { status: 503 }
      );
    }

    if (!provided || provided !== ownerKey) {
      return NextResponse.json(
        { ok: false, error: "Invalid access key." },
        { status: 401 }
      );
    }

    return NextResponse.json({
      ok: true,
      role: "owner",
      unlimited: true,
    });
  } catch {
    return NextResponse.json(
      { ok: false, error: "Unable to validate access key." },
      { status: 500 }
    );
  }
}
