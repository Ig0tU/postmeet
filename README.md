# PostMeet

**PostMeet** turns a meeting recording or timestamped transcript into an evidence-bound, publication-ready meeting page and YOOtheme layout.

The core is standalone. SignalMesh is optional orchestration/transport and is not required to run PostMeet.

## What it does

```text
recording / YouTube / Vimeo / transcript
                ↓
        media + captions
                ↓
      local Whisper ASR fallback
                ↓
       evidence extraction
                ↓
       canonical payload
                ↓
          validation gate
             ↙       ↘
       YOOtheme JSON    read-only HTML
```

PostMeet deliberately fails closed when it cannot obtain a usable timestamped transcript. It does not manufacture meeting facts, motions, votes, or timestamps.

## Install

Basic package:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

For real recordings/online sources, install the full runtime:

```bash
python -m pip install -e '.[all]'
```

`ffmpeg` is required for audio extraction. `yt-dlp` is used for YouTube/Vimeo acquisition and captions. `faster-whisper` provides local CPU ASR when captions are unavailable.

## Run a meeting

From a local recording:

```bash
postmeet run ./meeting.mp4 --output-dir ./postmeet-output
```

From a YouTube/Vimeo URL:

```bash
postmeet run 'https://www.youtube.com/watch?v=VIDEO_ID' \
  --site-url 'https://example.org' \
  --output-dir ./postmeet-output
```

Use a larger/smaller local Whisper model when needed:

```bash
postmeet run ./meeting.mp4 --model small --output-dir ./postmeet-output
```

The run produces:

- `payload.json` — canonical evidence payload
- `validation.json` — acceptance/defect report
- `layout.json` — hydrated YOOtheme layout
- `meeting.html` — standalone read-only HTML rendering
- `manifest.json` — generated-output/provenance manifest

## Existing transcript/caption files

PostMeet can ingest timestamped `.txt`, `.srt`, and `.vtt` files without ASR:

```bash
postmeet run ./meeting.vtt --output-dir ./postmeet-output
```

A timestamped text file uses:

```text
00:03 - Call to order
00:12 - I move to approve the agenda.
00:20 - Motion carries.
```

## Individual stages

Validate an existing payload:

```bash
postmeet validate payload.json
```

Hydrate the official Meeting Lens preset:

```bash
postmeet hydrate payload.json \
  --preset presets/meeting_lens_full.json \
  -o layout.json
```

Render an existing payload:

```bash
postmeet render payload.json -o meeting.html
```

## Configuration

Environment variables:

- `POSTMEET_WHISPER_MODEL` — default `small`
- `POSTMEET_WHISPER_DEVICE` — default `cpu`
- `POSTMEET_WHISPER_COMPUTE` — default `int8`
- `POSTMEET_WHISPER_LANG` — optional language code
- `POSTMEET_WHISPER_BIN` — optional Whisper CLI executable
- `POSTMEET_ALLOW_PRIVATE_URLS=1` — explicitly allow private media URLs; leave unset in production

The default network policy rejects localhost/private/link-local media references. A configured `site_url` may authorize media hosted on that same hostname.

## YOOtheme / Joomla

`presets/meeting_lens_full.json` is the extracted Meeting Lens YOOtheme layout preset. `layout.json` is the hydrated page representation intended for import/processing by the surrounding Joomla/YOOtheme deployment workflow.

PostMeet itself does not require Joomla at runtime, which makes it suitable for CI, scheduled ingestion, a worker container, or a Joomla-side integration.

## Production container

Build:

```bash
docker build -t postmeet .
```

Run:

```bash
docker run --rm -v "$PWD:/work" postmeet run /work/meeting.mp4 --output-dir /work/postmeet-output
```

The container is CPU-first and includes `ffmpeg` plus the Python runtime dependencies.

## Evidence model

Agenda records retain their source evidence and confidence. Motion/second/vote text is preserved as evidence rather than rewritten prose. Validation rejects malformed or ambiguous publication states and requires retention metadata before a payload is accepted.

## Provenance

The core contract and Meeting Lens preset were extracted from the working SignalMesh implementation at commit `ae5ef377236584bc1eb0e172303e121ad8fe6a17`. PostMeet then separates those capabilities into a provider-independent package.

## Status

PostMeet 1.0.0 is intended to be directly runnable as a standalone Python package. SignalMesh integration remains optional by design.
