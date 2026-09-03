"""Local-first timestamped ASR adapter for PostMeet."""
from __future__ import annotations
import json, os, shutil, subprocess, tempfile
from pathlib import Path
from typing import Any

def _run(cmd:list[str],timeout:int=900): return subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
def _stamp(sec:float)->str:
    m,s=divmod(int(sec),60); h,m=divmod(m,60); return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
def _fw(src:Path,model:str):
    try: from faster_whisper import WhisperModel
    except ImportError: return None
    m=WhisperModel(model or os.getenv("POSTMEET_WHISPER_MODEL","small"),device=os.getenv("POSTMEET_WHISPER_DEVICE","cpu"),compute_type=os.getenv("POSTMEET_WHISPER_COMPUTE","int8"))
    segs,_=m.transcribe(str(src),language=os.getenv("POSTMEET_WHISPER_LANG","en") or None,vad_filter=True,condition_on_previous_text=False)
    return [(float(s.start),(s.text or "").strip()) for s in segs if (s.text or "").strip()]
def transcribe(source:str,*,model:str="",prefer_asr:bool=False)->dict[str,Any]:
    with tempfile.TemporaryDirectory(prefix="postmeet-") as td:
        wd=Path(td); src=Path(source) if Path(source).exists() else None
        if src is None and shutil.which("ffmpeg"):
            out=wd/"audio.wav"; p=_run(["ffmpeg","-nostdin","-y","-i",source,"-vn","-ac","1","-ar","16000","-f","wav",str(out)],1800)
            if out.exists() and out.stat().st_size>1024: src=out
        if src is None and shutil.which("yt-dlp"):
            _run(["yt-dlp","-x","--audio-format","mp3","-o",str(wd/"audio.%(ext)s"),source],1800); found=sorted(wd.glob("audio.*")); src=found[0] if found else None
        if src is None: return {"text":"","cues":[],"source":"none"}
        cues=_fw(src,model)
        if cues is None:
            if not shutil.which(os.getenv("POSTMEET_WHISPER_BIN","whisper")): return {"text":"","cues":[],"source":"none"}
            out=wd/"json"; out.mkdir(); _run([os.getenv("POSTMEET_WHISPER_BIN","whisper"),str(src),"--model",model or os.getenv("POSTMEET_WHISPER_MODEL","small"),"--output_format","json","--output_dir",str(out),"--fp16","False"],14400)
            fs=sorted(out.glob("*.json")); data=json.loads(fs[0].read_text()) if fs else {}; cues=[(float(x.get("start",0)),str(x.get("text") or "").strip()) for x in data.get("segments",[]) if str(x.get("text") or "").strip()]
        text="\n".join(f"{_stamp(t)} - {v}" for t,v in cues)
        return {"text":text,"cues":[{"start":t,"text":v} for t,v in cues],"source":"asr"}
