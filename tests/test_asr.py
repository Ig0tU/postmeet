from pathlib import Path
from postmeet.asr import transcribe


def test_timestamped_text(tmp_path: Path):
    p = tmp_path / "captions.txt"
    p.write_text("00:03 - Call to order\n00:12 - I move to approve the agenda.\n00:20 - Motion carries.\n")
    r = transcribe(str(p))
    assert r["source"] == "captions"
    assert r["cues"][0]["start"] == 3
    assert "Motion carries" in r["text"]


def test_srt(tmp_path: Path):
    p = tmp_path / "captions.srt"
    p.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello board\n\n2\n00:00:04,000 --> 00:00:06,000\nMeeting starts\n")
    r = transcribe(str(p))
    assert len(r["cues"]) == 2
    assert r["cues"][1]["start"] == 4
