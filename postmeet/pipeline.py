"""End-to-end standalone PostMeet runner. SignalMesh is optional, never required."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime,timezone
from .media_ref import resolve
from .asr import transcribe
from .extraction import build_payload
from .validation import validate
from .hydration import hydrate
from .render import render
from .source_fields import apply as apply_source

def run(source:str,*,site_url:str="",media_root:str="",model:str="",brand:dict|None=None,output_dir:str="postmeet-output",preset_path:str="presets/meeting_lens_full.json"):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    media=resolve(source,site_url=site_url,media_root=media_root)
    if brand is None and site_url:
        try:
            from .brand import extract
            brand=extract(site_url)
        except Exception: brand={}
    asr=transcribe(media["resolved_ref"],model=model)
    payload=build_payload(meeting_key=media.get("canonical_ref") or source,title=media.get("title") or "Post-Meeting Record",transcript=asr.get("text",[]),recording_url=media.get("public_ref") or media.get("resolved_ref") or source)
    payload["source_media"]=media
    if brand: payload["brand"]=brand
    apply_source(payload,media,source)
    retention=payload.setdefault("retention",{}); retention.setdefault("correlation_id",media.get("canonical_ref") or source); retention.setdefault("stored_at",datetime.now(timezone.utc).isoformat().replace("+00:00","Z")); retention.setdefault("stages_complete",["media","transcribe","extract","validate"])
    report=validate(payload)
    (out/"payload.json").write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    (out/"validation.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    if not report.get("ok"): raise ValueError("PostMeet validation failed: "+"; ".join(str(x) for x in report.get("defects",[])))
    preset=Path(preset_path)
    if not preset.exists(): preset=Path(__file__).resolve().parent.parent/"presets"/"meeting_lens_full.json"
    layout=hydrate(json.loads(preset.read_text(encoding="utf-8")),payload)
    (out/"layout.json").write_text(json.dumps(layout,indent=2,ensure_ascii=False),encoding="utf-8")
    (out/"meeting.html").write_text(render(payload),encoding="utf-8")
    return {"output_dir":str(out),"media":media,"asr":asr,"validation":report,"payload":str(out/"payload.json"),"layout":str(out/"layout.json"),"html":str(out/"meeting.html")}
