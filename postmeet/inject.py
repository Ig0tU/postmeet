"""Canonical YouTube playback injection for legacy meeting HTML."""
from __future__ import annotations

import html
import json
import re
from typing import Any, Mapping
from .playback import ensure_playback, replace_playback_html


def inject_youtube_embed(target_html: str, youtube_url: str, video_title: str = "",
                         *, playback: Mapping[str, Any] | None = None) -> str:
    """Replace every old viewer and its config using the canonical renderer.

    ``video_title`` remains accepted for CLI compatibility but cannot substitute
    for YouTube metadata. Supply a verified canonical ``playback`` descriptor to
    reuse previously resolved metadata offline (only for the same URL/ID).
    """
    payload = {"youtube_url": youtube_url}
    if playback:
        payload["playback"] = dict(playback)
    descriptor = ensure_playback(payload)
    result_html = replace_playback_html(target_html, descriptor)
    escaped_url = html.escape(descriptor["recording_url"], quote=True)
    links = f'<div class="xs-ml-media-links"><a href="{escaped_url}" target="_blank" rel="noopener noreferrer">Recording link</a></div>'
    result_html = re.sub(
        r"<div\b[^>]*class=[\"'][^\"']*xs-ml-media-links[^\"']*[\"'][^>]*>.*?</div>",
        lambda match: links, result_html, flags=re.DOTALL | re.IGNORECASE)

    def patch_config_script(match: re.Match) -> str:
        config = json.loads(match.group(2))
        config["media"] = {"provider": "youtube", "url": descriptor["recording_url"],
                           "embedUrl": descriptor["embed_url"], "title": descriptor["title"],
                           "seekable": True, "valid": True}
        config["privacyMode"] = False
        content = json.dumps(config, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
        return match.group(1) + content + match.group(3)

    return re.sub(r'(<script\b[^>]*data-xs-ml-config[^>]*>)(.*?)(</script>)',
                  patch_config_script, result_html, flags=re.DOTALL | re.IGNORECASE)
