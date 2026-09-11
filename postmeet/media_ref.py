"""media_ref.py — arbitrary source reference -> a grounded media candidate.

A meeting recording is not a file type. It may be a direct MP4, a YouTube or
Vimeo page, a public Drive share, a council page containing an iframe, or a
relative Joomla media path. This module resolves transport only. It never
claims the content is actually a board meeting; Meeting Lens validation decides
that from the evidence after transcription.

The important contract is that downstream code receives a canonical media
reference and provenance instead of having to know which platform supplied it.
yt-dlp is used as the broad extractor when available; a small HTML discovery
fallback handles ordinary pages containing <video>/<source>/<iframe> media.
"""
from __future__ import annotations

import ipaddress
import os
import re
import socket
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.parse import urljoin, urlparse

MEDIA_EXT = {
    ".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi",
    ".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac", ".wma",
}

_MEETING_TERMS = {
    "board meeting": 9.0, "regular meeting": 8.0, "special meeting": 8.0,
    "council meeting": 8.0, "commission meeting": 8.0,
    "committee meeting": 7.0, "school board": 7.0,
    "board of education": 7.0, "public hearing": 6.0, "work session": 6.0,
    "business meeting": 5.0, "meeting": 4.0, "board": 3.0, "council": 3.0,
    "committee": 3.0, "commission": 3.0, "trustees": 3.0, "hearing": 3.0,
    "session": 2.0, "agenda": 2.0, "congress": 2.0, "senate": 2.0,
}
_NEGATIVE_TERMS = {
    "trailer": -5.0, "promo": -4.0, "commercial": -5.0,
    "highlight": -3.0, "shorts": -4.0, "music video": -5.0, "recap": -2.0,
}


