// Runs in the YouTube page's main world so it can read player data.
(function () {
  function extractAudioUrl() {
    try {
      const pr = window.ytInitialPlayerResponse;
      if (!pr || !pr.streamingData) return null;

      const formats = [
        ...(pr.streamingData.adaptiveFormats || []),
        ...(pr.streamingData.formats || []),
      ];

      const audioOnly = formats
        .filter((f) => f.mimeType && f.mimeType.startsWith("audio/"))
        .sort((a, b) => (b.bitrate || 0) - (a.bitrate || 0));

      const best = audioOnly[0];
      if (!best) return null;

      return {
        url: best.url || null,
        mimeType: best.mimeType || null,
        bitrate: best.bitrate || 0,
        contentLength: best.contentLength || null,
      };
    } catch {
      return null;
    }
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (event.data?.type !== "POSTMEET_GET_AUDIO") return;

    const result = extractAudioUrl();
    window.postMessage(
      { type: "POSTMEET_AUDIO_RESULT", result },
      "*"
    );
  });
})();
