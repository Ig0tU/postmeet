"""CLI entrypoint exercises the complete pipeline with a real timestamped VTT."""
import json
import sys
from pathlib import Path

import pytest

from postmeet.cli import main
from postmeet.hydration import find_meeting_lens_nodes

WATCH = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
EMBED = "https://www.youtube.com/embed/dQw4w9WgXcQ"


@pytest.mark.parametrize("option", ["--youtube-url", "--media-url", None])
def test_cli_run_full_timestamped_transcript_pipeline(tmp_path, monkeypatch, capsys, youtube_metadata, option):
    transcript = tmp_path / "Misleading local filename.vtt"
    transcript.write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nI call this meeting to order.\n\n"
        "00:00:06.000 --> 00:00:12.000\nI move to approve the agenda.\n\n"
        "00:00:13.000 --> 00:00:18.000\nAll in favor. Motion carries.\n",
        encoding="utf-8",
    )
    out = tmp_path / "outputs"
    argv = ["postmeet", "run", str(transcript), "--output-dir", str(out)]
    if option:
        argv.extend([option, "https://youtu.be/dQw4w9WgXcQ?t=2"])
    monkeypatch.setattr(sys, "argv", argv)
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["validation"]["ok"]
    assert len(result["asr"]["cues"]) == 3
    assert "Motion carries" in result["asr"]["text"]
    for filename in ("payload.json", "validation.json", "layout.json", "manifest.json", "meeting.html"):
        assert (out / filename).is_file()
    payload = json.loads((out / "payload.json").read_text())
    layout = json.loads((out / "layout.json").read_text())
    manifest = json.loads((out / "manifest.json").read_text())
    output_html = (out / "meeting.html").read_text()
    assert payload["items"]
    assert "Motion carries" in payload["transcript_text"]
    assert payload["source_media"]["resolved_ref"] == str(transcript)
    assert Path(result["payload"]) == out / "payload.json"
    assert manifest["source"] == str(transcript)
    assert manifest["playback"] == payload["playback"]
    assert json.loads((out / "validation.json").read_text())["ok"]
    for lens in find_meeting_lens_nodes(layout):
        assert len(lens["children"]) == len(payload["items"])
    if option:
        exact = youtube_metadata.return_value
        assert payload["playback"]["title"] == exact
        assert payload["source_fields"]["video_title"] == exact
        assert payload["source_media"]["title"] == exact
        assert payload["source_media"]["playback"] == payload["source_fields"]["playback"] == payload["playback"]
        assert payload["recording_url"] == WATCH
        assert f'src="{EMBED}"' in output_html
        assert "<video" not in output_html
        assert "youtube-nocookie" not in output_html
        assert "?enablejsapi" not in output_html
        for lens in find_meeting_lens_nodes(layout):
            assert lens["props"]["playback"]["title"] == exact
            assert lens["props"]["recording_url"] == WATCH
        youtube_metadata.assert_called_once_with(WATCH)
    else:
        assert payload["playback"]["provider"] == "native"
        assert '<video' in output_html
        youtube_metadata.assert_not_called()


def test_cli_pipeline_metadata_failure_does_not_publish_html(tmp_path, monkeypatch, youtube_metadata):
    from postmeet.playback import PlaybackMetadataError
    transcript = tmp_path / "meeting.vtt"
    transcript.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:05.000\nI call this meeting to order.\n")
    out = tmp_path / "failed"
    monkeypatch.setattr(sys, "argv", ["postmeet", "run", str(transcript), "--output-dir", str(out), "--youtube-url", WATCH])
    youtube_metadata.side_effect = PlaybackMetadataError("Metadata unavailable")
    with pytest.raises(PlaybackMetadataError, match="Metadata unavailable"):
        main()
    assert not (out / "meeting.html").exists()
    assert not (out / "layout.json").exists()
    assert not (out / "manifest.json").exists()
