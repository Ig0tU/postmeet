// Background service worker for the PostMeet extension.

const POSTMEET_ORIGIN = "https://postmeet-mu.vercel.app";

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "OPEN_POSTMEET") {
    const url =
      POSTMEET_ORIGIN +
      "/?youtube=" +
      encodeURIComponent(msg.youtubeUrl || "");
    chrome.tabs.create({ url });
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "UPLOAD_AND_TRANSCRIBE") {
    handleUploadAndTranscribe(msg)
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ error: err.message || String(err) }));
    return true; // keep channel open for async
  }
});

async function handleUploadAndTranscribe({ videoId, audioUrl, mimeType, youtubeUrl }) {
  // Fetch the audio stream from the extension context (has the user's cookies / session)
  const audioRes = await fetch(audioUrl);
  if (!audioRes.ok) {
    throw new Error("Could not fetch audio stream (" + audioRes.status + ")");
  }

  const blob = await audioRes.blob();
  const ext = (mimeType || "").includes("mp4") ? "m4a" : "webm";
  const filename = "youtube-" + videoId + "." + ext;

  // Upload to PostMeet's Blob endpoint via the existing client-upload flow
  // We POST the file to a simple server route that stores it and returns a URL,
  // or we open PostMeet with the file already staged.
  // For the first version, open PostMeet and pass the YouTube URL;
  // the extension can later POST the blob directly once the token route is confirmed.
  const form = new FormData();
  form.append("file", blob, filename);
  form.append("youtube_url", youtubeUrl || "");
  form.append("source", "extension");

  // Direct upload only works under 4.5 MB. For larger files we fall back to opening the page.
  if (blob.size > 4.5 * 1024 * 1024) {
    // Store a note and open the page so the user can finish via the web UI
    await chrome.storage.local.set({
      pendingYoutube: youtubeUrl,
      pendingVideoId: videoId,
    });
    chrome.tabs.create({
      url: POSTMEET_ORIGIN + "/?youtube=" + encodeURIComponent(youtubeUrl || ""),
    });
    return { ok: true, fallback: true };
  }

  const res = await fetch(POSTMEET_ORIGIN + "/api/transcribe", {
    method: "POST",
    body: form,
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    throw new Error(data.error || "Transcription failed (" + res.status + ")");
  }

  // Open the result page
  chrome.tabs.create({
    url: POSTMEET_ORIGIN + "/?youtube=" + encodeURIComponent(youtubeUrl || ""),
  });

  return { ok: true, transcript: data.text };
}
