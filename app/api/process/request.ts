// Transport only: postmeet.playback owns provider detection, metadata and URLs.
// A downloaded file remains the processing source even when YouTube is playback.
export function normalizeProcessRequest(body: Record<string, unknown>) {
  const text = (...values: unknown[]): string => {
    for (const value of values) {
      if (typeof value === "string" && value.trim()) return value.trim();
    }
    return "";
  };

  const filePath = text(body.filePath, body.file_path);
  const youtubeUrl = text(body.youtubeUrl, body.youtube_url);
  const mediaUrl = text(body.media_url, body.mediaUrl);
  const source = filePath || text(body.source) || youtubeUrl || mediaUrl;
  const siteUrl = text(body.site_url, body.siteUrl);
  return { filePath, source, youtubeUrl, mediaUrl, siteUrl };
}

export function pipelineArguments(
  input: ReturnType<typeof normalizeProcessRequest>,
  outputDir: string,
): string[] {
  const args = ["-m", "postmeet.cli", "run", input.source, "--output-dir", outputDir];
  if (input.siteUrl) args.push("--site-url", input.siteUrl);
  if (input.youtubeUrl) args.push("--youtube-url", input.youtubeUrl);
  if (input.mediaUrl) args.push("--media-url", input.mediaUrl);
  return args;
}
