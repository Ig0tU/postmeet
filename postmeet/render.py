#!/usr/bin/env python3
"""meeting_render.py — renders validated meeting payload into the exact DOM matching pgSrcTEMPLATE.html."""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List
from .media_ref import extract_youtube_id

ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def e(v: Any) -> str:
    return html.escape(str(v or ""), quote=True)


def _seconds(ts: str) -> int:
    parts = [int(p) for p in str(ts or "0").split(":") if p.isdigit()]
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _format_time(sec: int) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _embed_player(url: str, poster: str = "", captions_url: str = "", title: str = "") -> str:
    u = url or ""
    vid = extract_youtube_id(u)

    if vid:
        escaped_title = e(title or "Recording")
        return (f'<div class="xs-ml-player" data-xs-ml-player="" data-xs-ml-provider="youtube">\n'
                f'    <iframe id="player" width="1440" height="810" '
                f'src="https://www.youtube.com/embed/{vid}?enablejsapi=1" title="{escaped_title}" '
                f'frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" '
                f'referrerpolicy="strict-origin-when-cross-origin" allowfullscreen '
                f'style="width:100%; aspect-ratio:16/9; border-radius:8px; background:#000;"></iframe>\n'
                f'</div>')

    track_tag = f'<track kind="captions" src="{e(captions_url)}" srclang="en" label="Captions" default>' if captions_url else ""
    poster_attr = f' poster="{e(poster)}"' if poster else ""
    src = e(u) if u else "#"
    return (f'<div class="xs-ml-player" data-xs-ml-player data-xs-ml-provider="native">\n'
            f'<video id="player" controls preload="metadata" style="width:100%;aspect-ratio:16/9;border-radius:8px;background:#000;"{poster_attr}>\n'
            f'<source src="{src}">{track_tag}\n'
            f'Your browser does not support the video tag.\n'
            f'</video></div>')


