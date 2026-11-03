// Content script for YouTube pages.
// Injects a button and coordinates with the main-world script to get the audio URL.

const POSTMEET_ORIGIN = "https://postmeet-mu.vercel.app";

function getVideoId() {
  const url = new URL(location.href);
  const v = url.searchParams.get("v");
  if (v && /^[\w-]{11}$/.test(v)) return v;
  const parts = url.pathname.split("/").filter(Boolean);
  if (parts.length >= 2 && ["shorts", "live", "embed"].includes(parts[0])) {
    const id = parts[1];
    if (/^[\w-]{11}$/.test(id)) return id;
  }
  return null;
}

function injectMainScript() {
  if (document.getElementById("postmeet-injected")) return;
  const s = document.createElement("script");
  s.id = "postmeet-injected";
  s.src = chrome.runtime.getURL("injected.js");
  document.documentElement.appendChild(s);
}

function createButton() {
  if (document.getElementById("postmeet-btn")) return;

  const btn = document.createElement("button");
  btn.id = "postmeet-btn";
  btn.textContent = "Transcribe with PostMeet";
  Object.assign(btn.style, {
    margin: "8px 0",
    padding: "8px 14px",
    background: "#1c1917",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    fontSize: "13px",
    fontWeight: "600",
    cursor: "pointer",
    fontFamily: "system-ui, sans-serif",
  });

  btn.addEventListener("click", onClick);

  // Try common YouTube insertion points
  const target =
    document.querySelector("#above-the-fold #title") ||
    document.querySelector("ytd-watch-metadata") ||
    document.querySelector("#primary") ||
    document.body;
  target.prepend(btn);
}

function onClick() {
  const videoId = getVideoId();
  if (!videoId) {
    alert("Could not find a YouTube video ID on this page.");
    return;
  }

  const btn = document.getElementById("postmeet-btn");
  if (btn) btn.textContent = "Working…";

  // Ask the main-world script for the audio URL
  const handler = (event) => {
    if (event.source !== window) return;
    if (event.data?.type !== "POSTMEET_AUDIO_RESULT") return;
    window.removeEventListener("message", handler);

    const audio = event.data.result;
    if (!audio?.url) {
      // Fallback: open PostMeet with the URL so the user can still proceed
      chrome.runtime.sendMessage({
        type: "OPEN_POSTMEET",
        videoId,
        youtubeUrl: location.href,
      });
      if (btn) btn.textContent = "Transcribe with PostMeet";
      return;
    }

    chrome.runtime.sendMessage(
      {
        type: "UPLOAD_AND_TRANSCRIBE",
        videoId,
        audioUrl: audio.url,
        mimeType: audio.mimeType,
        youtubeUrl: location.href,
      },
      (resp) => {
        if (btn) btn.textContent = "Transcribe with PostMeet";
        if (resp?.error) {
          alert("PostMeet: " + resp.error);
        }
      }
    );
  };

  window.addEventListener("message", handler);
  window.postMessage({ type: "POSTMEET_GET_AUDIO" }, "*");

  // Timeout fallback
  setTimeout(() => {
    window.removeEventListener("message", handler);
    if (btn && btn.textContent === "Working…") {
      btn.textContent = "Transcribe with PostMeet";
      chrome.runtime.sendMessage({
        type: "OPEN_POSTMEET",
        videoId,
        youtubeUrl: location.href,
      });
    }
  }, 4000);
}

injectMainScript();

// YouTube is a SPA; re-inject on navigation
let lastUrl = location.href;
const observer = new MutationObserver(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    setTimeout(createButton, 800);
  }
});
observer.observe(document.body, { childList: true, subtree: true });

setTimeout(createButton, 1000);
