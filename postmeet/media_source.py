"""Source-agnostic media resolution for SignalMesh capabilities.

A URL is an address, not a media type. This resolver turns whatever the user
points at into a small evidence-bearing media object before a capability such as
Meeting Lens decides what to do with it. It prefers metadata/stream discovery;
it does not copy an entire video into the SignalMesh context layer.
"""
from __future__ import annotations

import html as _html
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx
from .playback import ensure_playback, extract_youtube_id

MEDIA_EXT = {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi",
             ".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac", ".wma"}


def _provider(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if extract_youtube_id(url):
        return "youtube"
    if host.endswith("vimeo.com"):
        return "vimeo"
    if host.endswith(("drive.google.com", "drive.usercontent.google.com")):
        return "google_drive"
    if host.endswith("loom.com"):
        return "loom"
    if host.endswith("facebook.com") or host.endswith("fb.watch"):
        return "facebook"
    return "web"


def _kind_from_ref(ref: str) -> str:
    ext = Path(urlsplit(ref).path).suffix.lower()
    if ext in MEDIA_EXT:
        return "audio" if ext in {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac", ".wma"} else "video"
    return "unknown"


def _ytdlp_info(url: str) -> Optional[Dict[str, Any]]:
    exe = shutil.which("yt-dlp")
    if not exe:
        return None
    try:
        p = subprocess.run(
            [exe, "--dump-single-json", "--skip-download", "--no-warnings",
             "--no-playlist", url],
            capture_output=True, text=True, timeout=90,
        )
        if p.returncode != 0 or not p.stdout.strip():
            return None
        data = json.loads(p.stdout)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _google_drive_direct(url: str) -> str:
    """Best-effort public Drive share -> download address; auth stays external."""
    p = urlsplit(url)
    if "drive.google.com" not in (p.hostname or "").lower():
        return ""
    m = re.search(r"/file/d/([^/]+)", p.path)
    file_id = m.group(1) if m else (parse_qs(p.query).get("id") or [""])[0]
    if not file_id:
        return ""
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def _read_page(url: str, limit: int = 2_000_000) -> tuple[str, str, str]:
    """Return (final_url, content_type, capped text). Never downloads the video."""
    try:
        headers = {"User-Agent": "SignalMesh-MediaResolver/1.0",
                   "Accept": "text/html,application/xhtml+xml,video/*,audio/*;q=.8,*/*;q=.2"}
        with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=25) as r:
            ctype = (r.headers.get("content-type") or "").lower()
            final = str(r.url)
            if ctype.startswith(("video/", "audio/")):
                return final, ctype, ""
            if "html" not in ctype and "xml" not in ctype and ctype:
                return final, ctype, ""
            buf = bytearray()
            for chunk in r.iter_bytes():
                if not chunk:
                    continue
                take = min(len(chunk), limit - len(buf))
                buf.extend(chunk[:take])
                if len(buf) >= limit:
                    break
            return final, ctype, bytes(buf).decode("utf-8", "replace")
    except Exception:
        return url, "", ""


def _attr(tag: str, name: str) -> str:
    m = re.search(rf"\b{name}\s*=\s*([\"'])(.*?)\1", tag, re.I | re.S)
    return _html.unescape(m.group(2).strip()) if m else ""


def _discover_in_html(page_url: str, text: str) -> Dict[str, str]:
    title = ""
    for rx in (
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=(["\'])(.*?)\1',
        r'<meta[^>]+content=(["\'])(.*?)\1[^>]+property=["\']og:title["\']',
        r'<title[^>]*>(.*?)</title>',
    ):
        m = re.search(rx, text, re.I | re.S)
        if m:
            title = _html.unescape((m.group(2) if m.lastindex and m.lastindex > 1 else m.group(1)).strip())
            title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", title)).strip()
            break

    candidates = []
    for tag in re.findall(r"<meta\b[^>]*>", text, re.I | re.S):
        prop = (_attr(tag, "property") or _attr(tag, "name")).lower()
        if prop in {"og:video", "og:video:url", "og:video:secure_url", "twitter:player", "twitter:player:stream"}:
            u = _attr(tag, "content")
            if u:
                candidates.append(u)
    for tag in re.findall(r"<(?:video|source|iframe)\b[^>]*>", text, re.I | re.S):
        u = _attr(tag, "src")
        if u:
            candidates.append(u)
    for rx in (r'["\']contentUrl["\']\s*:\s*["\']([^"\']+)',
               r'["\']embedUrl["\']\s*:\s*["\']([^"\']+)'):
        candidates.extend(re.findall(rx, text, re.I))

    for raw in candidates:
        u = urljoin(page_url, _html.unescape(raw.replace("\\/", "/")))
        if u.startswith(("http://", "https://")):
            return {"candidate": u, "title": title}
    return {"candidate": "", "title": title}


def inspect(source: str, *, site_url: str = "", expected_role: str = "",
            _depth: int = 0) -> Dict[str, Any]:
    """Resolve an address into a bounded semantic media descriptor."""
    raw = (source or "").strip()
    if not raw:
        raise ValueError("a media source is required")

    p = Path(raw)
    if p.exists():
        kind = _kind_from_ref(str(p))
        return {
            "input_ref": raw, "working_ref": str(p), "canonical_ref": str(p),
            "provider": "local_file", "media_kind": kind,
            "title": p.stem, "creator": "", "duration_seconds": None,
            "strategy": "direct_media", "expected_role": expected_role,
            "meeting_candidate": expected_role == "board_meeting" and kind in {"video", "audio"},
            "provenance": ["local_path"],
        }

    if not raw.startswith(("http://", "https://")) and site_url:
        raw = site_url.rstrip("/") + "/" + raw.lstrip("/")

    if not raw.startswith(("http://", "https://")):
        return {
            "input_ref": source, "working_ref": raw, "canonical_ref": raw,
            "provider": "site_media", "media_kind": _kind_from_ref(raw),
            "title": Path(urlsplit(raw).path).stem, "creator": "", "duration_seconds": None,
            "strategy": "direct_media", "expected_role": expected_role,
            "meeting_candidate": expected_role == "board_meeting",
            "provenance": ["site_relative_reference"],
        }

    provider = _provider(raw)
    direct_kind = _kind_from_ref(raw)
    if direct_kind != "unknown":
        return {
            "input_ref": source, "working_ref": raw, "canonical_ref": raw,
            "provider": provider if provider != "web" else "direct_http",
            "media_kind": direct_kind, "title": Path(urlsplit(raw).path).stem,
            "creator": "", "duration_seconds": None, "strategy": "direct_media",
            "expected_role": expected_role,
            "meeting_candidate": expected_role == "board_meeting",
            "provenance": ["url_extension"],
        }

    if extract_youtube_id(raw):
        projected = {"recording_url": raw}
        playback = ensure_playback(projected)
        return {
            "input_ref": source, "working_ref": raw, "canonical_ref": playback["youtube_url"],
            "provider": "youtube", "media_kind": "video", "title": playback["title"],
            "youtube_url": playback["youtube_url"], "playback": playback,
            "source_fields": projected["source_fields"], "creator": "", "duration_seconds": None,
            "strategy": "captions_then_platform_audio", "expected_role": expected_role,
            "meeting_candidate": expected_role == "board_meeting",
            "provenance": ["canonical_youtube_metadata"],
        }

    info = _ytdlp_info(raw)
    if info:
        vcodec = str(info.get("vcodec") or "")
        acodec = str(info.get("acodec") or "")
        kind = "video" if vcodec not in ("", "none") else ("audio" if acodec not in ("", "none") else "media")
        canonical = str(info.get("webpage_url") or info.get("original_url") or raw)
        extractor = str(info.get("extractor_key") or info.get("extractor") or provider)
        media = {
            "input_ref": source, "working_ref": raw, "canonical_ref": canonical,
            "provider": provider if provider != "web" else extractor.lower(),
            "media_kind": kind,
            "title": str(info.get("title") or ""),
            "creator": str(info.get("channel") or info.get("uploader") or ""),
            "duration_seconds": info.get("duration"),
            "strategy": "captions_then_platform_audio",
            "expected_role": expected_role,
            "meeting_candidate": expected_role == "board_meeting" and kind in {"video", "audio", "media"},
            "provenance": ["yt_dlp_metadata", f"extractor:{extractor}"],
        }
        if extract_youtube_id(canonical):
            playback = ensure_playback({"source_media": media})
            media.update(playback=playback, youtube_url=playback["youtube_url"],
                         title=playback["title"], provider="youtube")
        return media

    final, ctype, page = _read_page(raw)
    if ctype.startswith("video/") or ctype.startswith("audio/"):
        kind = "video" if ctype.startswith("video/") else "audio"
        return {
            "input_ref": source, "working_ref": final, "canonical_ref": final,
            "provider": provider if provider != "web" else "direct_http",
            "media_kind": kind, "title": Path(urlsplit(final).path).stem,
            "creator": "", "duration_seconds": None, "strategy": "direct_media",
            "expected_role": expected_role, "meeting_candidate": expected_role == "board_meeting",
            "provenance": [f"content_type:{ctype}"],
        }

    found = _discover_in_html(final, page) if page else {"candidate": "", "title": ""}
    if found["candidate"] and _depth < 2 and found["candidate"] != raw:
        child = inspect(found["candidate"], site_url=site_url, expected_role=expected_role,
                        _depth=_depth + 1)
        child["input_ref"] = source
        child.setdefault("provenance", []).insert(0, f"discovered_from:{final}")
        if not child.get("title") and found.get("title"):
            child["title"] = found["title"]
        return child

    drive = _google_drive_direct(raw)
    working = drive or raw
    return {
        "input_ref": source, "working_ref": working, "canonical_ref": final or raw,
        "provider": provider, "media_kind": "unknown_page",
        "title": found.get("title", ""), "creator": "", "duration_seconds": None,
        "strategy": "platform_or_page_probe",
        "expected_role": expected_role,
        "meeting_candidate": expected_role == "board_meeting",
        "provenance": ["html_probe"] + (["google_drive_download_candidate"] if drive else []),
    }