def render(payload: Dict[str, Any]) -> str:
    css_file = ASSETS_DIR / "meeting-lens.css"
    js_file = ASSETS_DIR / "meeting-lens.js"
    css_content = css_file.read_text(encoding="utf-8") if css_file.exists() else ""
    js_content = js_file.read_text(encoding="utf-8") if js_file.exists() else ""

    root_id = "xs-meeting-lens-" + re.sub(r"[^a-f0-9]+", "", str(payload.get("meeting_key", "demo")))[:18]
    if len(root_id) < 22:
        root_id += "6a991af820f285"

    title = payload.get("title") or "Board of Education Meeting"
    body_name = payload.get("body_name") or "Community School Board"
    meeting_status = (payload.get("meeting_status") or "complete").lower()
    meeting_type = (payload.get("meeting_type") or "regular").capitalize()
    duration = payload.get("duration") or ""

    yt_url = (payload.get("youtube_url") or
              (payload.get("source_fields") or {}).get("youtube_url") or
              (payload.get("source_media") or {}).get("youtube_url") or "")
    rec_url = yt_url or payload.get("recording_url") or ""

    poster = payload.get("poster") or ""
    captions_url = payload.get("captions_url") or ""
    transcript_url = payload.get("transcript_url") or ""
    starts_at = payload.get("starts_at") or ""
    ends_at = payload.get("ends_at") or ""
    tz = payload.get("timezone_label") or "Eastern Time"
    location = payload.get("location") or "District Board Room"
    address = payload.get("address") or ""
    contact_name = payload.get("contact_name") or "Board Services Office"
    contact_link = payload.get("contact_link") or ""
    summary = payload.get("summary") or ""
    public_notice = payload.get("public_notice") or ""
    accommodation = payload.get("accommodation_text") or ""
    transcript_text = payload.get("transcript_text") or ""

    items = payload.get("items") or []
    agenda_all = [i for i in items if i.get("record_type") == "agenda"]
    chapters = [i for i in items if i.get("record_type") == "chapter"]
    resources = [i for i in items if i.get("record_type") == "resource"]

    # Top-level vs child agenda items (strictly max 1 level)
    top_map = {a.get("record_key"): a for a in agenda_all if not a.get("parent_key")}
    tops = list(top_map.values())
    children_by_parent: Dict[str, List[dict]] = {}

    for a in agenda_all:
        pk = a.get("parent_key")
        if pk:
            if pk in top_map:
                children_by_parent.setdefault(pk, []).append(a)
            else:
                tops.append(a)

    # Render Chapters
    ch_li_list = []
    for ch in chapters:
        ch_key = ch.get("record_key") or "chapter"
        ch_title = ch.get("title") or "Chapter"
        start_str = str(ch.get("start_time") or "0:00")
        sec = _seconds(start_str)
        speaker = ch.get("speaker") or ""
        ag_ref = ch.get("agenda_key") or ""
        desc = ch.get("chapter_summary") or ch.get("description") or ""

        ag_link = f'<a href="#{root_id}--agenda-{e(ag_ref)}">Agenda</a>' if ag_ref else ""
        speaker_html = f'<span>{e(speaker)}</span>' if speaker else ""
        meta_bits = [b for b in [speaker_html, ag_link] if b]
        meta_html = f'<div class="xs-ml-chapter-meta">{" ".join(meta_bits)}</div>' if meta_bits else ""
        desc_html = f'<div class="xs-ml-chapter-summary">{e(desc)}</div>' if desc else ""

        ch_li_list.append(f'''<li id="{root_id}--chapter-{e(ch_key)}"
    class="xs-ml-chapter xs-ml-record" data-xs-ml-record
    data-xs-ml-type="chapter" data-xs-ml-status="chapter"
    data-xs-ml-key="{e(ch_key)}" data-xs-ml-agenda="{e(ag_ref)}" data-xs-ml-start="{sec}"
    data-xs-ml-search="{e(ch_title)} {e(speaker)} {e(desc)}">
    <button type="button" class="xs-ml-time-button" data-xs-ml-seek="{sec}"
        data-xs-ml-chapter="{e(ch_key)}"
        aria-label="Play recording at {e(start_str)}: {e(ch_title)}">{e(start_str)}</button>
    <div>
        <div class="xs-ml-chapter-title">{e(ch_title)}</div>
        {meta_html}
        {desc_html}
    </div>
</li>''')
    chapters_html = "\n".join(ch_li_list)

    # Render Agenda Items
    def render_agenda_item(a: dict, level: int = 1) -> str:
        k = a.get("record_key") or "agenda"
        num = a.get("agenda_number") or ""
        a_title = a.get("title") or "Agenda Item"
        kind = (a.get("agenda_kind") or "information").capitalize()
        outcome = (a.get("outcome") or "discussed").lower()
        outcome_label = outcome.capitalize()
        desc = a.get("description") or ""
        presenter = a.get("presenter") or ""
        start = str(a.get("start_time") or "")
        highlight = "true" if a.get("highlight") else "false"

        seek_sec = _seconds(start) if start else 0
        seek_btn = (f'<button type="button" class="xs-ml-agenda-seek" data-xs-ml-seek="{seek_sec}" '
                    f'aria-label="Start recording at {seek_sec} seconds for {e(a_title)}">'
                    f'<span uk-icon="icon: play" aria-hidden="true"></span> Start at {e(start)} </button>') if start else ""

        pres_html = f'<div class="xs-ml-record-meta"><span>Presenter: {e(presenter)}</span></div>' if presenter else ""
        desc_html = f'<div class="xs-ml-agenda-description">{e(desc)}</div>' if desc else ""

        # Outcomes / Motions
        motion = a.get("motion_text") or ""
        second = a.get("second_text") or ""
        vote = a.get("vote_text") or ""
        outcome_parts = []
        if motion: outcome_parts.append(f'<p><strong>Motion:</strong> {e(motion)}</p>')
        if second: outcome_parts.append(f'<p><strong>Second:</strong> {e(second)}</p>')
        if vote: outcome_parts.append(f'<p><strong>Vote:</strong> {e(vote)}</p>')
        outcome_html = f'<div class="xs-ml-outcome">{"".join(outcome_parts)}</div>' if outcome_parts else ""

        # Strictly max 1 level of children
        kids_html = ""
        if level < 2:
            kids = children_by_parent.get(k, [])
            if kids:
                k_lis = [render_agenda_item(ch, level + 1) for ch in kids]
                kids_html = f'<ol class="xs-ml-agenda" data-xs-ml-agenda-level="{level + 1}">{"".join(k_lis)}</ol>'

        num_span = f'<span class="xs-ml-agenda-number">{e(num)}</span>' if num else ""

        return f'''<li id="{root_id}--agenda-{e(k)}"
    class="xs-ml-agenda-item xs-ml-record" data-xs-ml-record
    data-xs-ml-type="agenda" data-xs-ml-status="{e(outcome)}"
    data-xs-ml-key="{e(k)}"
    data-xs-ml-search="{e(num)} {e(a_title)} {e(desc)} {e(kind)} {e(presenter)} {e(outcome)} {e(motion)} {e(vote)}"
    data-highlight="{highlight}">
    <div class="xs-ml-agenda-head">
        <div class="xs-ml-agenda-label">
            {num_span}
            <div>
                <div class="xs-ml-agenda-kind">{e(kind)}</div>
                <h3 class="xs-ml-agenda-title">{e(a_title)}</h3>
            </div>
        </div>
        <span class="xs-ml-chip xs-ml-status-{e(outcome)}"> {e(outcome_label)} </span>
    </div>
    {desc_html}
    {pres_html}
    {seek_btn}
    {outcome_html}
    {kids_html}
</li>'''

    agenda_lis = [render_agenda_item(a, 1) for a in tops]
    agenda_html = "\n".join(agenda_lis)

    # Render Resources
    res_lis = []
    for r in resources:
        rk = r.get("record_key") or "resource"
        rtitle = r.get("title") or "Resource Document"
        rlink = r.get("link") or "#"
        rmime = r.get("mime_type") or "document"
        rsize = r.get("file_size") or ""
        rtype = (r.get("resource_type") or "Resource").capitalize()
        status = (r.get("availability") or "published").lower()

        icon = "file-text"
        if "video" in rmime or "recording" in rtype.lower(): icon = "video-camera"
        elif "audio" in rmime: icon = "receiver"
        elif "caption" in rtype.lower() or "vtt" in rmime: icon = "commenting"

        size_span = f'<span>{e(rsize)}</span>' if rsize else ""

        res_lis.append(f'''<li class="xs-ml-resource xs-ml-record" data-xs-ml-record
    data-xs-ml-type="resource" data-xs-ml-status="{e(status)}"
    data-xs-ml-key="{e(rk)}"
    data-xs-ml-search="{e(rtitle)} {e(rtype)} {e(rmime)} {e(status)}">
    <span class="xs-ml-resource-icon" uk-icon="icon: {icon}" aria-hidden="true"></span>
    <div class="xs-ml-resource-copy">
        <div>
            <a class="xs-ml-resource-title" href="{e(rlink)}" target="_blank" rel="noopener noreferrer">{e(rtitle)}</a>
            <span class="xs-ml-resource-state xs-ml-status-{e(status)}">{e(status.capitalize())}</span>
        </div>
        <div class="xs-ml-record-meta">
            <span>{e(rtype)}</span>
            <span>{e(rmime)}</span> {size_span}
        </div>
        <span class="xs-ml-print-url">{e(rlink)}</span>
    </div>
</li>''')
    resources_html = "\n".join(res_lis)

    # Build xs-ml-config object
    ch_config = []
    for ch in chapters:
        ch_k = ch.get("record_key") or "chapter"
        st = _seconds(str(ch.get("start_time") or "0:00"))
        ch_config.append({
            "key": ch_k,
            "title": ch.get("title") or "Chapter",
            "start": st,
            "end": st + 60,
            "agendaKey": ch.get("agenda_key") or "",
            "recordingKey": "recording"
        })

    vid = extract_youtube_id(rec_url)
    provider = "youtube" if vid else "native"
    embed_url = f"https://www.youtube.com/embed/{vid}?enablejsapi=1" if vid else ""

    config_obj = {
        "id": root_id,
        "key": payload.get("meeting_key", "meeting"),
        "media": {
            "provider": provider,
            "url": rec_url,
            "embedUrl": embed_url,
            "seekable": True,
            "valid": bool(rec_url)
        },
        "chapters": ch_config,
        "agendaKeys": [a.get("record_key") for a in agenda_all if a.get("record_key")],
        "initialAgenda": agenda_all[0].get("record_key") if agenda_all else "",
        "syncEnabled": True,
        "followPlayback": True,
        "scrollActive": False,
        "showSearch": True,
        "showFilters": True,
        "urlMode": "hash",
        "urlParameter": f"meeting_{payload.get('meeting_key', 'meeting')}",
        "updateUrl": True,
        "rememberPosition": "none",
        "storageKey": f"patches-xs-meeting-lens-{payload.get('meeting_key', 'meeting')}",
        "fingerprint": "postmeet-live",
        "privacyMode": False,
        "transitionDuration": 180
    }
    config_json_str = json.dumps(config_obj, separators=(',', ':'))

    summary_block = f'<div class="xs-ml-summary">{e(summary)}</div>' if summary else ''
    notice_block = f'<div class="xs-ml-notice"><strong>Public notice:</strong><br>{e(public_notice)}</div>' if public_notice else ''
    accomm_block = f'<div class="xs-ml-accommodation"><strong>Accessibility and accommodations:</strong><br>{e(accommodation)}</div>' if accommodation else ''

    resources_section = f'''<section class="xs-ml-section" id="{root_id}-resources">
        <div class="xs-ml-section-heading">
            <h2>Meeting resources</h2>
            <span>{len(resources)} items</span>
        </div>
        <ul class="xs-ml-resources">{resources_html}</ul>
    </section>''' if resources else ''

    transcript_section = f'''<section class="xs-ml-section" id="{root_id}-transcript">
        <div class="xs-ml-section-heading">
            <h2>Transcript</h2>
            <span>Auto</span>
        </div>
        <div class="xs-ml-transcript-text" lang="en">{e(transcript_text)}</div>
    </section>''' if transcript_text else ''

    media_links = []
    if rec_url:
        if provider == "youtube":
            media_links.append(f'<a href="{e(rec_url)}" target="_blank">Recording link</a>')
        else:
            media_links.append(f'<a href="{e(rec_url)}">Recording link</a>')
    if captions_url: media_links.append(f'<a href="{e(captions_url)}">Captions</a>')
    if transcript_url: media_links.append(f'<a href="{e(transcript_url)}">Transcript</a>')
    media_links_html = f'<div class="xs-ml-media-links">{" ".join(media_links)}</div>' if media_links else ''

    chapters_render = chapters_html if chapters_html else '<li class="uk-text-meta">No chapters defined.</li>'
    player_html = _embed_player(rec_url, poster, captions_url, title)

    inline_js = f"""
{js_content}

// Direct Instant Search & Seek Bindings
document.addEventListener("DOMContentLoaded", function() {{
    var root = document.querySelector('[data-xs-ml-root="{root_id}"]') || document.querySelector('.xs-meeting-lens');
    if (!root) return;

    var searchInput = root.querySelector('[data-xs-ml-search]');
    var typeSelect = root.querySelector('[data-xs-ml-filter-type]');
    var statusSelect = root.querySelector('[data-xs-ml-filter-status]');
    var clearBtn = root.querySelector('[data-xs-ml-clear]');
    var resultsEl = root.querySelector('[data-xs-ml-results]');
    var records = root.querySelectorAll('[data-xs-ml-record]');

    function filterRecords() {{
        var query = (searchInput ? searchInput.value : "").trim().toLowerCase();
        var typeVal = (typeSelect ? typeSelect.value : "").trim().toLowerCase();
        var statusVal = (statusSelect ? statusSelect.value : "").trim().toLowerCase();
        var count = 0;

        records.forEach(function(rec) {{
            var rType = (rec.getAttribute('data-xs-ml-type') || '').toLowerCase();
            var rStatus = (rec.getAttribute('data-xs-ml-status') || '').toLowerCase();
            var rSearch = (rec.getAttribute('data-xs-ml-search') || rec.textContent || '').toLowerCase();

            var matchQ = !query || rSearch.indexOf(query) !== -1;
            var matchT = !typeVal || rType === typeVal;
            var matchS = !statusVal || rStatus === statusVal;

            if (matchQ && matchT && matchS) {{
                rec.style.display = "";
                count++;
            }} else {{
                rec.style.display = "none";
            }}
        }});

        if (resultsEl) {{
            if (!query && !typeVal && !statusVal) {{
                resultsEl.textContent = "";
            }} else {{
                resultsEl.textContent = count + " item" + (count === 1 ? "" : "s") + " matching";
            }}
        }}
    }}

    if (searchInput) searchInput.addEventListener('input', filterRecords);
    if (typeSelect) typeSelect.addEventListener('change', filterRecords);
    if (statusSelect) statusSelect.addEventListener('change', filterRecords);
    if (clearBtn) {{
        clearBtn.addEventListener('click', function() {{
            if (searchInput) searchInput.value = "";
            if (typeSelect) typeSelect.value = "";
            if (statusSelect) statusSelect.value = "";
            filterRecords();
        }});
    }}

    // Video Seek Handlers
    var video = root.querySelector('video#player');
    var iframe = root.querySelector('iframe#player');
    
    root.querySelectorAll('[data-xs-ml-seek]').forEach(function(btn) {{
        btn.addEventListener('click', function(e) {{
            var sec = parseFloat(btn.getAttribute('data-xs-ml-seek') || '0');
            if (video) {{
                video.currentTime = sec;
                video.play().catch(function(){{}});
            }} else if (iframe && iframe.contentWindow) {{
                iframe.contentWindow.postMessage(JSON.stringify({{
                    event: "command",
                    func: "seekTo",
                    args: [sec, true]
                }}), "*");
            }}
        }});
    }});
}});
"""

    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} — {e(body_name)}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/uikit@3/dist/css/uikit.min.css">
