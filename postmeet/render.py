"""Read-only UIkit twin of a hydrated PostMeet payload."""
from __future__ import annotations
import html
from typing import Any

def e(v:Any)->str:return html.escape(str(v or ""),quote=True)
def secs(v:str)->int:
    try:
        p=[int(x) for x in str(v or "0").split(":")]; p=[0]*(3-len(p))+p; return p[0]*3600+p[1]*60+p[2]
    except Exception:return 0

def _player(url:str)->str:
    if "youtube.com/watch?v=" in url:
        vid=url.split("watch?v=",1)[1].split("&",1)[0]; return f'<iframe id="player" class="uk-width-1-1" style="aspect-ratio:16/9;border:0" src="https://www.youtube.com/embed/{e(vid)}?enablejsapi=1" allow="accelerometer;autoplay;encrypted-media;picture-in-picture" allowfullscreen></iframe>'
    if "youtu.be/" in url:
        vid=url.split("youtu.be/",1)[1].split("?",1)[0]; return f'<iframe id="player" class="uk-width-1-1" style="aspect-ratio:16/9;border:0" src="https://www.youtube.com/embed/{e(vid)}?enablejsapi=1" allowfullscreen></iframe>'
    return f'<video id="player" class="uk-width-1-1" controls preload="metadata" src="{e(url)}"></video>' if url else '<div class="uk-placeholder uk-text-center">No recording linked.</div>'

def render(payload:dict[str,Any])->str:
    brand=payload.get("brand") or {}; primary=brand.get("primary") or "#1e3a5f"; accent=brand.get("accent") or "#c4a35a"; font=brand.get("font_body") or "Inter"
    items=payload.get("items") or []; agenda=[x for x in items if x.get("record_type")=="agenda"]; tops=[x for x in agenda if not x.get("parent_key")]; chapters=sorted([x for x in items if x.get("record_type")=="chapter"],key=lambda x:secs(x.get("start_time"))); resources=[x for x in items if x.get("record_type")=="resource")]
    kids={}; [kids.setdefault(x.get("parent_key"),[]).append(x) for x in agenda if x.get("parent_key")]
    def badge(o): return {"approved":("Approved","uk-label-success"),"failed":("Failed","uk-label-danger"),"voted":("Voted","uk-label-warning"),"moved":("Motion made","uk-label-warning")}.get(o,("Discussed","uk-label"))
    def body(x):
        z=""; 
        for label,key in (("Motion","motion_text"),("Second","second_text"),("Vote","vote_text")):
            if x.get(key): z+=f'<div class="pm-verbatim"><span class="pm-tag">{label}</span><blockquote>{e(x[key])}</blockquote></div>'
        return z
    def card(x):
        label,cls=badge(x.get("outcome")); seek=f'<a class="seek" data-t="{secs(x.get("start_time"))}" href="#player">▶ {e(x.get("start_time"))}</a>' if x.get("start_time") else ""; ch="".join(f'<li><strong>{e(c.get("title"))}</strong><span class="uk-label">{e(badge(c.get("outcome"))[0])}</span>{body(c)}</li>' for c in kids.get(x.get("record_key"),[])); return f'<article class="uk-card uk-card-default uk-card-body pm-item"><div class="uk-flex uk-flex-between"><h3>{e(x.get("title"))}</h3><span class="uk-label {cls}">{e(label)}</span></div><p class="uk-text-meta">{seek} {e(x.get("agenda_kind"))}</p>{body(x)}'+(f'<ul class="uk-list pm-children">{ch}</ul>' if ch else "")+'</article>'
    ah="".join(card(x) for x in tops) or '<div class="uk-alert">No agenda structure was detected.</div>'; ch="".join(f'<li><a class="seek" data-t="{secs(x.get("start_time"))}" href="#player">{e(x.get("start_time"))} — {e(x.get("title"))}</a></li>' for x in chapters) or '<li>No chapters detected.</li>'; rh="".join(f'<li><a href="{e(x.get("link"))}" target="_blank" rel="noopener">{e(x.get("title"))}</a></li>' for x in resources) or '<li>No resources.</li>'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(payload.get("title") or payload.get("meeting_key"))}</title><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/uikit@3/dist/css/uikit.min.css"><style>:root{{--pm-primary:{e(primary)};--pm-accent:{e(accent)}}}body{{font-family:"{e(font)}",system-ui,sans-serif}}.pm-hero{{background:var(--pm-primary);color:#fff}}.pm-hero h1{{color:#fff}}.pm-item{{margin-bottom:1rem;border-left:4px solid var(--pm-primary)}}.pm-verbatim blockquote{{border-left:3px solid var(--pm-accent);padding-left:.9rem}}.pm-tag{{font-size:11px;text-transform:uppercase;font-weight:700;color:var(--pm-primary)}}#transcript{{max-height:26rem;overflow:auto;white-space:pre-wrap}}</style></head><body><section class="uk-section uk-section-small pm-hero"><div class="uk-container"><h1>{e(payload.get("title") or "Meeting")}</h1><p>{e(payload.get("body_name"))} {e(payload.get("starts_at"))}</p></div></section><div class="uk-container uk-margin-medium-top uk-margin-large-bottom"><div class="uk-grid-large" uk-grid><div class="uk-width-2-3@m">{_player(str(payload.get("recording_url") or payload.get("source_url") or ""))}<p>{e(payload.get("summary"))}</p><h2>Agenda &amp; Outcomes</h2>{ah}<h2>Transcript</h2><div id="transcript" class="uk-card uk-card-default uk-card-body">{e(payload.get("transcript_text"))}</div></div><div class="uk-width-1-3@m"><h3>Chapters</h3><ul class="uk-list uk-list-divider">{ch}</ul><h3>Resources</h3><ul class="uk-list">{rh}</ul></div></div></div><script src="https://cdn.jsdelivr.net/npm/uikit@3/dist/js/uikit.min.js"></script><script>document.querySelectorAll('.seek').forEach(a=>a.onclick=ev=>{{const p=document.getElementById('player'),t=Number(a.dataset.t||0);if(p&&p.tagName==='VIDEO'){{ev.preventDefault();p.currentTime=t;p.play()}}else if(p)p.contentWindow.postMessage(JSON.stringify({{event:'command',func:'seekTo',args:[t,true]}}),'*')}})</script></body></html>'''
