import json
import pytest
from pathlib import Path
from postmeet.inject import inject_youtube_embed
from postmeet.render import render

ROOT = Path(__file__).resolve().parents[1]


def sample_payload():
    return json.loads((ROOT / "examples/sample_payload.json").read_text(encoding="utf-8"))


def test_inject_youtube_embed_basic():
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

    res = inject_youtube_embed(sample_html, yt_url, title)

    # Step 1 & 2: Check iframe player replacement
    assert 'data-xs-ml-provider="youtube"' in res
    assert 'src="https://www.youtube.com/embed/dQw4w9WgXcQ?enablejsapi=1"' in res
    assert 'title="Regular Board Meeting - October 2023"' in res
    assert '<video' not in res

    # Step 3: Check fallback link replacement
    assert f'<div class="xs-ml-media-links"><a href="{yt_url}" target="_blank">Recording link</a></div>' in res
    assert '/tmp/recording.mp4' not in res

    # Step 4: Check JSON state patch
    assert '"media":{"provider":"youtube","url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ","embedUrl":"https://www.youtube.com/embed/dQw4w9WgXcQ?enablejsapi=1","seekable":true,"valid":true}' in res


def test_inject_youtube_embed_standalone_video_element():
    sample_html = """<div>
    <video id="player" controls="" preload="metadata" style="width:100%;aspect-ratio:16/9;border-radius:8px;background:#000;"><source src="/tmp/postmeet_upload_cppcqbik/Monday July 7, 2025 - MSDMV School Board Meeting.mp4">Your browser does not support the video tag.</video>
    <div class="xs-ml-media-links"><a href="/tmp/postmeet_upload_cppcqbik/video.mp4">Recording link</a></div>
    <script type="application/json" data-xs-ml-config="test">{"media":{"provider":"native","url":"/tmp/video.mp4","embedUrl":"","seekable":true,"valid":true}}</script>
</div>"""

    yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    title = "MSDMV School Board Meeting"

    res = inject_youtube_embed(sample_html, yt_url, title)

    assert '<video' not in res
    assert 'src="https://www.youtube.com/embed/dQw4w9WgXcQ?enablejsapi=1"' in res
    assert 'title="MSDMV School Board Meeting"' in res
    assert f'<div class="xs-ml-media-links"><a href="{yt_url}" target="_blank">Recording link</a></div>' in res


def test_inject_youtube_embed_youtu_be_url():
    sample_html = """<div class="xs-ml-player" data-xs-ml-player data-xs-ml-provider="native"><video id="player"></video></div>
<div class="xs-ml-media-links"><a href="/tmp/video.mp4">Recording link</a></div>
<script type="application/json" data-xs-ml-config="test">{"media":{"provider":"native","url":"/tmp/video.mp4","embedUrl":"","seekable":true,"valid":true}}</script>"""

    yt_url = "https://youtu.be/dQw4w9WgXcQ"
    title = 'Meeting with "Quotes" & Special Characters'

    res = inject_youtube_embed(sample_html, yt_url, title)

    assert 'src="https://www.youtube.com/embed/dQw4w9WgXcQ?enablejsapi=1"' in res
    assert 'title="Meeting with &quot;Quotes&quot; &amp; Special Characters"' in res
    assert f'<div class="xs-ml-media-links"><a href="{yt_url}" target="_blank">Recording link</a></div>' in res
    assert f'"url":"{yt_url}"' in res


def test_inject_youtube_embed_invalid_url():
    with pytest.raises(ValueError, match="Could not extract a valid 11-character YouTube video ID"):
        inject_youtube_embed("<div></div>", "https://example.com/not-youtube", "Title")


def test_inject_youtube_embed_rendered_page():
    p = sample_payload()
    p["recording_url"] = "/tmp/meeting_recording_123.mp4"
    rendered_html = render(p)

    assert 'data-xs-ml-provider="native"' in rendered_html

    yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    title = p.get("title", "Board Meeting")

    injected_html = inject_youtube_embed(rendered_html, yt_url, title)

    assert 'data-xs-ml-provider="youtube"' in injected_html
    assert 'src="https://www.youtube.com/embed/dQw4w9WgXcQ?enablejsapi=1"' in injected_html
    assert f'<a href="{yt_url}" target="_blank">Recording link</a>' in injected_html
    assert '"media":{"provider":"youtube"' in injected_html
