import { NextResponse } from "next/server";

export async function POST(request: Request) {
  let body: any;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const joomlaUrl = String(body.joomla_url || "").trim().replace(/\/$/, "");
  const bridgeToken = String(body.bridge_token || "").trim();
  const data = body.data || body.payload;

  if (!joomlaUrl || !bridgeToken) {
    return NextResponse.json({ error: "Joomla Site URL and Bridge Token are required." }, { status: 400 });
  }
  if (!data) {
    return NextResponse.json({ error: "Meeting payload/data is required." }, { status: 400 });
  }

  const endpoint = `${joomlaUrl}/index.php?option=com_figmatoyoo&task=workflow_push`;
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Bridge-Token": bridgeToken,
      },
      body: JSON.stringify(data),
      cache: "no-store",
    });

    const text = await response.text();
    let resData: unknown;
    try {
      resData = JSON.parse(text);
    } catch {
      resData = { raw: text };
    }
    return NextResponse.json(resData, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to connect to Joomla bridge at " + endpoint + ": " + (error instanceof Error ? error.message : String(error)) },
      { status: 502 }
    );
  }
}
