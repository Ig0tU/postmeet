"""Local-first, timestamped transcription and PDF packet parser for PostMeet.

The adapter accepts local media, direct media URLs, YouTube/Vimeo URLs, PDF packets,
and already-timestamped .txt/.vtt/.srt transcripts. Network media is downloaded
only through the caller-approved reference; no cloud ASR service is required.
"""
from __future__ import annotations
import json, os, re, shutil, subprocess, tempfile
from pathlib import Path
from typing import Any


def _run(cmd: list[str], timeout: int = 900):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _stamp(sec: float) -> str:
    m, s = divmod(max(0, int(sec)), 60); h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _parse_clock(value: str) -> float:
    p = value.strip().replace(",", ".").split(":")
    if len(p) == 3: return int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2])
    if len(p) == 2: return int(p[0]) * 60 + float(p[1])
    return float(p[0])


def _parse_caption_file(path: Path) -> list[tuple[float, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".srt":
        cues = []
        blocks = re.split(r"\n\s*\n", text)
        for block in blocks:
            m = re.search(r"(\d{1,2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{3})\s*\n(.+)", block, re.S)
            if m:
                body = re.sub(r"<[^>]+>", "", m.group(3))
                body = re.sub(r"\s+", " ", body).strip()
                if body: cues.append((_parse_clock(m.group(1)), body))
        return cues
    if path.suffix.lower() == ".vtt":
        cues = []
        for block in re.split(r"\n\s*\n", text):
            m = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?\.\d{3})\s*-->\s*[^\n]+\n(.+)", block, re.S)
            if m:
                body = re.sub(r"<[^>]+>", "", m.group(2))
                body = re.sub(r"\s+", " ", body).strip()
                if body: cues.append((_parse_clock(m.group(1)), body))
        return cues
    cues = []
    for line in text.splitlines():
        m = re.match(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{2})\s*[-–]\s*(.+)$", line)
        if m:
            t = (int(m.group(1) or 0) * 3600) + (int(m.group(2)) * 60) + int(m.group(3))
            body = m.group(4).strip()
            if body: cues.append((float(t), body))
    return cues


def _parse_pdf_file(path: Path) -> dict[str, Any]:
    """Extract text from PDF pages and transform into timestamped document cues."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
    except Exception as e:
        return {"cues": [], "text": "", "page_count": 0, "title": "", "error": str(e)}

    cues: list[tuple[float, str]] = []
    t = 0.0
    doc_title = ""

    for page_num, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        lines = [re.sub(r"\s+", " ", l).strip() for l in raw_text.splitlines() if l.strip()]
        if not lines:
            continue

        if not doc_title and lines:
            doc_title = lines[0]
            if len(lines) > 1 and len(doc_title) < 35:
                doc_title += f": {lines[1]}"

        cues.append((t, f">> [Page {page_num}] {lines[0]}"))
        t += 4.0

        chunk: list[str] = []
        for line in lines[1:]:
            chunk.append(line)
            if len(" ".join(chunk)) > 200:
                cues.append((t, " ".join(chunk)))
                chunk = []
                t += 5.0
        if chunk:
            cues.append((t, " ".join(chunk)))
            t += 4.0

    return {
        "text": "\n".join(f"{_stamp(cue_t)} - {v}" for cue_t, v in cues),
        "cues": [{"start": cue_t, "text": v} for cue_t, v in cues],
        "source": "pdf",
        "page_count": len(reader.pages),
        "title": doc_title or path.stem.replace("_", " ").title()
    }


def _fw(src: Path, model: str):
    try: from faster_whisper import WhisperModel
    except ImportError: return None
    m = WhisperModel(model or os.getenv("POSTMEET_WHISPER_MODEL", "small"),
                     device=os.getenv("POSTMEET_WHISPER_DEVICE", "cpu"),
                     compute_type=os.getenv("POSTMEET_WHISPER_COMPUTE", "int8"))
    segs, _ = m.transcribe(str(src), language=os.getenv("POSTMEET_WHISPER_LANG", "") or None, vad_filter=True, condition_on_previous_text=False)
    return [(float(s.start), (s.text or "").strip()) for s in segs if (s.text or "").strip()]


def transcribe(source: str, *, model: str = "", prefer_asr: bool = False) -> dict[str, Any]:
    src_path = Path(source) if Path(source).is_file() else None

    # 1. Local Caption File
    if src_path and src_path.suffix.lower() in {".txt", ".srt", ".vtt"}:
        cues = _parse_caption_file(src_path)
        if cues:
            return {"text": "\n".join(f"{_stamp(t)} - {v}" for t, v in cues), "cues": [{"start": t, "text": v} for t, v in cues], "source": "captions"}

    # 2. Local PDF Document Packet
    if src_path and src_path.suffix.lower() == ".pdf":
        pdf_res = _parse_pdf_file(src_path)
        if pdf_res.get("cues"):
            return pdf_res

    # 3. Remote PDF URL
    if source.startswith(("http://", "https://")) and (source.lower().endswith(".pdf") or ".pdf?" in source.lower()):
        import urllib.request
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                req = urllib.request.Request(source, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    tf.write(resp.read())
                tf_path = Path(tf.name)
            pdf_res = _parse_pdf_file(tf_path)
            try: tf_path.unlink()
            except Exception: pass
            if pdf_res.get("cues"):
                return pdf_res
        except Exception as e:
            return {"text": "", "cues": [], "source": "pdf", "error": f"Failed to download and parse PDF: {e}"}

    # 4. Audio / Video media
    with tempfile.TemporaryDirectory(prefix="postmeet-") as td:
        wd = Path(td)
        src = src_path
        err_details = []

        if src is None and shutil.which("yt-dlp"):
            cap_prefix = wd / "captions"
            p1 = _run(["yt-dlp", "--skip-download", "--write-auto-subs", "--write-subs", "--sub-langs", "en,en-US,en-GB", "--sub-format", "vtt", "--no-playlist", "--extractor-args", "youtube:player_client=android,web", "-o", str(cap_prefix), source], 600)
            caps = sorted(wd.glob("captions*.vtt"))
            if caps:
                cues = _parse_caption_file(caps[0])
                if cues:
                    return {"text": "\n".join(f"{_stamp(t)} - {v}" for t, v in cues), "cues": [{"start": t, "text": v} for t, v in cues], "source": "captions"}
            if p1.returncode != 0 and p1.stderr.strip():
                err_details.append(p1.stderr.strip().splitlines()[-1])

        if src is None and shutil.which("ffmpeg") and (source.startswith(("http://", "https://"))):
            out = wd / "audio.wav"
            p = _run(["ffmpeg", "-nostdin", "-y", "-i", source, "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(out)], 1800)
            if p.returncode == 0 and out.exists() and out.stat().st_size > 1024:
                src = out
            elif p.returncode != 0 and p.stderr.strip():
                err_details.append(p.stderr.strip().splitlines()[-1])

        if src is None and shutil.which("yt-dlp") and source.startswith(("http://", "https://")):
            p = _run(["yt-dlp", "-x", "--audio-format", "mp3", "--no-playlist", "--extractor-args", "youtube:player_client=android,web", "-o", str(wd / "audio.%(ext)s"), source], 1800)
            found = sorted(wd.glob("audio.*"))
            src = found[0] if p.returncode == 0 and found else None
            if p.returncode != 0 and p.stderr.strip():
                err_details.append(p.stderr.strip().splitlines()[-1])

        if src is None:
            diag = f": {'; '.join(err_details)}" if err_details else ""
            return {"text": "", "cues": [], "source": "none", "error": f"No media or document could be acquired from '{source}'{diag}. Please use the 'File Upload' tab to upload the media or document directly."}

        cues = _fw(src, model)
        if cues is None:
            whisper = os.getenv("POSTMEET_WHISPER_BIN", "whisper")
            if not shutil.which(whisper):
                return {"text": "", "cues": [], "source": "none", "error": "No ASR backend installed. Install postmeet[asr] or a Whisper CLI."}
            out = wd / "json"
            out.mkdir()
            _run([whisper, str(src), "--output_format", "json", "--output_dir", str(out)], 1800)
            j = list(out.glob("*.json"))
            if not j:
                return {"text": "", "cues": [], "source": "none", "error": "Whisper produced no transcript output."}
            data = json.loads(j[0].read_text(encoding="utf-8"))
            cues = [(float(s.get("start", 0)), s.get("text", "").strip()) for s in data.get("segments", []) if s.get("text", "").strip()]

    return {"text": "\n".join(f"{_stamp(t)} - {v}" for t, v in cues), "cues": [{"start": t, "text": v} for t, v in cues], "source": "asr"}
