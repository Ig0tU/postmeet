"""Local-first, timestamped transcription for PostMeet.

The adapter accepts local media, direct media URLs, YouTube/Vimeo URLs, and
already-timestamped .txt/.vtt/.srt transcripts. Network media is downloaded
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
        cues=[]
        blocks=re.split(r"\n\s*\n", text)
        for block in blocks:
            m=re.search(r"(\d{1,2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{3})\s*\n(.+)",block,re.S)
            if m:
                body=re.sub(r"<[^>]+>","",m.group(3)); body=re.sub(r"\s+"," ",body).strip()
                if body: cues.append((_parse_clock(m.group(1)),body))
        return cues
    if path.suffix.lower() == ".vtt":
        cues=[]
        for block in re.split(r"\n\s*\n", text):
            m=re.search(r"(\d{1,2}:\d{2}(?::\d{2})?\.\d{3})\s*-->\s*[^\n]+\n(.+)",block,re.S)
            if m:
                body=re.sub(r"<[^>]+>","",m.group(2)); body=re.sub(r"\s+"," ",body).strip()
                if body: cues.append((_parse_clock(m.group(1)),body))
        return cues
    cues=[]
    for line in text.splitlines():
        m=re.match(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{2})\s*[-–]\s*(.+)$",line)
        if m:
            t=(int(m.group(1) or 0)*3600)+(int(m.group(2))*60)+int(m.group(3)); body=m.group(4).strip()
            if body: cues.append((float(t),body))
    return cues


def _fw(src: Path, model: str):
    try: from faster_whisper import WhisperModel
    except ImportError: return None
    m=WhisperModel(model or os.getenv("POSTMEET_WHISPER_MODEL","small"),device=os.getenv("POSTMEET_WHISPER_DEVICE","cpu"),compute_type=os.getenv("POSTMEET_WHISPER_COMPUTE","int8"))
    segs,_=m.transcribe(str(src),language=os.getenv("POSTMEET_WHISPER_LANG","") or None,vad_filter=True,condition_on_previous_text=False)
    return [(float(s.start),(s.text or "").strip()) for s in segs if (s.text or "").strip()]


def transcribe(source: str, *, model: str = "", prefer_asr: bool = False) -> dict[str, Any]:
    src_path=Path(source) if Path(source).is_file() else None
    if src_path and src_path.suffix.lower() in {".txt",".srt",".vtt"}:
        cues=_parse_caption_file(src_path)
        if cues: return {"text":"\n".join(f"{_stamp(t)} - {v}" for t,v in cues),"cues":[{"start":t,"text":v} for t,v in cues],"source":"captions"}
    with tempfile.TemporaryDirectory(prefix="postmeet-") as td:
        wd=Path(td); src=src_path
        if src is None and shutil.which("yt-dlp"):
            # Prefer captions when present; audio is the deterministic fallback.
            cap_prefix=wd/"captions"
            _run(["yt-dlp","--skip-download","--write-auto-subs","--write-subs","--sub-langs","en,en-US,en-GB","--sub-format","vtt","--no-playlist","-o",str(cap_prefix),source],600)
            caps=sorted(wd.glob("captions*.vtt"))
            if caps:
                cues=_parse_caption_file(caps[0])
                if cues: return {"text":"\n".join(f"{_stamp(t)} - {v}" for t,v in cues),"cues":[{"start":t,"text":v} for t,v in cues],"source":"captions"}
        if src is None and shutil.which("ffmpeg") and (source.startswith(("http://","https://"))):
            out=wd/"audio.wav"; p=_run(["ffmpeg","-nostdin","-y","-i",source,"-vn","-ac","1","-ar","16000","-f","wav",str(out)],1800)
            if p.returncode==0 and out.exists() and out.stat().st_size>1024: src=out
        if src is None and shutil.which("yt-dlp") and source.startswith(("http://","https://")):
            p=_run(["yt-dlp","-x","--audio-format","mp3","--no-playlist","-o",str(wd/"audio.%(ext)s"),source],1800)
            found=sorted(wd.glob("audio.*")); src=found[0] if p.returncode==0 and found else None
        if src is None: return {"text":"","cues":[],"source":"none","error":"No media could be acquired. Install ffmpeg/yt-dlp or provide a local media/transcript file."}
        cues=_fw(src,model)
        if cues is None:
            whisper=os.getenv("POSTMEET_WHISPER_BIN","whisper")
            if not shutil.which(whisper): return {"text":"","cues":[],"source":"none","error":"No ASR backend installed. Install postmeet[asr] or a Whisper CLI."}
            out=wd/"json"; out.mkdir()
            p=_run([whisper,str(src),"--model",model or os.getenv("POSTMEET_WHISPER_MODEL","small"),"--output_format","json","--output_dir",str(out),"--fp16","False"],14400)
            fs=sorted(out.glob("*.json")); data=json.loads(fs[0].read_text()) if p.returncode==0 and fs else {}
            cues=[(float(x.get("start",0)),str(x.get("text") or "").strip()) for x in data.get("segments",[]) if str(x.get("text") or "").strip()]
        if not cues: return {"text":"","cues":[],"source":"none","error":"ASR completed without usable transcript segments."}
        return {"text":"\n".join(f"{_stamp(t)} - {v}" for t,v in cues),"cues":[{"start":t,"text":v} for t,v in cues],"source":"asr"}