<style>
{css_content}
</style>
</head>
<body>

<main class="uk-section uk-section-default" style="padding-top: 40px; padding-bottom: 80px;">
  <div class="uk-container">
    <article class="xs-meeting-lens xs-ml-layout-workspace xs-ml-media-width-two-fifths xs-ml-card-default xs-ml-resource-list xs-ml-agenda-comfortable xs-ml-gap-medium xs-ml-transition-fade"
        data-xs-ml-root="{root_id}"
        data-xs-ml-key="{e(payload.get('meeting_key', 'meeting'))}"
        data-xs-ml-ready="ready"
        style="--xs-ml-duration: 180ms; --xs-ml-sticky-offset: 24px;">

        <!-- Header -->
        <header class="xs-ml-header uk-card-default" id="{root_id}-overview">
            <div class="xs-ml-heading-row">
                <div>
                    <div class="xs-ml-kicker">{e(body_name)}</div>
                    <h2 class="xs-ml-title">{e(title)}</h2>
                </div>
                <span class="xs-ml-status xs-ml-status-{meeting_status} xs-ml-status-badge">
                    {meeting_status.capitalize()}
                </span>
            </div>

            <dl class="xs-ml-meta">
                <div>
                    <dt><span uk-icon="icon: calendar" aria-hidden="true"></span><span class="xs-ml-sr-only">Date</span></dt>
                    <dd>{e(starts_at) if starts_at else "Official Meeting Date"}<br>{e(tz)}</dd>
                </div>
                <div>
                    <dt><span uk-icon="icon: clock" aria-hidden="true"></span><span class="xs-ml-sr-only">Timing</span></dt>
                    <dd>{e(meeting_type)} meeting<br>Duration {e(duration) if duration else "—"}</dd>
                </div>
                <div>
                    <dt><span uk-icon="icon: location" aria-hidden="true"></span><span class="xs-ml-sr-only">Location</span></dt>
                    <dd>{e(location)}<br>{e(address)}</dd>
                </div>
                <div>
                    <dt><span uk-icon="icon: receiver" aria-hidden="true"></span><span class="xs-ml-sr-only">Contact</span></dt>
                    <dd><a href="{e(contact_link) if contact_link else '#'}">{e(contact_name)}</a></dd>
                </div>
            </dl>

            {summary_block}
            {notice_block}
            {accomm_block}
        </header>

        <!-- Search & Filter Toolbar -->
        <form class="xs-ml-toolbar" data-xs-ml-toolbar role="search" onsubmit="return false" style="display: grid;">
            <div class="xs-ml-field">
                <label for="{root_id}-search">Search this meeting</label>
                <input id="{root_id}-search" type="search" data-xs-ml-search placeholder="Agenda, presenter, document, chapter, or outcome">
            </div>
            <div class="xs-ml-field">
                <label for="{root_id}-type">Record type</label>
                <select id="{root_id}-type" data-xs-ml-filter-type>
                    <option value="">All records</option>
                    <option value="agenda">Agenda</option>
                    <option value="resource">Resources</option>
                    <option value="chapter">Chapters</option>
                </select>
            </div>
            <div class="xs-ml-field">
                <label for="{root_id}-status">Status</label>
                <select id="{root_id}-status" data-xs-ml-filter-status>
                    <option value="">All statuses</option>
                    <option value="planned">Planned</option>
                    <option value="discussed">Discussed</option>
                    <option value="approved">Approved</option>
                    <option value="denied">Denied</option>
                    <option value="tabled">Tabled</option>
                    <option value="published">Published</option>
                </select>
            </div>
            <div class="xs-ml-toolbar-actions">
                <button type="button" class="xs-ml-tool-button" data-xs-ml-clear>Reset</button>
                <button type="button" class="xs-ml-tool-button" onclick="window.print()">Print</button>
            </div>
            <p class="xs-ml-results" data-xs-ml-results aria-live="polite"></p>
        </form>

        <!-- Workspace (Left: Sticky Media, Right: Records) -->
        <div class="xs-ml-workspace xs-ml-workspace-left">
            <!-- Left Media Column -->
            <div class="xs-ml-media-column xs-ml-sticky xs-ml-sticky-medium">
                <section class="xs-ml-section" id="{root_id}-recording">
                    <div class="xs-ml-section-heading">
                        <h2 id="{root_id}-recording-title">Recording &amp; chapters</h2>
                        <button type="button" class="xs-ml-tool-button" data-xs-ml-follow aria-pressed="true">
                            Follow playback: <span data-xs-ml-follow-label>On</span>
                        </button>
                    </div>

                    {player_html}
                    {media_links_html}

                    <ol class="xs-ml-chapters" aria-label="Recording chapters">
                        {chapters_render}
                    </ol>
                </section>
            </div>

            <!-- Right Records Column -->
            <div class="xs-ml-record-column">
                <section class="xs-ml-section" id="{root_id}-agenda">
                    <div class="xs-ml-section-heading">
                        <h2 id="{root_id}-agenda-title">Agenda &amp; outcomes</h2>
                        <span>{len(agenda_all)} items</span>
                    </div>
                    <ol class="xs-ml-agenda" data-xs-ml-agenda-level="1">
                        {agenda_html}
                    </ol>
                </section>

                {resources_section}
                {transcript_section}
            </div>
        </div>

        <script type="application/json" data-xs-ml-config="{root_id}">{config_json_str}</script>
    </article>
  </div>
</main>

<script src="https://cdn.jsdelivr.net/npm/uikit@3/dist/js/uikit.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/uikit@3/dist/js/uikit-icons.min.js"></script>
<script>
{inline_js}
</script>
</body>
</html>'''


def main() -> int:
    ap = argparse.ArgumentParser(description="meeting payload → viewable UIkit HTML")
    ap.add_argument("payload", nargs="?")
    ap.add_argument("-o", "--output", default="-")
    args = ap.parse_args()

    if not args.payload:
        print("Usage: python3 meeting_render.py <payload.json> [-o meeting.html]")
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
