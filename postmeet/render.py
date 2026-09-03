#!/usr/bin/env python3
"""meeting_render.py — hydrated meeting payload → UIkit HTML you can actually look at.

YOOtheme renders the canonical layout.json server-side inside Joomla. This is the
read-only twin: same brand pack, same UIkit 3 class vocabulary, so what you see
here is what the Joomla page shows. It never edits the canonical JSON.

    python3 tools/meeting_render.py payload.json -o meeting.html
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

OUTCOME_BADGE = {
    "approved": ("Approved", "uk-label-success"),
    "failed": ("Failed", "uk-label-danger"),
    "voted": ("Voted", "uk-label-warning"),
    "moved": ("Motion made", "uk-label-warning"),
    "discussed": ("Discussed", "uk-label"),
}


def e(v: Any) -> str:
    return html.escape(str(v or ""), quote=True)


def _by_type(payload: Dict[str, Any], kind: str) -> List[dict]:
    return [i for i in payload.get("items") or [] if i.get("record_type") == kind]


def _seconds(ts: str) -> int:
    parts = [int(p) for p in str(ts or "0").split(":") if p.isdigit()]
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _embed(url: str) -> str:
    """YouTube/Vimeo → iframe; anything else → native <video>."""
    u = url or ""
    vid = ""
    if "youtube.com/watch?v=" in u:
        vid = u.split("watch?v=")[1].split("&")[0]
    elif "youtu.be/" in u:
        vid = u.split("youtu.be/")[1].split("?")[0]
    if vid:
        return (f'<iframe id="player" class="uk-width-1-1" style="aspect-ratio:16/9;border:0"'
                f' src="https://www.youtube.com/embed/{e(vid)}?enablejsapi=1"'
                f' allow="accelerometer;autoplay;encrypted-media;picture-in-picture"'
                f' allowfullscreen></iframe>')
    if not u:
        return '<div class="uk-placeholder uk-text-center">No recording linked.</div>'
    return (f'<video id="player" class="uk-width-1-1" controls preload="metadata"'
            f' src="{e(u)}"></video>')


def _agenda_card(item: dict, children: List[dict]) -> str:
    label, cls = OUTCOME_BADGE.get(item.get("outcome", ""), OUTCOME_BADGE["discussed"])
    num = item.get("agenda_number")
    start = item.get("start_time", "")
    seek = (f'<a class="uk-link-muted seek" data-t="{_seconds(start)}" href="#player">'
            f'<span uk-icon="play-circle"></span> {e(start)}</a>') if start else ""

    def body(it: dict) -> str:
        out = ""
        if it.get("motion_text"):
            out += (f'<div class="ml-verbatim"><span class="ml-tag">Motion</span>'
                    f'<blockquote>{e(it["motion_text"])}</blockquote></div>')
        if it.get("second_text"):
            out += (f'<div class="ml-verbatim"><span class="ml-tag">Second</span>'
                    f'<blockquote>{e(it["second_text"])}</blockquote></div>')
        if it.get("vote_text"):
            out += (f'<div class="ml-verbatim"><span class="ml-tag">Vote</span>'
                    f'<blockquote>{e(it["vote_text"])}</blockquote></div>')
        return out

    kids = ""
    for c in children:
        klabel, kcls = OUTCOME_BADGE.get(c.get("outcome", ""), OUTCOME_BADGE["discussed"])
        kids += (f'<li class="ml-child"><div class="uk-flex uk-flex-middle uk-flex-between">'
                 f'<strong>{e(c.get("title"))}</strong>'
                 f'<span class="uk-label {kcls}">{e(klabel)}</span></div>{body(c)}</li>')
    kids = f'<ul class="uk-list ml-children">{kids}</ul>' if kids else ""

    return f'''<article class="uk-card uk-card-default uk-card-small uk-card-body ml-item">
  <div class="uk-flex uk-flex-middle uk-flex-between uk-margin-small-bottom">
    <h3 class="uk-card-title uk-margin-remove">{f'<span class="ml-num">{e(num)}</span>' if num else ''}{e(item.get("title"))}</h3>
    <span class="uk-label {cls}">{e(label)}</span>
  </div>
  <p class="uk-text-meta uk-margin-remove-top">{seek}
     <span class="uk-margin-small-left">{e(item.get("agenda_kind", ""))}</span></p>
  {body(item)}
  {kids}
</article>'''


def render(payload: Dict[str, Any]) -> str:
    brand = payload.get("brand") or {}
    primary = brand.get("primary") or "#1e3a5f"
    accent = brand.get("accent") or "#c4a35a"
    font = brand.get("font_body") or "Inter"

    agenda = _by_type(payload, "agenda")
    tops = [a for a in agenda if not a.get("parent_key")]
    kids: Dict[str, List[dict]] = {}
    for a in agenda:
        if a.get("parent_key"):
            kids.setdefault(a["parent_key"], []).append(a)

    chapters = sorted(_by_type(payload, "chapter"), key=lambda c: _seconds(c.get("start_time", "")))
    resources = _by_type(payload, "resource")

    ch_html = "".join(
        f'<li><a class="seek uk-link-reset" data-t="{_seconds(c.get("start_time",""))}" href="#player">'
        f'<span class="ml-time">{e(c.get("start_time"))}</span> {e(c.get("title"))}</a></li>'
        for c in chapters) or '<li class="uk-text-meta">No chapters detected.</li>'

    ag_html = "".join(_agenda_card(a, kids.get(a.get("record_key", ""), [])) for a in tops) or (
        '<div class="uk-alert" uk-alert><p>No agenda structure was detected in this '
        'recording. Chapters and the transcript are still available below.</p></div>')

    res_html = "".join(
        f'<li><a href="{e(r.get("link"))}" target="_blank" rel="noopener">'
        f'<span uk-icon="link"></span> {e(r.get("title"))}</a> '
        f'<span class="uk-text-meta">{e(r.get("resource_type"))}</span></li>'
        for r in resources) or '<li class="uk-text-meta">No resources.</li>'

    transcript = e(payload.get("transcript_text", ""))
    counts = (f'{len(tops)} agenda items · {len(chapters)} chapters · '
              f'{len([a for a in agenda if a.get("motion_text")])} motions')

    return f'''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(payload.get("title") or payload.get("meeting_key"))}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/uikit@3/dist/css/uikit.min.css">
<style>
  :root{{--ml-primary:{e(primary)};--ml-accent:{e(accent)}}}
  body{{font-family:"{e(font)}",system-ui,sans-serif}}
  .ml-hero{{background:var(--ml-primary);color:#fff}}
  .ml-hero h1{{color:#fff;margin:0}}
  .ml-num{{display:inline-block;min-width:2em;color:var(--ml-accent);font-weight:700}}
  .ml-time{{display:inline-block;min-width:5em;color:var(--ml-accent);font-variant-numeric:tabular-nums}}
  .ml-item{{margin-bottom:1rem;border-left:4px solid var(--ml-primary)}}
  .ml-verbatim blockquote{{margin:.25rem 0 .75rem;padding-left:.9rem;
    border-left:3px solid var(--ml-accent);font-size:.94rem}}
  .ml-tag{{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--ml-primary);font-weight:700}}
  .ml-children{{border-top:1px dashed #ddd;padding-top:.6rem;margin-top:.6rem}}
  .ml-child{{padding-left:.8rem;border-left:2px solid var(--ml-accent)}}
  #transcript{{max-height:26rem;overflow:auto;white-space:pre-wrap;font-size:.86rem;line-height:1.7}}
</style></head><body>

<section class="uk-section uk-section-small ml-hero">
  <div class="uk-container">
    <h1>{e(payload.get("title") or "Meeting")}</h1>
    <p class="uk-margin-remove">{e(payload.get("body_name"))} {e(payload.get("starts_at"))}
       <span class="uk-margin-small-left">{e(counts)}</span></p>
  </div>
</section>

<div class="uk-container uk-margin-medium-top uk-margin-large-bottom">
  <div class="uk-grid-large" uk-grid>
    <div class="uk-width-2-3@m">
      {_embed(payload.get("recording_url", ""))}
      <p class="uk-text-meta uk-margin-small-top">{e(payload.get("summary"))}</p>
      <h2 class="uk-heading-line uk-margin-medium-top"><span>Agenda &amp; Outcomes</span></h2>
      {ag_html}
      <h2 class="uk-heading-line uk-margin-medium-top"><span>Transcript</span></h2>
      <div id="transcript" class="uk-card uk-card-default uk-card-small uk-card-body">{transcript}</div>
    </div>
    <div class="uk-width-1-3@m">
      <h3 class="uk-heading-bullet">Chapters</h3>
      <ul class="uk-list uk-list-divider">{ch_html}</ul>
      <h3 class="uk-heading-bullet uk-margin-medium-top">Resources</h3>
      <ul class="uk-list">{res_html}</ul>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/uikit@3/dist/js/uikit.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/uikit@3/dist/js/uikit-icons.min.js"></script>
<script>
// Seek links drive whichever player is present — <video> directly, YouTube via postMessage.
document.querySelectorAll(".seek").forEach(a => a.addEventListener("click", ev => {{
  const t = Number(a.dataset.t || 0), p = document.getElementById("player");
  if (!p) return;
  if (p.tagName === "VIDEO") {{ ev.preventDefault(); p.currentTime = t; p.play(); return; }}
  p.contentWindow.postMessage(JSON.stringify(
    {{event:"command", func:"seekTo", args:[t, true]}}), "*");
}}));
</script>
</body></html>'''


def demo() -> None:
    p = {
        "title": "Board Meeting", "recording_url": "https://youtu.be/abc123",
        "brand": {"primary": "#234423", "accent": "#c4a35a", "font_body": "Open Sans"},
        "transcript_text": "00:05 - call to order",
        "items": [
            {"record_type": "agenda", "record_key": "a1", "title": "Approval of Minutes",
             "agenda_number": "1", "agenda_kind": "action", "outcome": "approved",
             "start_time": "01:05", "motion_text": "I move we approve <the> minutes",
             "vote_text": "motion carries"},
            {"record_type": "agenda", "record_key": "a1-m2", "parent_key": "a1",
             "title": "Motion: appoint chair", "outcome": "failed", "agenda_kind": "action"},
            {"record_type": "chapter", "record_key": "c1", "title": "Opening",
             "start_time": "00:05", "end_time": "05:00"},
            {"record_type": "resource", "record_key": "r1", "title": "Meeting Recording",
             "resource_type": "recording", "link": "https://youtu.be/abc123"},
        ],
    }
    out = render(p)
    assert "youtube.com/embed/abc123" in out, "youtube url not embedded"
    assert "#234423" in out, "brand primary not applied"
    assert "uk-label-success" in out and "uk-label-danger" in out, "outcome badges missing"
    assert 'data-t="65"' in out, "seek offset wrong"
    # user/transcript text must never break out of the document
    assert "I move we approve &lt;the&gt; minutes" in out, "motion text not escaped"
    assert out.count("ml-child") >= 1, "child motion not nested"
    print("meeting_render demo ok")


def main() -> int:
    ap = argparse.ArgumentParser(description="meeting payload → viewable UIkit HTML")
    ap.add_argument("payload", nargs="?")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("-o", "--output", default="-")
    args = ap.parse_args()

    if args.demo or not args.payload:
        demo()
        return 0

    data = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    out = render(data)
    if args.output == "-":
        print(out)
    else:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
