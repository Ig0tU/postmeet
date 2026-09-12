"""Canonical public playback, separate from local processing media references.

``ensure_playback`` is the single payload normalization boundary. YouTube titles
are metadata, never meeting titles or filenames. Complete, internally consistent
YouTube descriptors can be serialized and reused offline for the same video ID.
Tests/adapters may patch ``resolve_youtube_title(youtube_url)`` or ``urlopen``.
"""
from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from typing import Any, Mapping
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_EMBED_HOSTS = _YOUTUBE_HOSTS | {"youtube-nocookie.com", "www.youtube-nocookie.com"}
_SHORT_HOSTS = {"youtu.be", "www.youtu.be"}
_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
OEMBED_TIMEOUT = 8
OEMBED_MAX_BYTES = 128 * 1024


class PlaybackMetadataError(ValueError):
    """A YouTube reference cannot be published without its exact source title."""


def extract_youtube_id(url: str) -> str | None:
    """Parse an absolute http(s) YouTube URL, never a bare ID/path/filename.

    Supports watch, youtu.be, embed (including legacy nocookie), shorts, live,
    and legacy /v/. Hostnames, path components and the entire ID are validated.
    """
    if not isinstance(url, str) or not url or any(c.isspace() or ord(c) < 32 for c in url):
        return None
    try:
        p = urlsplit(url)
        if p.scheme not in {"http", "https"} or p.username is not None or p.password is not None:
            return None
        if p.port not in (None, 80 if p.scheme == "http" else 443):
            return None
        host = (p.hostname or "").lower()
        path = p.path[:-1] if p.path.endswith("/") else p.path
        candidate = None
        if host in _SHORT_HOSTS and path.count("/") == 1:
            candidate = path[1:]
        elif host in _YOUTUBE_HOSTS and path == "/watch":
            values = parse_qs(p.query, keep_blank_values=True).get("v", [])
            if len(values) == 1:
                candidate = values[0]
        elif host in _EMBED_HOSTS:
            parts = path.split("/")
            allowed = {"embed", "shorts", "live", "v"} if host in _YOUTUBE_HOSTS else {"embed"}
            if len(parts) == 3 and parts[1] in allowed:
                candidate = parts[2]
        return candidate if candidate and _ID.fullmatch(candidate) else None
    except (ValueError, TypeError):
        return None


def resolve_youtube_title(youtube_url: str) -> str:
    """Fetch exact title via bounded stdlib HTTPS oEmbed, then bounded yt-dlp.

    Raises PlaybackMetadataError on unavailable/empty metadata. Patch this
    function for deterministic/offline tests; no global cache hides ID changes.
    """
    video_id = extract_youtube_id(youtube_url)
    if not video_id:
        raise PlaybackMetadataError("A valid absolute YouTube video URL is required.")
    canonical = f"https://www.youtube.com/watch?v={video_id}"
    endpoint = "https://www.youtube.com/oembed?" + urlencode({"url": canonical, "format": "json"})
    try:
        request = Request(endpoint, headers={"Accept": "application/json", "User-Agent": "PostMeet/1.0"})
        with urlopen(request, timeout=OEMBED_TIMEOUT) as response:
            raw = response.read(OEMBED_MAX_BYTES + 1)
        if len(raw) > OEMBED_MAX_BYTES:
            raise ValueError("oEmbed response exceeds size limit")
        info = json.loads(raw.decode("utf-8"))
        title = info.get("title") if isinstance(info, dict) else None
        if isinstance(title, str) and title.strip():
            return title
    except Exception:
        pass
    # Existing adapter is subprocess-bounded. Only a matching ID can supply title.
    from .source_fields import _ytdlp
    info = _ytdlp(canonical)
    if info.get("id") == video_id and isinstance(info.get("title"), str) and info["title"].strip():
        return info["title"]
    raise PlaybackMetadataError(f"YouTube metadata unavailable for {canonical}; exact video title is required (no filename or meeting-title fallback).")


def _youtube_descriptor(video_id: str, title: str) -> dict[str, str]:
    canonical = f"https://www.youtube.com/watch?v={video_id}"
    return {"provider": "youtube", "youtube_url": canonical, "video_id": video_id,
            "title": title, "embed_url": f"https://www.youtube.com/embed/{video_id}",
            "recording_url": canonical}