def _is_http(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def _mediaish_url(value: str) -> bool:
    try:
        return Path(urlparse(value).path).suffix.lower() in MEDIA_EXT
    except Exception:
        return False


def _same_host(a: str, b: str) -> bool:
    try:
        return bool(a and b and urlparse(a).hostname and
                    urlparse(a).hostname == urlparse(b).hostname)
    except Exception:
        return False


def _private_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").strip().lower()
    if not host:
        return False
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return True
    return False


def _guard_url(url: str, site_url: str = "") -> None:
    if not _is_http(url):
        raise ValueError("Only http(s) media references may be fetched remotely.")
    if os.environ.get("MEETING_ALLOW_PRIVATE_URLS", "").lower() in {"1", "true", "yes"}:
        return
    if site_url and _same_host(url, site_url):
        return
    if _private_host(url):
        raise ValueError("That media URL resolves to a private/local network address.")


def extract_youtube_id(url: str) -> str | None:
    """Extract canonical 11-character YouTube ID from various URL formats.

    Supports:
    - https://www.youtube.com/watch?v=<id>
    - https://youtu.be/<id>
    - https://www.youtube.com/embed/<id>
    - https://www.youtube-nocookie.com/embed/<id>
    - https://www.youtube.com/shorts/<id>
    - https://www.youtube.com/v/<id>
    - Bare/direct YouTube ID string
    """
    u = (url or "").strip()
    if not u:
        return None
    patterns = [
        r"(?:https?://)?(?:www\.)?youtube\.com/watch\?(?:.*&)?v=([A-Za-z0-9_-]{11})",
        r"(?:https?://)?(?:www\.)?youtube(?:-nocookie)?\.com/embed/([A-Za-z0-9_-]{11})",
        r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([A-Za-z0-9_-]{11})",
        r"(?:https?://)?(?:www\.)?youtube\.com/v/([A-Za-z0-9_-]{11})",
        r"(?:https?://)?youtu\.be/([A-Za-z0-9_-]{11})",
        r"^([A-Za-z0-9_-]{11})$",
    ]
    for pattern in patterns:
        m = re.search(pattern, u)
        if m:
            return m.group(1)
    return None


def normalize_url(url: str) -> str:
    """Normalize malformed YouTube or media URLs."""
    u = (url or "").strip()
    yt_id = extract_youtube_id(u)
    if yt_id and not _mediaish_url(u):
        return f"https://www.youtube.com/watch?v={yt_id}"
    return u


def normalize(source: str, *, site_url: str = "", media_root: str = "") -> str:
    s = normalize_url(source)
    if not s:
        raise ValueError("A meeting recording or page URL is required.")
    if _is_http(s):
        _guard_url(s, site_url)
        return s
    if media_root:
        root = Path(media_root).expanduser().resolve()
        candidate = (root / s.lstrip("/")).resolve()
        try:
            inside = candidate.is_relative_to(root)
        except AttributeError:
            inside = str(candidate).startswith(str(root) + os.sep)
        if inside and candidate.is_file():
            return str(candidate)
    if site_url:
        url = urljoin(site_url.rstrip("/") + "/", s.lstrip("/"))
        _guard_url(url, site_url)
        return url
    p = Path(s).expanduser()
    if p.is_file():
        return str(p.resolve())
    raise ValueError(f"Could not resolve a recording at {s!r}.")


def _score(meta: Dict[str, Any]) -> float:
    text = " ".join(str(meta.get(k) or "") for k in
                    ("title", "description", "channel", "uploader", "webpage_url")).lower()
    score = sum(weight for term, weight in _MEETING_TERMS.items() if term in text)
    score += sum(weight for term, weight in _NEGATIVE_TERMS.items() if term in text)
    try:
        duration = float(meta.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration >= 20 * 60:
        score += 2.0
    if duration >= 60 * 60:
        score += 2.0
    if duration >= 3 * 60 * 60:
        score += 1.0
    return round(score, 3)


def _flatten(info: Any) -> Iterable[Dict[str, Any]]:
    if not isinstance(info, dict):
        return
    entries = info.get("entries")
    if entries:
        for entry in entries:
            if entry:
                yield from _flatten(entry)
        return
    yield info


def _candidate_ref(meta: Dict[str, Any], fallback: str) -> str:
    for key in ("webpage_url", "original_url", "url"):
        value = str(meta.get(key) or "").strip()
        if _is_http(value):
            return value
    return fallback


def _yt_candidates(url: str) -> List[Dict[str, Any]]:
    try:
        import yt_dlp  # type: ignore
    except ImportError:
        return []
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "extract_flat": False, "noplaylist": False, "socket_timeout": 20}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for meta in _flatten(info):
        ref = _candidate_ref(meta, url)
        out.append({
            "resolved_ref": ref,
            "canonical_ref": str(meta.get("webpage_url") or ref),
            "title": str(meta.get("title") or "").strip(),
            "description": str(meta.get("description") or "")[:1200],
            "provider": str(meta.get("extractor_key") or meta.get("extractor") or "yt-dlp"),
            "duration": meta.get("duration") or 0,
            "thumbnail": str(meta.get("thumbnail") or ""),
            "kind": "platform_media",
            "meeting_score": _score(meta),
        })
    return out


class _MediaHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        candidates: List[str] = []
        if tag in {"video", "audio", "source", "iframe"}:
            candidates.extend([a.get("src", ""), a.get("data-src", "")])
        elif tag == "a":
            candidates.append(a.get("href", ""))
        elif tag == "meta" and a.get("property", "").lower() in {
            "og:video", "og:video:url", "og:video:secure_url",
        }:
            candidates.append(a.get("content", ""))
        for value in candidates:
            value = value.strip()
            if not value:
                continue
            low = value.lower()
            if (_mediaish_url(value) or "youtube.com" in low or "youtu.be" in low or
                    "vimeo.com" in low or "drive.google.com" in low or
                    "streamable.com" in low or "wistia" in low):
                self.refs.append(value)


def _html_candidates(url: str, site_url: str = "") -> List[Dict[str, Any]]:
    try:
        import httpx
        with httpx.Client(follow_redirects=True, timeout=20,
                          headers={"User-Agent": "SignalMesh-MediaRef/1.0"}) as client:
            r = client.get(url)
            r.raise_for_status()
            ctype = (r.headers.get("content-type") or "").lower()
            if ctype.startswith(("video/", "audio/")):
                return [{"resolved_ref": str(r.url), "canonical_ref": str(r.url),
                         "title": Path(urlparse(str(r.url)).path).name,
                         "description": "", "provider": "http", "duration": 0,
                         "thumbnail": "", "kind": "direct_media", "meeting_score": 0.0}]
            text = r.text[:2_000_000]
            base = str(r.url)
    except Exception:
        return []
    parser = _MediaHTML()
    try:
        parser.feed(text)
    except Exception:
        pass
    out: List[Dict[str, Any]] = []
    seen = set()
    for raw in parser.refs[:40]:
        ref = urljoin(base, raw)
        if ref in seen:
            continue
        seen.add(ref)
        try:
            _guard_url(ref, site_url)
        except ValueError:
            continue
        meta_candidates = _yt_candidates(ref)
        if meta_candidates:
            out.extend(meta_candidates)
            continue
        out.append({"resolved_ref": ref, "canonical_ref": ref,
                    "title": Path(urlparse(ref).path).name, "description": "",
                    "provider": "html-discovery", "duration": 0, "thumbnail": "",
                    "kind": "embedded_media", "meeting_score": 0.0})
    return out


def resolve(source: str, *, site_url: str = "", media_root: str = "") -> Dict[str, Any]:
    normalized = normalize(source, site_url=site_url, media_root=media_root)
    if not _is_http(normalized):
        return {"original_ref": source, "resolved_ref": normalized,
                "canonical_ref": normalized, "public_ref": "",
                "title": Path(normalized).stem, "provider": "local", "duration": 0,
                "kind": "local_media", "candidate_count": 1, "meeting_score": 0.0,
                "selection_reason": "local media path"}
    _guard_url(normalized, site_url)
    if _mediaish_url(normalized):
        return {"original_ref": source, "resolved_ref": normalized,
                "canonical_ref": normalized, "public_ref": normalized,
                "title": Path(urlparse(normalized).path).stem, "provider": "http",
                "duration": 0, "kind": "direct_media", "candidate_count": 1,
                "meeting_score": 0.0, "selection_reason": "direct media URL"}
    candidates = _yt_candidates(normalized)
    if not candidates:
        candidates = _html_candidates(normalized, site_url=site_url)
    if not candidates:
        return {"original_ref": source, "resolved_ref": normalized,
                "canonical_ref": normalized, "public_ref": normalized, "title": "",
                "provider": "web", "duration": 0, "kind": "web_page_candidate",
                "candidate_count": 1, "meeting_score": 0.0,
                "selection_reason": "page retained for downstream extractor"}
    ranked = sorted(candidates, key=lambda c: (
        float(c.get("meeting_score") or 0), float(c.get("duration") or 0)), reverse=True)
    chosen = dict(ranked[0])
    chosen.update({"original_ref": source,
                   "public_ref": chosen.get("canonical_ref") or chosen.get("resolved_ref"),
                   "candidate_count": len(ranked),
                   "selection_reason": ("highest board/meeting semantic score, then duration"
                                        if len(ranked) > 1 else
                                        "single discovered media candidate")})
    return chosen
