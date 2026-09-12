import json
from pathlib import Path
from postmeet.validation import validate
from postmeet.hydration import hydrate
from postmeet.render import render

ROOT = Path(__file__).resolve().parents[1]


def payload(): return json.loads((ROOT / "examples/sample_payload.json").read_text())
def preset(): return json.loads((ROOT / "presets/meeting_lens_full.json").read_text())


def test_sample_validates():
    result = validate(payload())
    assert result["ok"], result
    assert result["agenda_count"] == 2


def test_hydration_fills_layout_and_preserves_items():
    layout = hydrate(preset(), payload())
    assert layout["version"] == "5.0.43"
    lens = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == "xs_meeting_lens": lens.append(n)
            for c in n.get("children") or []: walk(c)
        elif isinstance(n, list):
            for c in n: walk(c)

    walk(layout)
    assert len(lens) == 1
    assert len(lens[0]["children"]) == 2
    assert lens[0]["children"][1]["props"]["motion_text"].startswith("I move")


def test_youtube_id_extraction():
    from postmeet.media_ref import extract_youtube_id
    urls = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ]
    for url, expected_id in urls:
        assert extract_youtube_id(url) == expected_id, f"Failed for {url}"


def test_hydration_with_youtube_url():
    p = payload()
    p["youtube_url"] = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    layout = hydrate(preset(), p)

    lens = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == "xs_meeting_lens": lens.append(n)
            for c in n.get("children") or []: walk(c)
        elif isinstance(n, list):
            for c in n: walk(c)

    walk(layout)
    assert len(lens) == 1
    props = lens[0]["props"]
    assert props["recording_url"] == "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?enablejsapi=1"
    # Ensure transcript text and items were preserved
    assert len(lens[0]["children"]) == 2


def test_render_with_youtube_url():
    p = payload()
    p["youtube_url"] = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    html_out = render(p)
    assert 'data-xs-ml-provider="youtube"' in html_out
    assert 'src="https://www.youtube.com/embed/dQw4w9WgXcQ?enablejsapi=1"' in html_out
    assert '"provider":"youtube"' in html_out


def test_pipeline_with_and_without_youtube_url(tmp_path):
    from postmeet.pipeline import run
    vtt_file = tmp_path / "sample.vtt"
    vtt_file.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nCall to order.\n\n00:00:06.000 --> 00:00:10.000\nI move to approve the agenda.\n",
        encoding="utf-8"
    )

    # Run pipeline with local file (or transcript file)
    res_no_yt = run(str(vtt_file), output_dir=str(tmp_path / "out1"))
    assert Path(res_no_yt["layout"]).exists()

    # Run pipeline with youtube_url
    res_yt = run(str(vtt_file), output_dir=str(tmp_path / "out2"), youtube_url="https://youtu.be/dQw4w9WgXcQ")
    assert Path(res_yt["layout"]).exists()
    assert Path(res_yt["html"]).exists()
    html_content = Path(res_yt["html"]).read_text(encoding="utf-8")
    assert 'data-xs-ml-provider="youtube"' in html_content
    assert 'src="https://www.youtube.com/embed/dQw4w9WgXcQ?enablejsapi=1"' in html_content

    layout_data = json.loads(Path(res_yt["layout"]).read_text())

    lens = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == "xs_meeting_lens": lens.append(n)
            for c in n.get("children") or []: walk(c)
        elif isinstance(n, list):
            for c in n: walk(c)

    walk(layout_data)
    assert lens[0]["props"]["recording_url"] == "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?enablejsapi=1"
