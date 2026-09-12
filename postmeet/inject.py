"""inject.py — Generic YouTube Embed Injection into xs-meeting-lens HTML documents."""
from __future__ import annotations

import html
import json
import re
from .media_ref import extract_youtube_id


def inject_youtube_embed(target_html: str, youtube_url: str, video_title: str) -> str:
    """Transform a native .mp4 video player block within an xs-meeting-lens HTML
    document into a dynamically generated YouTube iframe.

    Step 1: Extract Video ID.
    Step 2: Replace <div class="xs-ml-player"...> container or <video> element.
    Step 3: Replace <div class="xs-ml-media-links"> fallback link.
    Step 4: Patch "media":{...} inside <script type="application/json" data-xs-ml-config=...>.
    """
    # Step 1: Extract Video ID
    video_id = extract_youtube_id(youtube_url)
    if not video_id:
        raise ValueError(f"Could not extract a valid 11-character YouTube video ID from {youtube_url!r}")

    result_html = target_html

    # Step 2: DOM Replacement (The Player)
    escaped_title = html.escape(video_title, quote=True)
    player_replacement = (
        f'<div class="xs-ml-player" data-xs-ml-player="" data-xs-ml-provider="youtube">\n'
        f'    <iframe id="player" width="1440" height="810" '
        f'src="https://www.youtube.com/embed/{video_id}?enablejsapi=1" title="{escaped_title}" '
        f'frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" '
        f'referrerpolicy="strict-origin-when-cross-origin" allowfullscreen '
        f'style="width:100%; aspect-ratio:16/9; border-radius:8px; background:#000;"></iframe>\n'
        f'</div>'
    )

    player_pattern = re.compile(
        r'<div\b(?=[^>]*\bclass=["\']?[^"\'>]*xs-ml-player[^"\'>]*["\']?)(?:(?=[^>]*\bdata-xs-ml-provider=["\']?native["\']?)|(?=[^>]*>.*?<video\b))[^>]*>.*?</div>',
        re.DOTALL
    )
    if player_pattern.search(result_html):
        result_html = player_pattern.sub(player_replacement, result_html)
    else:
        video_standalone_pattern = re.compile(r'<video\b.*?</video>', re.DOTALL)
        result_html = video_standalone_pattern.sub(player_replacement, result_html)

    # Step 3: DOM Replacement (Fallback Link)
    escaped_url = html.escape(youtube_url, quote=True)
    media_links_replacement = f'<div class="xs-ml-media-links"><a href="{escaped_url}" target="_blank">Recording link</a></div>'
    media_links_pattern = re.compile(
        r'<div\b[^>]*class=["\']?[^"\'>]*xs-ml-media-links[^"\'>]*["\']?[^>]*>.*?</div>',
        re.DOTALL
    )
    result_html = media_links_pattern.sub(media_links_replacement, result_html)

    # Step 4: JSON State Patch
    media_obj_str = json.dumps({
        "provider": "youtube",
        "url": youtube_url,
        "embedUrl": f"https://www.youtube.com/embed/{video_id}?enablejsapi=1",
        "seekable": True,
        "valid": True
    }, separators=(',', ':'))

    def patch_config_script(match: re.Match) -> str:
        opening = match.group(1)
        content = match.group(2)
        closing = match.group(3)
        patched_content = re.sub(r'"media"\s*:\s*\{[^{}]*\}', f'"media":{media_obj_str}', content)
        return f"{opening}{patched_content}{closing}"

    script_pattern = re.compile(
        r'(<script\b[^>]*data-xs-ml-config[^>]*>)(.*?)(</script>)',
        re.DOTALL
    )
    result_html = script_pattern.sub(patch_config_script, result_html)

    return result_html
