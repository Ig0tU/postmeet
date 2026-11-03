# PostMeet Chrome Extension

One-click YouTube → transcript pipeline for PostMeet.

The extension runs inside your browser session, so it can read the audio stream that the server-side YouTube fetch cannot reach.

## Install (developer mode)

1. Clone or download this repo.
2. Open `chrome://extensions` (or `edge://extensions`, `brave://extensions`).
3. Enable **Developer mode**.
4. Click **Load unpacked** and select the `extension/` folder.
5. Open any YouTube video. A **Transcribe with PostMeet** button appears under the title.

## How it works

1. Content script injects the button on YouTube watch pages.
2. On click, a main-world script reads `ytInitialPlayerResponse` and picks the best audio-only stream.
3. The background worker fetches that stream (using your browser session) and either:
   - Sends it to PostMeet for transcription (files under ~4.5 MB), or
   - Opens PostMeet with the YouTube URL pre-filled so you can finish the flow.
4. The finished meeting page is available on PostMeet.

## Notes

- Works on public videos you can play in the browser.
- Age-restricted or login-only videos may still fail if the stream URL requires a signature the page has not yet deciphered.
- For large files, the extension falls back to opening the PostMeet page so the existing Blob upload path can be used.

## Future

- Direct Blob upload of large files from the extension.
- Access-key storage in the extension so authenticated users skip the web login.