def _verified(descriptor: Any, video_id: str) -> bool:
    if not isinstance(descriptor, Mapping):
        return False
    title = descriptor.get("title")
    if not isinstance(title, str) or not title.strip():
        return False
    expected = _youtube_descriptor(video_id, title)
    return all(descriptor.get(k) == v for k, v in expected.items())


def _walk(data: Any):
    """Visit recording/source containers only, never agenda/resource references.

    Mesh envelopes may nest a source descriptor; supplemental items, brand data
    and arbitrary URL-bearing dictionaries are not playback associations.
    """
    containers = {"source_media", "source_fields", "source", "media", "mesh",
                  "source_model", "source_descriptor", "recording", "payload",
                  "data", "metadata", "playback"}
    seen = set()
    stack = [data]
    while stack:
        node = stack.pop()
        if not isinstance(node, Mapping) or id(node) in seen:
            continue
        seen.add(id(node))
        yield node
        stack.extend(reversed([value for key, value in node.items()
                               if key in containers and isinstance(value, Mapping)]))


def ensure_playback(payload: dict[str, Any]) -> dict[str, str]:
    """Resolve and persist one descriptor in payload, source_media, source_fields.

    Explicit legacy youtube_url (even nested) wins over recording/source refs.
    Local resolved_ref/working_ref are untouched. A complete canonical descriptor
    is reusable offline only when all six fields match the selected video's ID.
    Non-YouTube payloads do not perform metadata requests and retain native media.
    """
    nodes = list(_walk(payload))
    # Descriptors are caches, not overrides of an explicitly changed source URL.
    descriptors = [n.get("playback") for n in nodes if isinstance(n.get("playback"), Mapping)]
    descriptor_ids = {id(d) for d in descriptors}
    surfaces = [n for n in nodes if id(n) not in descriptor_ids]
    candidates = [n.get("youtube_url") for n in surfaces if n.get("youtube_url")]
    explicit = candidates[0] if candidates else None
    video_id = extract_youtube_id(explicit) if explicit else None
    if explicit and not video_id:
        raise PlaybackMetadataError(f"Invalid YouTube URL: {explicit!r}; expected an absolute YouTube video URL with an exact 11-character ID.")
    ref_keys = ("recording_url", "canonical_ref", "source_url", "video_url", "public_ref", "input_ref", "original_ref", "source", "url", "resolved_ref", "working_ref", "embed_url")
    if not video_id:
        for key in ref_keys:
            for node in surfaces:
                video_id = extract_youtube_id(node.get(key))
                if video_id:
                    break
            if video_id:
                break
    if not video_id:
        for descriptor in descriptors:
            candidate_id = extract_youtube_id(descriptor.get("youtube_url"))
            if candidate_id and _verified(descriptor, candidate_id):
                video_id = candidate_id
                break
    if video_id:
        cached = next((d for d in descriptors if _verified(d, video_id)), None)
        title = cached["title"] if cached else resolve_youtube_title(f"https://www.youtube.com/watch?v={video_id}")
        if not isinstance(title, str) or not title.strip():
            raise PlaybackMetadataError("YouTube metadata did not contain a nonempty title.")
        descriptor = _youtube_descriptor(video_id, title)
    else:
        media = payload.get("source_media") or {}
        url = payload.get("recording_url") or media.get("public_ref") or media.get("canonical_ref") or media.get("working_ref") or media.get("resolved_ref") or ""
        descriptor = {"provider": "native", "youtube_url": "", "video_id": "", "title": str(payload.get("title") or media.get("title") or ""), "embed_url": "", "recording_url": str(url)}
    payload["playback"] = descriptor
    for key in ("source_media", "source_fields"):
        if not isinstance(payload.get(key), dict):
            payload[key] = dict(payload.get(key) or {})
        payload[key]["playback"] = dict(descriptor)
    fields = payload["source_fields"]
    fields.update(descriptor)
    if video_id:
        payload["recording_url"] = descriptor["recording_url"]
        payload["youtube_url"] = descriptor["youtube_url"]
        fields.update(video_title=descriptor["title"], video_url=descriptor["youtube_url"], source_url=descriptor["youtube_url"])
        payload["source_media"].update(youtube_url=descriptor["youtube_url"], title=descriptor["title"])
    return descriptor


