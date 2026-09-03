"""Bounded source metadata projection; never invents meeting facts."""
from __future__ import annotations
import datetime as dt, json, shutil, subprocess
from typing import Any, Dict, Mapping

def _metadata(url:str)->dict:
    if not url or not shutil.which("yt-dlp"): return {}
    try:
        p=subprocess.run(["yt-dlp","--dump-single-json","--skip-download","--no-playlist","--no-warnings",url],capture_output=True,text=True,timeout=90)
        return json.loads(p.stdout) if p.returncode==0 and p.stdout.strip() else {}
    except Exception: return {}

def _iso(v:Any)->str:
    try: return dt.datetime.fromtimestamp(float(v),tz=dt.timezone.utc).isoformat().replace("+00:00","Z") if v not in (None,"") else ""
    except Exception: return ""

def duration_label(v:Any)->str:
    try: total=max(0,int(round(float(v))))
    except Exception: return ""
    h,r=divmod(total,3600); m,s=divmod(r,60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def extract(source_media:Mapping[str,Any],source_ref:str="",metadata:Mapping[str,Any]|None=None)->Dict[str,Any]:
    media=dict(source_media or {}); info=dict(metadata or {})
    if not info and str(media.get("provider","")).lower()=="youtube": info=_metadata(source_ref or str(media.get("canonical_ref", "")))
    seconds=info.get("duration",media.get("duration_seconds",0)); channel=info.get("channel") or info.get("uploader") or media.get("creator") or ""
    canonical=info.get("webpage_url") or info.get("original_url") or media.get("canonical_ref") or media.get("input_ref") or source_ref
    published=_iso(info.get("release_timestamp") or info.get("timestamp"))
    upload=str(info.get("upload_date") or ""); upload=f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}" if len(upload)==8 and upload.isdigit() else upload
    return {"provider":str(media.get("provider") or ""),"source_url":str(canonical or ""),"video_url":str(canonical or ""),"video_id":str(info.get("id") or ""),"video_title":str(info.get("title") or media.get("title") or ""),"description":str(info.get("description") or ""),"thumbnail":str(info.get("thumbnail") or ""),"duration_seconds":seconds,"duration":duration_label(seconds),"published_at":published or upload,"upload_date":upload,"live_status":str(info.get("live_status") or ""),"channel":str(channel),"channel_name":str(channel),"channel_id":str(info.get("channel_id") or info.get("uploader_id") or ""),"channel_url":str(info.get("channel_url") or info.get("uploader_url") or ""),"uploader":str(info.get("uploader") or channel),"uploader_id":str(info.get("uploader_id") or ""),"uploader_url":str(info.get("uploader_url") or ""),"view_count":info.get("view_count"),"like_count":info.get("like_count"),"comment_count":info.get("comment_count"),"tags":list(info.get("tags") or []),"categories":list(info.get("categories") or []),"license":str(info.get("license") or "")}

def apply(payload:Dict[str,Any],source_media:Mapping[str,Any],source_ref:str="")->Dict[str,Any]:
    fields=extract(source_media,source_ref); payload["source_fields"]=fields
    for k,v in {"poster":fields["thumbnail"],"duration":fields["duration"],"duration_seconds":fields["duration_seconds"],"channel":fields["channel"],"channel_name":fields["channel_name"],"video_id":fields["video_id"],"source_url":fields["source_url"],"source_title":fields["video_title"],"source_description":fields["description"],"source_published_at":fields["published_at"],"source_provider":fields["provider"]}.items():
        if payload.get(k) in (None,"",[]) and v not in (None,"",[]): payload[k]=v
    return fields
