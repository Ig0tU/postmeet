# PostMeet

PostMeet is the standalone post-meeting evidence pipeline extracted from SignalMesh's Meeting Lens implementation.

It turns timestamped meeting evidence into a validated canonical payload and hydrates that payload into a YOOtheme layout. SignalMesh is not required for the core transformation.

## Current pipeline

```text
transcript/evidence
      ↓
  extraction
      ↓
 canonical payload
      ↓
   validation
      ↓
 YOOtheme preset
      ↓
   layout.json
```

The canonical payload preserves agenda, resource and chapter records, including evidence fields and verbatim motion/vote text. Validation blocks public closed/executive status, malformed records, missing chapter timestamps, orphan agenda parents and missing retention metadata.

## CLI

```bash
pip install -e .
postmeet validate examples/sample_payload.json
postmeet hydrate examples/sample_payload.json --preset presets/meeting_lens_full.json -o layout.json
```

## Architecture

- `postmeet/extraction.py` — deterministic transcript → agenda/outcomes extraction
- `postmeet/validation.py` — acceptance gate
- `postmeet/hydration.py` — canonical payload → YOOtheme layout projection
- `schema/meeting_lens_payload.json` — payload contract
- `presets/meeting_lens_full.json` — Meeting Lens YOOtheme preset

SignalMesh can later sit outside this package as an orchestration/transport adapter. The PostMeet core remains usable without a mesh, vector database, Joomla runtime or external agent catalogue.

## Provenance

The core validation, hydration contract and YOOtheme preset are extracted from the working Meeting Lens implementation in `Ig0tU/SignalMesh` at commit `ae5ef377236584bc1eb0e172303e121ad8fe6a17`.