def render_playback(descriptor: Mapping[str, Any], poster: str = "", captions_url: str = "") -> str:
    """Shared player markup. Public iframe src has no query string or nocookie."""
    e = lambda value: html.escape(str(value or ""), quote=True)
    if descriptor.get("provider") == "youtube":
        video_id = extract_youtube_id(descriptor.get("youtube_url"))
        if not video_id or not _verified(descriptor, video_id):
            raise PlaybackMetadataError("A complete, consistent canonical YouTube playback descriptor is required.")
        return (f'<div class="xs-ml-player" data-xs-ml-player="" data-xs-ml-provider="youtube" data-player-title="{e(descriptor["title"])}">\n'
                f'<iframe id="player" width="1440" height="810" src="{e(descriptor["embed_url"])}" title="{e(descriptor["title"])}" '
                'frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" '
                'referrerpolicy="strict-origin-when-cross-origin" allowfullscreen '
                'style="width:100%;aspect-ratio:16/9;border-radius:8px;background:#000;"></iframe>\n</div>')
    track = f'<track kind="captions" src="{e(captions_url)}" srclang="en" label="Captions" default>' if captions_url else ""
    poster_attr = f' poster="{e(poster)}"' if poster else ""
    return ('<div class="xs-ml-player" data-xs-ml-player data-xs-ml-provider="native">\n'
            f'<video id="player" controls preload="metadata" style="width:100%;aspect-ratio:16/9;border-radius:8px;background:#000;"{poster_attr}>\n'
            f'<source src="{e(descriptor.get("recording_url")) or "#"}">{track}\n'
            'Your browser does not support the video tag.\n</video></div>')


def replace_playback_html(text: str, descriptor: Mapping[str, Any]) -> str:
    """Replace all legacy player DOM spans, including nested/custom HTML props.

    Uses parser offsets rather than a div regex so nested fallback wrappers are
    removed with the old viewer. Unrelated iframes (e.g. maps) are preserved.
    """
    if descriptor.get("provider") != "youtube" or "<" not in text:
        return text
    class Players(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.offsets = [0]
            for match in re.finditer("\n", text):
                self.offsets.append(match.end())
            self.stack = []
            self.spans = []
        def pos(self):
            line, col = self.getpos()
            return self.offsets[line - 1] + col
        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            src = a.get("src") or a.get("data-src") or ""
            cls = (a.get("class") or "").split()
            try:
                host = (urlsplit(src).hostname or "").lower()
            except ValueError:
                host = ""
            player = ("xs-ml-player" in cls or "data-xs-ml-player" in a or tag in {"video", "audio"}
                      or (tag == "iframe" and (host in _EMBED_HOSTS | _SHORT_HOSTS | {"player.vimeo.com"}
                          or a.get("id") == "player" or re.search(r"\.(?:mp4|webm|mov)(?:[?#]|$)", src, re.I))))
            if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
                self.stack.append((tag, self.pos(), player))
        def handle_endtag(self, tag):
            for index in range(len(self.stack) - 1, -1, -1):
                if self.stack[index][0] == tag:
                    entries = self.stack[index:]
                    del self.stack[index:]
                    for _, start, player in entries:
                        if player:
                            end = text.find(">", self.pos()) + 1
                            if end:
                                self.spans.append((start, end))
                    break
    parser = Players()
    parser.feed(text)
    spans = []
    for start, end in sorted(parser.spans, key=lambda span: (span[0], -span[1])):
        if not spans or start >= spans[-1][1]:
            spans.append((start, end))
    replacement = render_playback(descriptor)
    for start, end in reversed(spans):
        text = text[:start] + replacement + text[end:]

    def patch_config(match):
        config = json.loads(match.group(2))
        config["media"] = {"provider": "youtube", "url": descriptor["recording_url"],
                           "embedUrl": descriptor["embed_url"], "title": descriptor["title"],
                           "valid": True, "seekable": True}
        config["privacyMode"] = False
        content = json.dumps(config, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
        return match.group(1) + content + match.group(3)

    text = re.sub(r'(<script\b[^>]*data-xs-ml-config[^>]*>)(.*?)(</script>)',
                  patch_config, text, flags=re.I | re.S)

    def patch_link(match):
        tag = match.group(0)
        href = re.search(r'''\bhref\s*=\s*(["'])(.*?)\1''', tag, re.I | re.S)
        if href and re.search(r"\.(?:mp4|webm|mov|m4v|mp3|m4a)(?:[?#]|$)", html.unescape(href.group(2)), re.I):
            value = html.escape(descriptor["recording_url"], quote=True)
            return tag[:href.start(2)] + value + tag[href.end(2):]
        return tag
    return re.sub(r'<a\b[^>]*>', patch_link, text, flags=re.I | re.S)
