/** Python publication runs on the worker, never in Vercel's Node runtime. */
export async function finalizePublication(result: unknown, request: Record<string, unknown>): Promise<unknown> {
  const worker = (process.env.POSTMEET_WORKER_URL || process.env.NEXT_PUBLIC_POSTMEET_WORKER_URL || "https://acecalisto3-postmeet.hf.space").replace(/\/$/, "");
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (process.env.HF_TOKEN) headers.authorization = `Bearer ${process.env.HF_TOKEN}`;
  const response = await fetch(`${worker}/finalize`, {
    method: "POST", headers, body: JSON.stringify({ result, request }),
    cache: "no-store", signal: AbortSignal.timeout(45000),
  });
  const text = await response.text();
  let data: any;
  try { data = JSON.parse(text); } catch { throw new Error(`Publication worker returned HTTP ${response.status} without JSON`); }
  if (!response.ok || !data?.ok) throw new Error(data?.error || data?.detail || `Publication worker failed: HTTP ${response.status}`);
  return data;
}
