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

    kind = item.get("agenda_kind", "information")
    return f'''<article class="ml-item" data-kind="{e(kind)}">
  <div class="ml-item-header">
    <h3 class="ml-item-title">{f'<span class="ml-num">{e(num)}</span>' if num else ''}{e(item.get("title"))}</h3>
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
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(payload.get("title") or "Meeting Record")}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/uikit@3/dist/css/uikit.min.css">
<style>
  :root {{
    --ml-primary: {e(primary)};
    --ml-secondary: {e(secondary)};
    --ml-accent: {e(accent)};
  }}
  body {{
    font-family: "{e(font_body)}", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f8fafc;
    color: #1e293b;
    margin: 0;
    padding: 0;
  }}
  .ml-workspace {{
    max-width: 1440px;
    margin: 0 auto;
    padding: 24px 20px 60px;
  }}
  .ml-sticky-media {{
    position: sticky;
    top: 24px;
  }}
  .ml-player-card {{
    background: #000;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 20px -2px rgba(0,0,0,0.15);
  }}
  .ml-meta-card {{
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 20px;
    margin-top: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  }}
  .ml-meta-card h2 {{
    font-size: 1.25rem;
    font-weight: 700;
    margin: 0 0 8px;
    color: #0f172a;
  }}
  .ml-item {{
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 18px 20px;
    margin-bottom: 14px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    transition: transform 0.15s ease, border-color 0.15s ease;
  }}
  .ml-item:hover {{
    border-color: #cbd5e1;
    transform: translateY(-1px);
  }}
  .ml-item-header {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 6px;
  }}
  .ml-item-title {{
    font-size: 1.08rem;
    font-weight: 600;
    margin: 0;
    color: #0f172a;
  }}
  .ml-num {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 24px;
    height: 24px;
    background: #f1f5f9;
    color: var(--ml-primary);
    border-radius: 6px;
    font-size: 0.82rem;
    font-weight: 700;
    margin-right: 8px;
  }}
  .ml-seek-btn {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 0.78rem;
    font-weight: 600;
    color: #475569;
    text-decoration: none;
    cursor: pointer;
  }}
  .ml-seek-btn:hover {{
    background: #e2e8f0;
    color: #0f172a;
  }}
  .ml-verbatim {{
    margin-top: 10px;
    padding-left: 12px;
    border-left: 3px solid var(--ml-primary);
  }}
  .ml-verbatim blockquote {{
    margin: 2px 0 0;
    font-size: 0.92rem;
    color: #334155;
    font-style: normal;
  }}
  .ml-tag {{
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--ml-primary);
  }}
  .ml-search-bar {{
    position: relative;
    margin-bottom: 16px;
  }}
  .ml-search-input {{
    width: 100%;
    height: 42px;
    padding: 8px 14px 8px 38px;
    border-radius: 8px;
    border: 1px solid #cbd5e1;
    background: #fff;
    font-size: 0.92rem;
    outline: none;
    box-sizing: border-box;
  }}
  .ml-search-input:focus {{
    border-color: var(--ml-primary);
    box-shadow: 0 0 0 2px rgba(30,58,95,0.15);
  }}
  .ml-search-icon {{
    position: absolute;
    left: 12px;
    top: 11px;
    color: #94a3b8;
  }}
  .ml-filters {{
    display: flex;
    gap: 6px;
    margin-bottom: 16px;
    overflow-x: auto;
    padding-bottom: 4px;
  }}
  .ml-filter-btn {{
    background: #fff;
    border: 1px solid #e2e8f0;
    padding: 5px 12px;
    border-radius: 20px;
    font-size: 0.82rem;
    font-weight: 500;
    color: #475569;
    cursor: pointer;
    white-space: nowrap;
  }}
  .ml-filter-btn.active {{
    background: var(--ml-primary);
    border-color: var(--ml-primary);
    color: #fff;
  }}
  .ml-chapter-list {{
    list-style: none;
    padding: 0;
    margin: 0;
  }}
  .ml-chapter-item {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 10px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.88rem;
  }}
  .ml-chapter-item:hover {{
    background: #f1f5f9;
  }}
  #transcript {{
    max-height: 24rem;
    overflow-y: auto;
    font-size: 0.88rem;
    line-height: 1.65;
    background: #fff;
    padding: 16px;
    border-radius: 8px;
    border: 1px solid #e2e8f0;
    white-space: pre-wrap;
  }}
</style>
</head>
<body>

<div class="ml-workspace">
  <div class="uk-grid uk-grid-medium" uk-grid>
    <!-- Left Workspace Column: Sticky Media & Index -->
    <div class="uk-width-2-5@m">
      <div class="ml-sticky-media">
        <div class="ml-player-card">
          {_embed(payload.get("recording_url", ""))}
        </div>

        <div class="ml-meta-card">
          <h2>{e(payload.get("title") or "Meeting Record")}</h2>
          <div class="uk-flex uk-flex-middle uk-flex-between uk-margin-small-bottom">
            <span class="uk-text-meta">{e(payload.get("body_name") or "Public Board Meeting")}</span>
            <span class="uk-label uk-label-success">{e(payload.get("meeting_status", "complete").upper())}</span>
          </div>
          {f'<p class="uk-text-small uk-text-muted uk-margin-remove-top">{e(payload.get("summary"))}</p>' if payload.get("summary") else ''}
          <div class="uk-text-meta uk-margin-small-top">
            <span>{e(counts)}</span>
          </div>
        </div>

        <div class="ml-meta-card">
          <ul uk-tab>
            <li class="uk-active"><a href="#">Chapters</a></li>
            <li><a href="#">Resources</a></li>
            <li><a href="#">Transcript</a></li>
          </ul>
          <ul class="uk-switcher uk-margin-small-top">
            <li>
              <ul class="ml-chapter-list">
                {ch_html if ch_html else '<li class="uk-text-meta uk-text-muted">No chapters detected.</li>'}
              </ul>
            </li>
            <li>
              <ul class="uk-list uk-list-divider">
                {res_html if res_html else '<li class="uk-text-meta uk-text-muted">No external resources attached.</li>'}
              </ul>
            </li>
            <li>
              <div id="transcript">{transcript}</div>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <!-- Right Workspace Column: Search, Filter, Agenda Items -->
    <div class="uk-width-3-5@m">
      <div class="ml-search-bar">
        <span class="ml-search-icon" uk-icon="search"></span>
        <input class="ml-search-input" id="ml-search" type="text" placeholder="Search agenda items, motions, outcomes, or presenters...">
      </div>

      <div class="ml-filters" id="ml-filter-bar">
        <button class="ml-filter-btn active" data-filter="all">All Items</button>
        <button class="ml-filter-btn" data-filter="action">Action / Motions</button>
        <button class="ml-filter-btn" data-filter="consent">Consent</button>
        <button class="ml-filter-btn" data-filter="hearing">Hearing</button>
        <button class="ml-filter-btn" data-filter="information">Information</button>
      </div>

      <div id="ml-agenda-container">
        {ag_html}
      </div>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/uikit@3/dist/js/uikit.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/uikit@3/dist/js/uikit-icons.min.js"></script>
<script>
// Live search & filtering
const searchInput = document.getElementById("ml-search");
const items = document.querySelectorAll(".ml-item");
const filterBtns = document.querySelectorAll(".ml-filter-btn");
let activeFilter = "all";

function filterList() {{
  const query = searchInput.value.toLowerCase().trim();
  items.forEach(el => {{
    const kind = (el.dataset.kind || "").toLowerCase();
    const text = el.innerText.toLowerCase();
    const matchesFilter = activeFilter === "all" || kind.includes(activeFilter);
    const matchesQuery = !query || text.includes(query);
    el.style.display = matchesFilter && matchesQuery ? "" : "none";
  }});
}}

if (searchInput) searchInput.addEventListener("input", filterList);

filterBtns.forEach(btn => {{
  btn.addEventListener("click", () => {{
    filterBtns.forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    activeFilter = btn.dataset.filter;
    filterList();
  }});
}});

// Playhead seek triggers
document.querySelectorAll(".seek").forEach(a => a.addEventListener("click", ev => {{
  const t = Number(a.dataset.t || 0), p = document.getElementById("player");
  if (!p) return;
  if (p.tagName === "VIDEO") {{ ev.preventDefault(); p.currentTime = t; p.play(); return; }}
  p.contentWindow.postMessage(JSON.stringify({{event:"command", func:"seekTo", args:[t, true]}}), "*");
}}));
</script>
</body>
</html>'''


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
