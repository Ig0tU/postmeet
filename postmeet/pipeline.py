"""Production-oriented end-to-end PostMeet pipeline."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from .media_ref import resolve
from .asr import transcribe
from .extraction import build_payload
from .validation import validate
from .hydration import hydrate
from .render import render
from .source_fields import apply as apply_source, extract as extract_source


def run(source: str, *, site_url: str = "", media_root: str = "", model: str = "", brand: dict | None = None,
        output_dir: str = "postmeet-output", preset_path: str = "presets/meeting_lens_full.json"):
    out = Path(output_dir).expanduser().resolve(); out.mkdir(parents=True, exist_ok=True)
    media = resolve(source, site_url=site_url, media_root=media_root)
    source_fields = extract_source(media, source)
    if source_fields.get("video_title"):
        media["title"] = source_fields["video_title"]
    if source_fields.get("video_url"):
        media["public_ref"] = source_fields["video_url"]
        media["canonical_ref"] = source_fields["video_url"]

    if brand is None and site_url:
        try:
            from .brand import extract as extract_brand
            brand = extract_brand(site_url)
        except Exception:
            brand = {}

    asr = transcribe(media["resolved_ref"], model=model)
    if not asr.get("cues"):
        raise RuntimeError(asr.get("error") or "PostMeet could not obtain a timestamped transcript.")

    payload = build_payload(
        meeting_key=media.get("canonical_ref") or source,
        title=media.get("title") or "Post-Meeting Record",
        transcript=asr["text"],
        recording_url=media.get("public_ref") or media.get("resolved_ref") or source,
        meeting_status="complete",
        retention={"correlation_id": media.get("canonical_ref") or source,
                   "stored_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                   "stages_complete": ["media", "transcribe", "extract"]},
    )
    payload["transcript_text"] = asr["text"]
    payload["source_media"] = media
    payload["source_fields"] = source_fields
    if brand: payload["brand"] = brand
    apply_source(payload, media, source)

    report = validate(payload)
    (out / "payload.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "validation.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if not report.get("ok"):
        raise ValueError("PostMeet validation failed: " + "; ".join(d["msg"] for d in report.get("defects", [])))

    preset = Path(preset_path).expanduser()
    if not preset.exists():
        preset = Path(__file__).resolve().parent.parent / "presets" / "meeting_lens_full.json"
    if not preset.is_file():
        raise FileNotFoundError(f"YOOtheme preset not found: {preset}")
    layout = hydrate(json.loads(preset.read_text(encoding="utf-8")), payload)
    (out / "layout.json").write_text(json.dumps(layout, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "meeting.html").write_text(render(payload), encoding="utf-8")
    manifest = {"version": 1, "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "source": source, "outputs": {"payload": "payload.json", "validation": "validation.json", "layout": "layout.json", "html": "meeting.html"},
                "counts": {"items": len(payload.get("items", [])), "agenda": report.get("agenda_count", 0), "chapters": report.get("chapter_count", 0)}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"output_dir": str(out), "media": media, "asr": asr, "validation": report,
            "payload": str(out / "payload.json"), "layout": str(out / "layout.json"), "html": str(out / "meeting.html"), "manifest": str(out / "manifest.json")}
