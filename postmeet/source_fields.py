#!/usr/bin/env python3
"""Canonical source-field projection for PostMeet.

PostMeet resolves media before it understands a meeting.  The media resolver is
intentionally small, but a publish target such as a Vlog/YOOtheme template may
already expose richer source fields (channel, thumbnail, description, publish
date, etc.).  This adapter preserves those facts as data so downstream template
hydration does not have to scrape the source again or invent values.

For YouTube-like sources we ask yt-dlp for metadata only (never the media bytes).
For every other provider the semantic ``source_media`` descriptor remains the
source of truth.
"""
from __future__ import annotations

import datetime as _dt
import json
import shutil
import subprocess
from typing import Any, Dict, Mapping, Optional


YTDLP_FIELDS = (
    "id", "title", "description", "thumbnail", "duration", "timestamp",
    "release_timestamp", "upload_date", "live_status", "channel", "channel_id",
    "channel_url", "uploader", "uploader_id", "uploader_url", "view_count",
    "like_count", "comment_count", "tags", "categories", "license",
    "webpage_url", "original_url",
)


def _ytdlp(url: str) -> Dict[str, Any]:
    exe = shutil.which("yt-dlp")
    if not exe or not url:
        return {}
    try:
        proc = subprocess.run(
            [exe, "--dump-single-json", "--skip-download", "--no-warnings",
             "--no-playlist", url],
            capture_output=True, text=True, timeout=90,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return {}
        data = json.loads(proc.stdout)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _iso_timestamp(value: Any) -> str:
    try:
        if value in (None, ""):
            return ""
        return _dt.datetime.fromtimestamp(float(value), tz=_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def _upload_date(value: Any) -> str:
    raw = str(value or "").strip()
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw


def duration_label(seconds: Any) -> str:
    try:
        total = max(0, int(round(float(seconds))))
    except (TypeError, ValueError):
        return ""
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def from_metadata(source_media: Mapping[str, Any], metadata: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Build the bounded, template-facing source field set.

    ``metadata`` is injectable so tests and non-YouTube adapters can use the
    exact same projection without shelling out to yt-dlp.
    """
    media = dict(source_media or {})
    info = dict(metadata or {})

    channel = str(info.get("channel") or info.get("uploader") or media.get("creator") or "")
    canonical = str(info.get("webpage_url") or info.get("original_url") or media.get("canonical_ref") or media.get("input_ref") or "")
    seconds = info.get("duration")
    if seconds in (None, ""):
        seconds = media.get("duration_seconds")

    published_at = _iso_timestamp(info.get("release_timestamp") or info.get("timestamp"))
    upload_date = _upload_date(info.get("upload_date"))
    if not published_at:
        published_at = upload_date

    fields: Dict[str, Any] = {
        "provider": str(media.get("provider") or ""),
        "source_url": canonical,
        "video_url": canonical,
        "video_id": str(info.get("id") or ""),
        "video_title": str(info.get("title") or media.get("title") or ""),
        "description": str(info.get("description") or ""),
        "thumbnail": str(info.get("thumbnail") or ""),
        "duration_seconds": seconds,
        "duration": duration_label(seconds),
        "published_at": published_at,
        "upload_date": upload_date,
        "live_status": str(info.get("live_status") or ""),
        "channel": channel,
        "channel_name": channel,
        "channel_id": str(info.get("channel_id") or info.get("uploader_id") or ""),
        "channel_url": str(info.get("channel_url") or info.get("uploader_url") or ""),
        "uploader": str(info.get("uploader") or channel),
        "uploader_id": str(info.get("uploader_id") or ""),
        "uploader_url": str(info.get("uploader_url") or ""),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
        "tags": list(info.get("tags") or []),
        "categories": list(info.get("categories") or []),
        "license": str(info.get("license") or ""),
    }
    # Keep the object deterministic and JSON-safe while retaining explicit zero
    # counts. Empty strings/lists are useful because the template can declare a
    # field without us pretending a value exists.
    return fields


def extract(source_media: Mapping[str, Any], source_ref: str = "") -> Dict[str, Any]:
    media = dict(source_media or {})
    provider = str(media.get("provider") or "").lower()
    metadata: Dict[str, Any] = {}
    if provider == "youtube":
        raw = _ytdlp(str(source_ref or media.get("canonical_ref") or media.get("input_ref") or ""))
        metadata = {k: raw.get(k) for k in YTDLP_FIELDS if k in raw}
    return from_metadata(media, metadata)


def apply(payload: Dict[str, Any], source_media: Mapping[str, Any], source_ref: str = "") -> Dict[str, Any]:
    """Attach source fields and convenient canonical aliases to ``payload``.

    Existing meeting facts win.  Source metadata fills blanks; it never replaces
    a title/summary/poster that a later meeting specialist has established.
    """
    fields = extract(source_media, source_ref)
    payload["source_fields"] = fields

    aliases = {
        "poster": fields.get("thumbnail"),
        "duration": fields.get("duration"),
        "duration_seconds": fields.get("duration_seconds"),
        "channel": fields.get("channel"),
        "channel_name": fields.get("channel_name"),
        "channel_id": fields.get("channel_id"),
        "channel_url": fields.get("channel_url"),
        "video_id": fields.get("video_id"),
        "source_url": fields.get("source_url"),
        "source_title": fields.get("video_title"),
        "source_description": fields.get("description"),
        "source_published_at": fields.get("published_at"),
        "source_provider": fields.get("provider"),
    }
    for key, value in aliases.items():
        if payload.get(key) in (None, "", []):
            if value not in (None, "", []):
                payload[key] = value
    return fields
