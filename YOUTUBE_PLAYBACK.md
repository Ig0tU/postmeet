# Canonical YouTube playback

## Contract

`postmeet.playback.ensure_playback(payload)` selects recording-source metadata (not agenda/resource links), resolves the exact YouTube title using bounded HTTPS oEmbed with a bounded yt-dlp fallback, and persists:

- `provider`
- `youtube_url`
- `video_id`
- `title`
- `embed_url` — `https://www.youtube.com/embed/<real-video-id>`
- `recording_url`

The descriptor is mirrored at `payload.playback`, `source_media.playback`, `source_fields.playback` and flattened source fields. Local `resolved_ref` / `working_ref` stay processing assets. An editorial meeting title is independent of the exact playback title.

A complete matching descriptor is reusable offline. Missing/unresolvable metadata fails publication instead of inventing a title or falling back to local playback. Supported absolute URLs include watch, youtu.be, embed, shorts, live, and legacy /v/. Bare IDs/filenames and host lookalikes are rejected.

`render_playback` owns playback markup. Render, hydrate, injection and worker publication use this renderer. Generated iframe URLs are query-free; the existing browser provider adds `enablejsapi=1` and the document origin at runtime for API controls. Native-only sources keep native markup.

## Outputs and older integrations

- Pipeline payload, source models and manifest retain the descriptor.
- Standalone HTML and CLI/module render share the same renderer.
- YouTube-backed Meeting Lens layouts publish an actual YOOtheme `html` element containing the canonical meeting view. Merely adding a new property to an old custom element would allow an installed template to ignore it and keep its old player. Meeting records remain in the layout and rendered content.
- Custom HTML/media nodes are rewritten to the same iframe.
- Legacy HTML injection replaces every recognized recording player and media config.
- `postmeet.publication.finalize` normalizes legacy worker HTML, structured layouts, prepared variants and JSON-serialized bundles. The web proxy and direct-worker UI paths use this boundary before downloads appear.
- No separate ZIP generator, remote URL artifact downloader or Joomla runtime is present in this repository; those external systems are not covered by local verification.

The Next server needs `python3` and the PostMeet package at runtime for the publication endpoint, just as its local processing endpoint does. Browser-only/static or Node-only hosting must provide that runtime or deploy an equivalent updated Python publication service; it fails closed rather than serving stale worker output. This change does not deploy/update an external worker or Joomla installation.

## Verification (2026-09-12)

- 130 Python tests passed.
- 8 Node adapter tests passed (mocked route dependencies; Python finalizer tested separately).
- Real Chromium DOM verified 11 generated surfaces: pipeline HTML, render function, render CLI, render module, inject function, inject CLI, hydrated layout HTML export, custom layout, worker publication, prepared mobile HTML, JSON bundle HTML. Each used the resolved YouTube iframe/title and zero native video/audio/source elements.
- Print DOM retained the YouTube iframe; the native-only control retained its native video.
- Live YouTube oEmbed resolved `jNQXAC9IVRw` to `Me at the zoo`. This is a test input, never a runtime fallback or hard-coded production ID.
- Screenshots show the real embedded thumbnail/title. Processing used a clearly synthetic timestamped VTT fixture through the actual caption/extraction/validation/hydration/render pipeline, not a claimed transcript of that YouTube video.

Limitations: audible playback and live seek success were not verified (the embedded play-button check timed out). No live ASR/model inference, deployed worker or Joomla/YOOtheme host verification. Next production build blocked by registry HTTP 403 for `undici-types@6.21.0`; do not interpret passing adapter tests as a production build.

Reproduce:

```sh
python3 -m pytest -q
node --experimental-vm-modules --test tests/frontend-playback.test.mjs
python3 -m pip install playwright
python3 -m playwright install chromium
PYTHONPATH=. python3 tests/browser_verify.py --output /tmp/postmeet-evidence --youtube-url 'https://www.youtube.com/watch?v=YOUR_REAL_ID'
```

The browser test accepts arbitrary valid YouTube video URLs. Evidence includes per-surface actual iframe outerHTML, title, URL and native-element counts.
