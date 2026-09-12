import json
import pytest
from pathlib import Path
from postmeet.inject import inject_youtube_embed
from postmeet.render import render

ROOT = Path(__file__).resolve().parents[1]


def sample_payload():
    return json.loads((ROOT / "examples/sample_payload.json").read_text(encoding="utf-8"))


def test_inject_youtube_embed_basic(youtube_metadata):
    sample_html = """<!doctype html>
<html>
<body>
    <div class="xs-ml-player" data-xs-ml-player="" data-xs-ml-provider="native">
        <video id="player" controls><source src="/tmp/recording.mp4"></video>
    </div>
    <div class="xs-ml-media-links"><a href="/tmp/recording.mp4">Recording link</a></div>
    <script type="application/json" data-xs-ml-config="cfg1">{"id":"cfg1","media":{"provider":"native","url":"/tmp/recording.mp4","embedUrl":"","seekable":true,"valid":true}}</script>
</body>
</html>"""

    yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    title = "Regular Board Meeting - October 2023"

    youtube_metadata.return_value = title
    res = inject_youtube_embed(sample_html, yt_url, "Wrong caller-provided title")

    # Step 1 & 2: Check iframe player replacement
    assert 'data-xs-ml-provider="youtube"' in res
    assert 'src="https://www.youtube.com/embed/dQw4w9WgXcQ"' in res
    assert 'title="Regular Board Meeting - October 2023"' in res
    assert '<video' not in res

    # Step 3: Check fallback link replacement
    assert f'<div class="xs-ml-media-links"><a href="{yt_url}" target="_blank" rel="noopener noreferrer">Recording link</a></div>' in res
    assert '/tmp/recording.mp4' not in res

    # Step 4: Check JSON state patch
    import re
    config = json.loads(re.search(r'<script[^>]*>(.*?)</script>', res, re.S).group(1))
    assert config["media"] == {"provider": "youtube", "url": yt_url,
        "embedUrl": "https://www.youtube.com/embed/dQw4w9WgXcQ", "title": title,
        "seekable": True, "valid": True}
    assert config["privacyMode"] is False


def test_inject_youtube_embed_standalone_video_element(youtube_metadata):
    sample_html = """<div>
    <video id="player" controls="" preload="metadata" style="width:100%;aspect-ratio:16/9;border-radius:8px;background:#000;"><source src="/tmp/postmeet_upload_cppcqbik/Monday July 7, 2025 - MSDMV School Board Meeting.mp4">Your browser does not support the video tag.</video>
    <div class="xs-ml-media-links"><a href="/tmp/postmeet_upload_cppcqbik/video.mp4">Recording link</a></div>
    <script type="application/json" data-xs-ml-config="test">{"media":{"provider":"native","url":"/tmp/video.mp4","embedUrl":"","seekable":true,"valid":true}}</script>
</div>"""

    yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    title = "MSDMV School Board Meeting"

    youtube_metadata.return_value = title
    res = inject_youtube_embed(sample_html, yt_url, "Wrong caller-provided title")

    assert '<video' not in res
    assert 'src="https://www.youtube.com/embed/dQw4w9WgXcQ"' in res
    assert 'title="MSDMV School Board Meeting"' in res
    assert f'<div class="xs-ml-media-links"><a href="{yt_url}" target="_blank" rel="noopener noreferrer">Recording link</a></div>' in res


def test_inject_youtube_embed_youtu_be_url(youtube_metadata):
    sample_html = """<div class="xs-ml-player" data-xs-ml-player data-xs-ml-provider="native"><video id="player"></video></div>
<div class="xs-ml-media-links"><a href="/tmp/video.mp4">Recording link</a></div>
<script type="application/json" data-xs-ml-config="test">{"media":{"provider":"native","url":"/tmp/video.mp4","embedUrl":"","seekable":true,"valid":true}}</script>"""

    yt_url = "https://youtu.be/dQw4w9WgXcQ"
    title = 'Meeting with "Quotes" & Special Characters'

    youtube_metadata.return_value = title
    res = inject_youtube_embed(sample_html, yt_url, "Wrong caller-provided title")

    assert 'src="https://www.youtube.com/embed/dQw4w9WgXcQ"' in res
    assert 'title="Meeting with &quot;Quotes&quot; &amp; Special Characters"' in res
    canonical = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert f'<div class="xs-ml-media-links"><a href="{canonical}" target="_blank" rel="noopener noreferrer">Recording link</a></div>' in res
    assert f'"url":"{canonical}"' in res


def test_inject_youtube_embed_invalid_url():
    with pytest.raises(ValueError, match="Invalid YouTube URL"):
        inject_youtube_embed("<div></div>", "https://example.com/not-youtube", "Title")


def test_inject_youtube_embed_rendered_page(youtube_metadata):
    p = sample_payload()
    p["recording_url"] = "/tmp/meeting_recording_123.mp4"
    rendered_html = render(p)

    assert 'data-xs-ml-provider="native"' in rendered_html

    yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    title = p.get("title", "Board Meeting")

    youtube_metadata.return_value = title
    injected_html = inject_youtube_embed(rendered_html, yt_url, "Wrong caller-provided title")

    assert 'data-xs-ml-provider="youtube"' in injected_html
    assert 'src="https://www.youtube.com/embed/dQw4w9WgXcQ"' in injected_html
    assert f'<a href="{yt_url}" target="_blank" rel="noopener noreferrer">Recording link</a>' in injected_html
    assert '"media":{"provider":"youtube"' in injected_html
