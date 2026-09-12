"""Canonical playback contract; all metadata is supplied locally by test doubles."""
import copy
import html
import io
import json
from html.parser import HTMLParser
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

from postmeet import playback
from postmeet.hydration import hydrate
from postmeet.inject import inject_youtube_embed
from postmeet.media_ref import extract_youtube_id as compatibility_parser
from postmeet.render import render

VIDEO_ID = "dQw4w9WgXcQ"
OTHER_ID = "abcdefghijk"
WATCH = f"https://www.youtube.com/watch?v={VIDEO_ID}"
EMBED = f"https://www.youtube.com/embed/{VIDEO_ID}"


class Markup(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def attrs(self, tag):
        return [attrs for name, attrs in self.tags if name == tag]


VALID_URLS = [
    WATCH, WATCH + "&t=42s&list=PLtest#chapter", WATCH.replace("https:", "http:"),
    WATCH.replace("www.youtube.com", "youtube.com"),
    WATCH.replace("www.youtube.com", "m.youtube.com"),
    WATCH.replace("www.youtube.com", "music.youtube.com"),
    WATCH.replace("www.youtube.com", "WWW.YOUTUBE.COM"),
    WATCH.replace("www.youtube.com", "www.youtube.com:443"),
    f"https://youtu.be/{VIDEO_ID}", f"https://www.youtu.be/{VIDEO_ID}?si=share&t=12",
    EMBED, EMBED + "/", EMBED + "?enablejsapi=1",
    f"https://www.youtube-nocookie.com/embed/{VIDEO_ID}",
    f"https://youtube-nocookie.com/embed/{VIDEO_ID}",
    f"https://www.youtube.com/shorts/{VIDEO_ID}",
    f"https://www.youtube.com/live/{VIDEO_ID}?feature=share",
    f"https://www.youtube.com/v/{VIDEO_ID}",
    "https://youtu.be/a_B-cD0eF12",
]
INVALID_URLS = [
    None, 123, {}, "", VIDEO_ID, VIDEO_ID + ".mp4", "/tmp/" + VIDEO_ID + ".mp4",
    "/watch?v=" + VIDEO_ID, "//youtube.com/watch?v=" + VIDEO_ID,
    "youtube.com/watch?v=" + VIDEO_ID, "ftp://youtube.com/watch?v=" + VIDEO_ID,
    "https://notyoutube.com/watch?v=" + VIDEO_ID,
    "https://youtube.com.evil.test/watch?v=" + VIDEO_ID,
    "https://www.youtube.com@evil.test/watch?v=" + VIDEO_ID,
    "https://user@www.youtube.com/watch?v=" + VIDEO_ID,
    "https://www.youtube.com:9999/watch?v=" + VIDEO_ID,
    "https://www.youtube.com:bad/watch?v=" + VIDEO_ID,
    "https://[broken/watch?v=" + VIDEO_ID,
    "https://www.youtube.com/watch", "https://www.youtube.com/watch?v=",
    WATCH + "&v=" + OTHER_ID, WATCH + "&v=", WATCH + "X", WATCH[:-1],
    WATCH + " ", " " + WATCH, WATCH + "\n", WATCH.replace(VIDEO_ID, "bad!bad!bad"),
    WATCH.replace(VIDEO_ID, VIDEO_ID + "%2Fextra"), EMBED + "/extra", EMBED + "//",
    f"https://youtu.be/{VIDEO_ID}/extra", f"https://www.youtube.com/channel/{VIDEO_ID}",
    f"https://www.youtube-nocookie.com/watch?v={VIDEO_ID}",
    "https://example.com/meeting.mp4?youtube=" + VIDEO_ID,
]


@pytest.mark.parametrize("url", VALID_URLS)
def test_strict_url_valid(url):
    expected = "a_B-cD0eF12" if "a_B-cD0eF12" in url else VIDEO_ID
    assert playback.extract_youtube_id(url) == expected
    assert compatibility_parser(url) == expected


@pytest.mark.parametrize("url", INVALID_URLS)
def test_strict_url_invalid(url):
    assert playback.extract_youtube_id(url) is None
    assert compatibility_parser(url) is None


@pytest.fixture
def descriptor(youtube_metadata):
    return playback.ensure_playback({"youtube_url": WATCH})


@pytest.mark.parametrize("surface", [
    {"youtube_url": WATCH}, {"recording_url": WATCH},
    {"source_media": {"canonical_ref": WATCH}},
    {"source_fields": {"video_url": WATCH}},
    {"source_media": {"metadata": {"original_ref": WATCH}}},
    {"mesh": {"source": {"youtube_url": WATCH}}},
    {"source": {"mesh": {"media": {"public_ref": WATCH}}}},
    {"source_fields": {"mesh": {"source": {"url": WATCH}}}},
])
def test_source_and_mesh_awareness(surface, youtube_metadata):
    p = copy.deepcopy(surface)
    d = playback.ensure_playback(p)
    assert d["video_id"] == VIDEO_ID
    assert d["title"] == youtube_metadata.return_value
    assert p["playback"] == p["source_media"]["playback"] == p["source_fields"]["playback"]
    youtube_metadata.assert_called_once_with(WATCH)


def test_local_processing_and_exact_title_persist(youtube_metadata):
    p = {"title": "Meeting editorial title", "recording_url": "/tmp/wrong-filename.mp4",
         "youtube_url": f"https://youtu.be/{VIDEO_ID}?t=30",
         "source_media": {"resolved_ref": "/tmp/work.mp4", "working_ref": "/tmp/work.wav", "title": "Filename title"}}
    d = playback.ensure_playback(p)
    assert d == {"provider": "youtube", "youtube_url": WATCH, "video_id": VIDEO_ID,
                 "title": youtube_metadata.return_value, "embed_url": EMBED, "recording_url": WATCH}
    assert p["title"] == "Meeting editorial title"
    assert p["source_media"]["resolved_ref"] == "/tmp/work.mp4"
    assert p["source_media"]["working_ref"] == "/tmp/work.wav"
    assert p["source_fields"]["video_title"] == d["title"]
    assert p["source_media"]["title"] == d["title"]
    saved = json.loads(json.dumps(p))
    assert saved["playback"] == saved["source_media"]["playback"] == saved["source_fields"]["playback"] == d


@pytest.mark.parametrize("cache_surface", ["playback", "source_media", "source_fields"])
def test_verified_serialized_cache_is_stable_offline(cache_surface, descriptor, youtube_metadata):
    p = {"youtube_url": f"https://youtu.be/{VIDEO_ID}"}
    if cache_surface == "playback":
        p["playback"] = descriptor
    else:
        p[cache_surface] = {"playback": descriptor}
    p = json.loads(json.dumps(p))
    youtube_metadata.reset_mock()
    youtube_metadata.side_effect = AssertionError("Cache must work offline")
    assert playback.ensure_playback(p) == descriptor
    snapshot = json.dumps(p, sort_keys=True)
    assert playback.ensure_playback(p) == descriptor
    assert json.dumps(p, sort_keys=True) == snapshot
    youtube_metadata.assert_not_called()


def test_changed_id_invalidates_cached_title(descriptor, youtube_metadata):
    p = {"youtube_url": WATCH, "playback": descriptor}
    playback.ensure_playback(p)
    p["youtube_url"] = f"https://youtu.be/{OTHER_ID}"
    youtube_metadata.reset_mock()
    youtube_metadata.return_value = "Exact second video's title"
    d = playback.ensure_playback(p)
    assert d["video_id"] == OTHER_ID
    assert d["title"] == "Exact second video's title"
    assert VIDEO_ID not in json.dumps(d)
    assert p["source_media"]["playback"] == p["source_fields"]["playback"] == d
    youtube_metadata.assert_called_once_with(f"https://www.youtube.com/watch?v={OTHER_ID}")


@pytest.mark.parametrize("field", ["provider", "youtube_url", "video_id", "title", "embed_url", "recording_url"])
def test_partial_or_inconsistent_cache_requires_metadata(field, descriptor, youtube_metadata):
    bad = dict(descriptor)
    bad.pop(field)
    youtube_metadata.reset_mock()
    youtube_metadata.return_value = "Refreshed exact title"
    assert playback.ensure_playback({"youtube_url": WATCH, "playback": bad})["title"] == "Refreshed exact title"
    youtube_metadata.assert_called_once_with(WATCH)


@pytest.mark.parametrize("bad_title", [None, "", " \t", 123])
def test_empty_metadata_fails_closed(bad_title, youtube_metadata):
    youtube_metadata.return_value = bad_title
    p = {"youtube_url": WATCH, "title": "Not metadata", "source_media": {"title": "file.mp4"}}
    with pytest.raises(playback.PlaybackMetadataError, match="nonempty title"):
        playback.ensure_playback(p)
    assert "playback" not in p


@pytest.mark.parametrize("consumer", ["ensure", "render", "hydrate", "inject"])
def test_metadata_failure_never_falls_back(consumer, youtube_metadata):
    youtube_metadata.side_effect = playback.PlaybackMetadataError("Metadata unavailable")
    p = {"youtube_url": WATCH, "title": "Not source title", "items": []}
    actions = {"ensure": lambda: playback.ensure_playback(p), "render": lambda: render(p),
               "hydrate": lambda: hydrate({"children": []}, p),
               "inject": lambda: inject_youtube_embed("<video></video>", WATCH, "Caller title")}
    with pytest.raises(playback.PlaybackMetadataError, match="Metadata unavailable"):
        actions[consumer]()


def test_oembed_returns_exact_title_with_bounded_request(monkeypatch):
    exact = '  Exact "source" & title — café  '
    response = Mock(wraps=io.BytesIO(json.dumps({"title": exact}).encode()))
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    opener = Mock(return_value=response)
    monkeypatch.setattr(playback, "urlopen", opener)
    assert playback.resolve_youtube_title(f"https://youtu.be/{VIDEO_ID}?t=20") == exact
    request = opener.call_args.args[0]
    assert parse_qs(urlsplit(request.full_url).query) == {"url": [WATCH], "format": ["json"]}
    assert opener.call_args.kwargs["timeout"] == playback.OEMBED_TIMEOUT
    response.read.assert_called_once_with(playback.OEMBED_MAX_BYTES + 1)


@pytest.mark.parametrize("raw", [b"bad json", b"{}", b'{"title":" "}', b"[]", b"x" * (playback.OEMBED_MAX_BYTES + 1)])
def test_oembed_failure_uses_matching_id_fallback(raw, monkeypatch):
    monkeypatch.setattr(playback, "urlopen", lambda *a, **k: io.BytesIO(raw))
    fallback = Mock(return_value={"id": VIDEO_ID, "title": "Exact fallback title"})
    monkeypatch.setattr("postmeet.source_fields._ytdlp", fallback)
    assert playback.resolve_youtube_title(WATCH) == "Exact fallback title"
    fallback.assert_called_once_with(WATCH)


@pytest.mark.parametrize("metadata", [{}, {"id": OTHER_ID, "title": "Wrong video"}, {"id": VIDEO_ID, "title": ""}])
def test_all_metadata_providers_fail_closed(metadata, monkeypatch):
    monkeypatch.setattr(playback, "urlopen", Mock(side_effect=OSError("offline")))
    monkeypatch.setattr("postmeet.source_fields._ytdlp", Mock(return_value=metadata))
    with pytest.raises(playback.PlaybackMetadataError, match="exact video title is required"):
        playback.resolve_youtube_title(WATCH)


@pytest.mark.parametrize("old_html", [
    '<video controls><source src="/tmp/old.mp4"><track src="old.vtt"></video>',
    '<audio src="/tmp/old.mp3"></audio>',
    '<div class="xs-ml-player"><div><video src="/tmp/old.mp4"></video></div><p>Old fallback</p></div>',
    '<iframe src="https://www.youtube-nocookie.com/embed/abcdefghijk?enablejsapi=1"></iframe>',
    '<iframe data-src="https://www.youtube.com/embed/abcdefghijk"></iframe>',
    '<iframe src="https://player.vimeo.com/video/123"></iframe>',
    '<iframe src="/tmp/old.mp4"></iframe>',
    '<iframe id="player" src="https://legacy.example/player"></iframe>',
    "<DIV class='custom xs-ml-player' data-xs-ml-player=''><VIDEO src='/tmp/old.mp4'></VIDEO></DIV>",
])
def test_replace_all_legacy_html_variants(old_html, descriptor):
    result = playback.replace_playback_html('<section>Keep me' + old_html + '</section>', descriptor)
    frames = Markup(result).attrs("iframe")
    assert len(frames) == 1
    assert frames[0]["src"] == EMBED
    assert frames[0]["title"] == descriptor["title"]
    assert "Keep me" in result
    for obsolete in ("<video", "<audio", "/tmp/old", "Old fallback", "nocookie", "enablejsapi"):
        assert obsolete not in result
    assert playback.replace_playback_html(result, descriptor) == result


def test_render_exact_escaped_title_and_canonical_player(descriptor):
    output = playback.render_playback(descriptor)
    frame, = Markup(output).attrs("iframe")
    assert frame["src"] == EMBED
    assert frame["title"] == descriptor["title"]
    assert html.escape(descriptor["title"], quote=True) in output
    assert "?" not in frame["src"]
    assert "allowfullscreen" in frame


def test_replace_multiple_players_preserves_unrelated_iframe_and_config(descriptor):
    source = '<video src="old.mp4"></video><iframe src="https://maps.example/map"></iframe><audio src="old.mp3"></audio>'
    source += '<script data-xs-ml-config="a">{"other":"preserved","privacyMode":true,"media":{"url":"old.mp4"}}</script>'
    source += '<a href="old.mp4">Recording</a><a href="agenda.pdf">Agenda</a>'
    output = playback.replace_playback_html(source, descriptor)
    frames = Markup(output).attrs("iframe")
    assert [f["src"] for f in frames] == [EMBED, "https://maps.example/map", EMBED]
    assert '"other":"preserved"' in output
    assert '"privacyMode":false' in output
    assert '<a href="agenda.pdf">Agenda</a>' in output
    assert f'<a href="{WATCH}">Recording</a>' in output
    assert "old.mp" not in output


def test_hydrate_custom_html_multiple_lenses_and_typed_video(descriptor):
    old = '<div class="xs-ml-player"><div><video src="/tmp/obsolete.mp4"></video></div></div>'
    preset = {"children": [
        {"type": "xs_meeting_lens", "props": {"recording_url": "/tmp/obsolete.mp4"}},
        {"type": "xs_meeting_lens", "props": {"recording_url": "/tmp/obsolete.mp4"}},
        {"type": "html", "props": {"custom_slot": {"nested": [old, old]}}},
        {"type": "video", "props": {"video": "/tmp/obsolete.mp4", "controls": True, "class": "keep-style"}},
    ]}
    original = copy.deepcopy(preset)
    items = [{"record_type": "agenda", "record_key": "one", "title": "Motion", "motion_text": "I move", "custom_fact": 42}]
    p = {"title": "Editorial meeting title", "youtube_url": WATCH, "playback": descriptor, "items": items}
    layout = hydrate(preset, p)
    assert preset == original
    assert layout["name"] == p["title"]
    for lens in layout["children"][:2]:
        assert lens["props"]["playback"] == descriptor
        assert lens["props"]["video_title"] == descriptor["title"]
        assert lens["props"]["recording_url"] == WATCH
        assert lens["children"][0]["props"]["custom_fact"] == 42
        assert lens["children"][0]["props"]["motion_text"] == "I move"
    slots = layout["children"][2]["props"]["custom_slot"]["nested"]
    assert all(Markup(value).attrs("iframe")[0]["src"] == EMBED for value in slots)
    assert layout["children"][3]["type"] == "html"
    assert layout["children"][3]["props"]["class"] == "keep-style"
    assert "/tmp/obsolete.mp4" not in json.dumps(layout)
    assert "<video" not in json.dumps(layout)


def test_repeated_injection_is_stable_and_offline(descriptor, youtube_metadata):
    source = '<video src="/tmp/old.mp4"></video><video src="/tmp/old.mp4"></video><div class="xs-ml-media-links"><a href="/tmp/old.mp4">Recording</a></div>'
    youtube_metadata.reset_mock()
    youtube_metadata.side_effect = AssertionError("Use provided descriptor offline")
    once = inject_youtube_embed(source, WATCH, "Not exact metadata", playback=descriptor)
    twice = inject_youtube_embed(once, f"https://youtu.be/{VIDEO_ID}", playback=descriptor)
    assert once == twice
    assert len(Markup(twice).attrs("iframe")) == 2
    assert "old.mp4" not in twice
    youtube_metadata.assert_not_called()


@pytest.mark.parametrize("record_type", ["agenda", "resource"])
@pytest.mark.parametrize("url_field", ["url", "youtube_url", "source_url"])
def test_unrelated_item_youtube_url_must_not_override_recording(record_type, url_field, youtube_metadata):
    p = {"title": "Local meeting", "recording_url": "/tmp/meeting.mp4",
         "source_media": {"resolved_ref": "/tmp/meeting.mp4"},
         "items": [{"record_type": record_type, "record_key": "unrelated", "title": "Supplemental video", url_field: WATCH}]}
    d = playback.ensure_playback(p)
    assert d["provider"] == "native", "Supplemental agenda/resource links are not recording sources"
    assert d["recording_url"] == "/tmp/meeting.mp4"
    assert p["items"][0][url_field] == WATCH
    youtube_metadata.assert_not_called()


def test_local_source_keeps_native_media_handling(youtube_metadata):
    p = {"title": "Local source", "recording_url": "/media/local.mp4",
         "source_media": {"resolved_ref": "/tmp/local.mp4", "working_ref": "/tmp/local.wav"},
         "captions_url": "captions.vtt", "poster": "poster.jpg", "items": []}
    d = playback.ensure_playback(p)
    assert d["provider"] == "native"
    output = playback.render_playback(d, p["poster"], p["captions_url"])
    markup = Markup(output)
    assert markup.attrs("video")[0]["poster"] == "poster.jpg"
    assert markup.attrs("source")[0]["src"] == "/media/local.mp4"
    assert markup.attrs("track")[0]["src"] == "captions.vtt"
    preset = {"children": [{"type": "video", "props": {"video": "/media/local.mp4", "controls": True}}]}
    layout = hydrate(preset, p)
    assert layout["children"][0] == preset["children"][0]
    assert '<video' in render(p)
    assert p["source_media"]["working_ref"] == "/tmp/local.wav"
    youtube_metadata.assert_not_called()
