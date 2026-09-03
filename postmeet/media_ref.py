"""Resolve a recording/page reference into grounded media metadata."""
from __future__ import annotations
import ipaddress, os, socket
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import Any, Dict

MEDIA_EXT={".mp4",".m4v",".mov",".webm",".mkv",".avi",".mp3",".m4a",".wav",".aac",".ogg",".flac",".wma"}

def _http(s:str)->bool: return s.startswith(("http://","https://"))
def _private(url:str)->bool:
    host=(urlparse(url).hostname or "").lower()
    if host in {"localhost","localhost.localdomain"} or host.endswith(".local"): return True
    try:
        return any(ipaddress.ip_address(x[4][0]).is_private or ipaddress.ip_address(x[4][0]).is_loopback or ipaddress.ip_address(x[4][0]).is_link_local for x in socket.getaddrinfo(host,None,type=socket.SOCK_STREAM))
    except Exception: return False

def _guard(url:str,site_url:str=""):
    if not _http(url): raise ValueError("Only http(s) media references may be fetched remotely.")
    if os.getenv("POSTMEET_ALLOW_PRIVATE_URLS","").lower() in {"1","true","yes"}: return
    if site_url and urlparse(url).hostname==urlparse(site_url).hostname: return
    if _private(url): raise ValueError("Media URL resolves to a private/local network address.")

def normalize(source:str,*,site_url:str="",media_root:str="")->str:
    s=(source or "").strip()
    if not s: raise ValueError("A meeting recording or page URL is required.")
    if _http(s): _guard(s,site_url); return s
    if media_root:
        root=Path(media_root).expanduser().resolve(); p=(root/s.lstrip("/")).resolve()
        if p.is_file() and str(p).startswith(str(root)+os.sep): return str(p)
    if site_url:
        u=urljoin(site_url.rstrip("/")+"/",s.lstrip("/")); _guard(u,site_url); return u
    p=Path(s).expanduser()
    if p.is_file(): return str(p.resolve())
    raise ValueError(f"Could not resolve a recording at {s!r}.")

def _google_drive(url: str) -> str:
    p = urlparse(url)
    if "drive.google.com" not in (p.hostname or "").lower(): return ""
    import re
    m = re.search(r"/file/d/([^/]+)", p.path)
    return f"https://drive.google.com/uc?export=download&id={m.group(1)}" if m else ""

def resolve(source:str,*,site_url:str="",media_root:str="")->Dict[str,Any]:
    ref=normalize(source,site_url=site_url,media_root=media_root)
    if not _http(ref): return {"original_ref":source,"resolved_ref":ref,"canonical_ref":ref,"public_ref":"","title":Path(ref).stem,"provider":"local","kind":"local_media","duration":0,"meeting_score":0.0}
    gdrive = _google_drive(ref)
    if gdrive:
        return {"original_ref":source,"resolved_ref":gdrive,"canonical_ref":source,"public_ref":source,"title":"drive_media","provider":"google_drive","kind":"direct_media","duration":0,"meeting_score":0.0}
    path=Path(urlparse(ref).path); ext=path.suffix.lower()
    provider="youtube" if "youtube.com" in ref or "youtu.be" in ref else "vimeo" if "vimeo.com" in ref else "http"
    if provider == "http" and ext not in MEDIA_EXT:
        try:
            import requests, re
            r = requests.get(ref, headers={"User-Agent": "PostMeet/1.0"}, timeout=10)
            if "text/html" in (r.headers.get("content-type") or ""):
                m = re.search(r'<meta\b[^>]+(?:property|name)=["\'](?:og:video|og:video:url|og:video:secure_url)["\'][^>]+content=["\']([^"\']+)["\']', r.text, re.I)
                if not m: m = re.search(r'<(?:video|source)\b[^>]+src=["\']([^"\']+)["\']', r.text, re.I)
                if m:
                    cand = urljoin(ref, m.group(1).replace("&amp;", "&"))
                    return {"original_ref":source,"resolved_ref":cand,"canonical_ref":ref,"public_ref":cand,"title":path.stem,"provider":"direct_html","kind":"direct_media","duration":0,"meeting_score":0.0}
        except Exception: pass
    return {"original_ref":source,"resolved_ref":ref,"canonical_ref":ref,"public_ref":ref,"title":path.stem,"provider":provider,"kind":"direct_media" if ext in MEDIA_EXT else "web_page_candidate","duration":0,"meeting_score":0.0}
