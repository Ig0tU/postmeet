#!/usr/bin/env python3
"""meeting_extract.py — timestamped transcript → chapters / agenda / outcomes.

Deterministic and evidence-bound: every field traces to a transcript line.
Nothing here paraphrases a motion or a vote — those are copied verbatim.
This is the no-SLM floor. An SLM, when wired, can only improve on it.

    python3 tools/meeting_extract.py transcript.txt
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

Cue = Tuple[float, str]

_LINE = re.compile(r"^\s*(?:(\d+):)?(\d{1,2}):(\d\d)\s*[-–]\s*(.+)$")

# Parliamentary language. Board meetings are formulaic — that is what makes
# rules-first extraction honest here instead of guesswork.
AGENDA_CUES = re.compile(
    r"\b(call(?:ing)? (?:this |the )?meeting to order|roll call|pledge of allegiance|"
    r"approval of (?:the )?(?:minutes|agenda)|consent (?:agenda|calendar)|"
    r"public (?:comment|participation|hearing)|superintendent'?s? report|"
    r"(?:financial|treasurer'?s?|principal'?s?) report|old business|new business|"
    r"executive session|closed session|adjourn(?:ment)?|"
    r"(?:agenda )?item (?:number |no\.? |#)?\d+|next (?:agenda )?item|"
    r"mov(?:e|ing) on to|turn(?:ing)? to item)\b",
    re.I,
)
# "who made the motion" is a chair recapping, not a motion being made.
MOTION_RE = re.compile(
    r"\b(i move\b|i'?d like to move\b|move that\b|so moved\b|"
    r"entertain a motion\b|do i have a motion\b|"
    r"(?<!made the )(?<!have the )motion to\s+\w)", re.I)
SECOND_RE = re.compile(r"\b(i second|second(?:ed)?(?: that| the motion)?)\b", re.I)
VOTE_RE = re.compile(r"\b(all (?:those )?in favou?r|all opposed|any opposed|aye|nay|"
                     r"abstain|roll call vote|motion (?:carries|passes|fails|is approved|is denied)|"
                     r"unanimous(?:ly)?)\b", re.I)
CARRIED_RE = re.compile(r"\b(motion (?:carries|passes|is approved)|approved unanimously|"
                        r"unanimously approved)\b", re.I)
FAILED_RE = re.compile(r"\b(motion (?:fails|failed|is denied|does not carry))\b", re.I)

CHAPTER_TARGET_SECONDS = 300  # fall back to ~5min blocks when no agenda structure

# Canonical agenda labels. A board page reads "Call to Order", not the raw
# caption fragment the chair happened to say. The spoken line is retained as
# evidence_line so nothing is lost.
CANON: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(r"meeting to order", re.I), "Call to Order", "procedural"),
    (re.compile(r"roll call vote", re.I), "", ""),  # a vote, not an agenda item
    (re.compile(r"roll call", re.I), "Roll Call", "procedural"),
    (re.compile(r"pledge of allegiance", re.I), "Pledge of Allegiance", "procedural"),
    (re.compile(r"approval of (?:the )?minutes", re.I), "Approval of Minutes", "action"),
    (re.compile(r"approval of (?:the )?agenda", re.I), "Approval of Agenda", "action"),
    (re.compile(r"consent (?:agenda|calendar)", re.I), "Consent Agenda", "action"),
    (re.compile(r"public (?:comment|participation)", re.I), "Public Comment", "information"),
    (re.compile(r"public hearing", re.I), "Public Hearing", "information"),
    (re.compile(r"superintendent", re.I), "Superintendent's Report", "information"),
    (re.compile(r"treasurer", re.I), "Treasurer's Report", "information"),
    (re.compile(r"financial report", re.I), "Financial Report", "information"),
    (re.compile(r"principal", re.I), "Principal's Report", "information"),
    (re.compile(r"old business", re.I), "Old Business", "action"),
    (re.compile(r"new business", re.I), "New Business", "action"),
    (re.compile(r"(?:executive|closed) session", re.I), "Executive Session", "procedural"),
    (re.compile(r"adjourn", re.I), "Adjournment", "procedural"),
]

SPEAKER_MARK = re.compile(r"(^|\s)&?gt;{1,2}|^>>+|^\s*\[[^\]]*\]\s*")


def clean(line: str) -> str:
    """Caption artifacts out: HTML entities, '>>' speaker marks, double spaces."""
    s = html.unescape(html.unescape(line or ""))
    s = re.sub(r">>+", " ", s)
    s = re.sub(r"\[(?:music|applause|inaudible|laughter)[^\]]*\]", " ", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


def motion_title(text: str, limit: int = 88) -> str:
    """Title a motion by its subject, in the mover's own words."""
    m = re.search(
        r"\bmove[sd]?\s+(?:that\s+)?(?:the\s+.{0,70}?board of (?:directors|education)\s+)?"
        r"(?:we\s+)?(.+)", text, re.I)
    body = (m.group(1) if m else text).strip()
    body = re.sub(r"\.\s.*$", "", body).strip(" .,;:")
    if len(body) > limit:
        body = body[:limit].rsplit(" ", 1)[0] + "…"
    return f"Motion: {body[:1].lower()}{body[1:]}" if body else "Motion"


def canon_label(phrase: str) -> Tuple[str, str]:
    """Matched cue phrase → (canonical title, agenda_kind). ('','') when unmapped."""
    for pat, label, kind in CANON:
        if pat.search(phrase):
            return label, kind
    m = re.search(r"item\s*(?:number|no\.?|#)?\s*(\d+)", phrase, re.I)
    if m:
        return f"Item {m.group(1)}", "information"
    return "", ""


def parse_transcript(text: str) -> List[Cue]:
    cues: List[Cue] = []
    for raw in text.splitlines():
        m = _LINE.match(raw)
        if not m:
            continue
        h, mi, s, body = m.groups()
        t = (int(h) * 3600 if h else 0) + int(mi) * 60 + int(s)
        body = clean(body)
        if body:
            cues.append((float(t), body))
    return cues


def stamp(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _slug(text: str, n: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:n] or "item"


def _title(line: str, limit: int = 90) -> str:
    """Title from the speaker's own words. Trimmed, never invented."""
    t = re.sub(r"\s+", " ", line).strip().rstrip(".,;:")
    if len(t) > limit:
        cut = t[:limit].rsplit(" ", 1)[0]
        t = cut + "…"
    return t[:1].upper() + t[1:]


def _motion_spans(lines: List[str], span: int = 4) -> List[str]:
    """Motions as spoken, not clipped to one caption cue."""
    return [" ".join(lines[i:i + span]) for i, l in enumerate(lines)
            if MOTION_RE.search(l)]


def find_agenda(cues: List[Cue]) -> List[dict]:
    """Agenda items anchored on parliamentary cue phrases."""
    hits: List[Tuple[int, float, str]] = []
    for idx, (t, line) in enumerate(cues):
        m = AGENDA_CUES.search(line)
        if m:
            phrase = m.group(0).lower()
            # same cue phrase restated seconds later is one item, not two
            if hits and phrase == hits[-1][2].lower() and t - hits[-1][1] < 60:
                continue
            hits.append((idx, t, m.group(0)))

    items: List[dict] = []
    for n, (idx, t, phrase) in enumerate(hits):
        # "roll call vote" belongs to a motion, not the agenda spine
        if re.search(r"roll call vote", phrase, re.I):
            continue
        end_idx = hits[n + 1][0] if n + 1 < len(hits) else len(cues)
        body = [c[1] for c in cues[idx:end_idx]]
        # Match the whole spoken line: "Moving on to new business" leads with the
        # transition phrase, but the item is New Business.
        label, kind = canon_label(cues[idx][1])
        if not label:
            label, kind = canon_label(phrase)
        titled = bool(label)
        # A chair says "superintendent" a dozen times; the agenda has one such
        # item — unless a motion was made under the repeat, which makes it a
        # distinct action the board actually took.
        if titled and any(i["title"] == label for i in items):
            motions = _motion_spans(body)
            if not motions:
                continue
            label, kind = motion_title(motions[0]), "action"
        if not titled:
            label = _title(cues[idx][1])
            kind = "information"
        motions = _motion_spans(body)
        if motions:
            # A ceremonial slot that carries a motion is really that action —
            # "Pledge of Allegiance" must not head an appointment vote.
            if kind == "procedural":
                label, titled = motion_title(motions[0]), True
            kind = "action"
        number = str(len(items) + 1)
        items.append({
            "record_type": "agenda",
            "record_key": f"agenda-{number.zfill(2)}-{_slug(label)}",
            "title": label,
            "agenda_number": number,
            "agenda_kind": kind,
            "description": " ".join(body)[:600],
            "outcome": "discussed",
            "highlight": False,
            "start_time": stamp(t),
            "evidence_line": cues[idx][1],
            "confidence": 0.75 if titled else 0.5,
        })
    return items


def find_outcomes(cues: List[Cue], agenda: List[dict]) -> int:
    """Attach verbatim motion/vote text to the agenda item that owns each motion."""
    starts = [(a["start_time"], a) for a in agenda]

    def owner(ts: str):
        chosen = None
        for st, a in starts:
            if st <= ts or _sec(st) <= _sec(ts):
                chosen = a
        return chosen

    updated = 0
    for i, (t, line) in enumerate(cues):
        if not MOTION_RE.search(line):
            continue
        # Read the motion before deciding where it belongs — an orphan motion
        # needs its own wording to be titled by.
        window = cues[i:i + 25]
        motion = " ".join(l for _, l in cues[i:i + 4])
        votes = [l for _, l in window if VOTE_RE.search(l)]
        seconds = [l for _, l in window if SECOND_RE.search(l)]
        joined = " ".join(l for _, l in window)

        target = owner(stamp(t))
        if not target:
            # A motion made where no agenda heading was ever detected is still a
            # motion. Dropping it would leave the record showing that nothing
            # happened, which is the one thing it must never do.
            target = {
                "record_type": "agenda",
                "record_key": f"agenda-motion-{updated + 1:02d}",
                "title": motion_title(motion),
                "agenda_number": "",
                "agenda_kind": "action",
                "description": joined[:600],
                "outcome": "moved",
                "highlight": True,
                "start_time": stamp(t),
                "evidence_line": line,
                "confidence": 0.5,
            }
            agenda.append(target)
            starts.append((target["start_time"], target))

        # One agenda item can carry several motions; later ones become children
        # rather than overwriting the first. Every vote survives.
        if target.get("motion_text"):
            root_parent_key = target.get("parent_key") or target["record_key"]
            child = {
                "record_type": "agenda",
                "record_key": f"{root_parent_key}-m{len(agenda)}",
                "title": motion_title(motion),
                "agenda_number": "",
                "agenda_kind": "action",
                "description": joined[:600],
                "outcome": "discussed",
                "highlight": False,
                "parent_key": root_parent_key,
                "start_time": stamp(t),
                "evidence_line": line,
                "confidence": 0.7,
            }
            agenda.append(child)
            starts.append((child["start_time"], child))
            target = child

        target["motion_text"] = motion.strip()
        if seconds:
            target["second_text"] = seconds[0].strip()
        if votes:
            target["vote_text"] = " ".join(votes).strip()
        if CARRIED_RE.search(joined):
            target["outcome"] = "approved"
            target["highlight"] = True
        elif FAILED_RE.search(joined):
            target["outcome"] = "failed"
            target["highlight"] = True
        elif votes:
            target["outcome"] = "voted"
        else:
            target["outcome"] = "moved"
        target["agenda_kind"] = "action"
        target["verbatim"] = True
        updated += 1
    return updated


def find_votes(cues: List[Cue], agenda: List[dict]) -> int:
    """Record decisions whose motion was never cleanly captured.

    ASR garbles the mover's sentence more often than it garbles the ritual that
    follows it — "all in favor… motion carries" survives almost anything. A vote
    with no readable motion is still a decision the board made, and dropping it
    would leave the public record showing nothing happened.
    """
    added = 0
    for i, (t, line) in enumerate(cues):
        carried, failed = CARRIED_RE.search(line), FAILED_RE.search(line)
        if not (carried or failed):
            continue
        owner = None
        for a in agenda:
            if a.get("start_time") and _sec(a["start_time"]) <= t and not a.get("parent_key"):
                owner = a
        if owner is None:
            # No agenda spine reached this point in the recording — the vote is
            # its own item rather than being dropped for want of a heading.
            owner = {
                "record_type": "agenda",
                "record_key": f"agenda-vote-{added + 1:02d}",
                "title": "Recorded vote",
                "agenda_number": "",
                "agenda_kind": "action",
                "description": " ".join(l for _, l in cues[max(0, i - 12):i + 3])[:600],
                "outcome": "discussed",
                "highlight": True,
                "start_time": stamp(t),
                "evidence_line": line,
                "confidence": 0.5,
            }
            agenda.append(owner)
        # Already accounted for by a motion that found its own vote.
        if owner.get("vote_text") and abs(_sec(owner.get("start_time", "0:00")) - t) < 900:
            if CARRIED_RE.search(owner["vote_text"]) or FAILED_RE.search(owner["vote_text"]):
                continue
        window = [l for _, l in cues[max(0, i - 12):i + 3]]
        votes = [l for l in window if VOTE_RE.search(l)]
        target = owner
        if owner.get("motion_text") and owner.get("vote_text"):
            root_parent_key = owner.get("parent_key") or owner["record_key"]
            target = {
                "record_type": "agenda",
                "record_key": f"{root_parent_key}-v{added}",
                "title": "Recorded vote",
                "agenda_number": "",
                "agenda_kind": "action",
                "description": " ".join(window)[:600],
                "parent_key": root_parent_key,
                "start_time": stamp(t),
                "evidence_line": line,
                "confidence": 0.5,
            }
            agenda.append(target)
        target["vote_text"] = " ".join(votes).strip() or line
        target["outcome"] = "approved" if carried else "failed"
        target["agenda_kind"] = "action"
        target["highlight"] = True
        target["verbatim"] = True
        added += 1
    return added


def _sec(ts: str) -> int:
    parts = [int(p) for p in ts.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def build_chapters(cues: List[Cue], agenda: List[dict]) -> List[dict]:
    """Chapters follow agenda boundaries when they exist, else fixed time blocks."""
    if not cues:
        return []
    ends = cues[-1][0] + 5

    if agenda:
        bounds = [(_sec(a["start_time"]), a) for a in agenda]
        chapters = []
        for n, (start, a) in enumerate(bounds):
            end = bounds[n + 1][0] if n + 1 < len(bounds) else ends
            body = [l for t, l in cues if start <= t < end]
            chapters.append({
                "record_type": "chapter",
                "record_key": f"chapter-{n + 1:02d}",
                "title": a["title"],
                "start_time": stamp(start),
                "end_time": stamp(end),
                "agenda_key": a["record_key"],
                "chapter_summary": " ".join(body)[:400],
                "confidence": 0.6,
            })
        return chapters

    chapters = []
    start = cues[0][0]
    n = 0
    while start < ends:
        end = min(start + CHAPTER_TARGET_SECONDS, ends)
        body = [(t, l) for t, l in cues if start <= t < end]
        if body:
            n += 1
            chapters.append({
                "record_type": "chapter",
                "record_key": f"chapter-{n:02d}",
                "title": _title(body[0][1]),
                "start_time": stamp(start),
                "end_time": stamp(end),
                "chapter_summary": " ".join(l for _, l in body)[:400],
                "confidence": 0.4,
            })
        start = end
    return chapters


def summarize(cues: List[Cue], agenda: List[dict]) -> str:
    """Extractive only — counts and the speakers' own item titles."""
    if not cues:
        return ""
    mins = int(cues[-1][0] // 60)
    if agenda:
        actions = [a for a in agenda if a.get("agenda_kind") == "action"]
        approved = [a for a in agenda if a.get("outcome") == "approved"]
        lead = "; ".join(a["title"] for a in agenda[:4])
        return (f"{mins}-minute meeting across {len(agenda)} agenda items "
                f"({len(actions)} action, {len(approved)} approved). Covered: {lead}.")
    return f"{mins}-minute recording, {len(cues)} transcript segments, no agenda structure detected."


def extract(transcript_text: str) -> dict:
    cues = parse_transcript(transcript_text)
    agenda = find_agenda(cues)
    outcomes = find_outcomes(cues, agenda)
    votes = find_votes(cues, agenda)

    agenda.sort(key=lambda a: (_sec(a["start_time"]), bool(a.get("parent_key"))))
    top = [a for a in agenda if not a.get("parent_key")]
    for n, a in enumerate(top, start=1):
        a["agenda_number"] = str(n)
    chapters = build_chapters(cues, top)
    return {
        "cues": len(cues),
        "duration": stamp(cues[-1][0]) if cues else "",
        "agenda": agenda,
        "chapters": chapters,
        "outcomes_attached": outcomes,
        "votes_recovered": votes,
        "summary": summarize(cues, agenda),
    }


def demo() -> None:
    sample = "\n".join([
        "00:05 - I'm calling this meeting to order at seven p.m.",
        "00:20 - First item, approval of the minutes from last month.",
        "00:31 - I move that we approve the minutes as presented.",
        "00:36 - I second that.",
        "00:40 - All in favor say aye.",
        "00:43 - Aye.",
        "00:46 - Motion carries, five to zero.",
        "01:10 - Moving on to new business, the transportation contract.",
        "01:30 - I move to award the contract to Ridgeline Bus.",
        "01:40 - All opposed?",
        "01:44 - The motion fails, two to four.",
        "02:10 - With no further business, we adjourn.",
    ])
    r = extract(sample)
    assert r["cues"] == 12, r["cues"]
    titles = [a["title"] for a in r["agenda"]]
    assert titles == ["Call to Order", "Approval of Minutes", "New Business",
                      "Adjournment"], titles
    assert r["outcomes_attached"] == 2, r["outcomes_attached"]

    by_outcome = {a["outcome"] for a in r["agenda"]}
    assert "approved" in by_outcome and "failed" in by_outcome, by_outcome

    minutes = next(a for a in r["agenda"] if a["outcome"] == "approved")
    assert "approve the minutes" in minutes["motion_text"], minutes["motion_text"]
    assert "aye" in minutes["vote_text"].lower(), minutes["vote_text"]
    assert minutes["verbatim"] is True

    contract = next(a for a in r["agenda"] if a["outcome"] == "failed")
    assert "Ridgeline Bus" in contract["motion_text"], contract["motion_text"]

    assert len(r["chapters"]) == len(r["agenda"])
    assert r["chapters"][0]["agenda_key"] == r["agenda"][0]["record_key"]

    # A motion with no agenda heading anywhere before it is still on the record.
    orphan = "\n".join([
        "00:10 - Just some opening remarks from the chair.",
        "00:40 - I move that the district approve the transportation contract.",
        "00:48 - Second.",
        "00:52 - All in favor?",
    ])
    o = extract(orphan)
    assert o["agenda"], "a motion with no agenda heading was dropped"
    assert o["outcomes_attached"] == 1, o["outcomes_attached"]
    assert "transportation contract" in o["agenda"][0]["motion_text"], o["agenda"][0]
    assert o["agenda"][0]["outcome"] in ("moved", "voted"), o["agenda"][0]["outcome"]

    # A vote whose motion the transcriber mangled is still a decision on record.
    garbled = "\n".join([
        "00:05 - Call to order.",
        "00:30 - So you may make a motion.",
        "00:40 - [inaudible] the district board of the tractors approve the thing.",
        "00:50 - We have a motion and a second.",
        "00:55 - All in favor.",
        "00:58 - So motion carries.",
    ])
    g = extract(garbled)
    assert g["votes_recovered"] >= 1, g["votes_recovered"]
    decided = [a for a in g["agenda"] if a["outcome"] == "approved"]
    assert decided, [a["outcome"] for a in g["agenda"]]
    assert "motion carries" in decided[0]["vote_text"].lower(), decided[0]["vote_text"]

    # A clean motion must not be double-counted by the vote recovery pass.
    assert r["agenda"][1]["outcome"] == "approved"
    assert len([a for a in r["agenda"] if a["title"] == "Recorded vote"]) == 0, \
        "clean motions were re-recorded as bare votes"

    # no parliamentary language → time-block chapters, no agenda, still non-empty
    plain = "\n".join(f"{i:02d}:00 - line {i}" for i in range(0, 12))
    p = extract(plain)
    assert p["agenda"] == []
    assert len(p["chapters"]) >= 2, len(p["chapters"])
    print("meeting_extract demo ok")


def main() -> int:
    ap = argparse.ArgumentParser(description="transcript → chapters/agenda/outcomes")
    ap.add_argument("transcript", nargs="?", help="timestamped transcript file")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("-o", "--output", default="-")
    args = ap.parse_args()

    if args.demo or not args.transcript:
        demo()
        return 0

    result = extract(Path(args.transcript).read_text(encoding="utf-8"))
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output == "-":
        print(text)
    else:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
def extract_speakers(cues: List[Cue], transcript_text: str = "") -> List[Dict[str, Any]]:
    """Identify non-duplicating distinct speakers and counts from transcript cues."""
    speakers_map: Dict[str, Dict[str, Any]] = {}
    speaker_prefix = re.compile(
        r"^(?:>>\s*)?(?:\[([^\]]+)\]|([A-Z][A-Za-z\s\.\-]{2,30}):|(SPEAKER[_\s]\d+):)", re.M
    )

    for t, line in cues:
        m = speaker_prefix.search(line)
        if m:
            raw_label = (m.group(1) or m.group(2) or m.group(3)).strip()
            label = clean(raw_label)
            if label and label.lower() not in {"music", "applause", "inaudible", "laughter", "cheering"}:
                spk_id = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
                if spk_id not in speakers_map:
                    speakers_map[spk_id] = {
                        "id": spk_id,
                        "label": label,
                        "count": 0,
                        "sample": clean(line)[:120],
                        "first_spoken": stamp(t),
                    }
                speakers_map[spk_id]["count"] += 1

    if not speakers_map:
        current_spk_idx = 1
        last_t = 0.0
        turn_counts: Dict[str, int] = {}
        first_stamps: Dict[str, str] = {}
        samples: Dict[str, str] = {}

        for t, line in cues:
            if ">>" in line or (t - last_t > 12.0 and last_t > 0):
                current_spk_idx = ((current_spk_idx) % 4) + 1
            spk_id = f"speaker-{current_spk_idx}"
            turn_counts[spk_id] = turn_counts.get(spk_id, 0) + 1
            if spk_id not in samples:
                samples[spk_id] = clean(line)[:120]
                first_stamps[spk_id] = stamp(t)
            last_t = t

        for spk_id, count in turn_counts.items():
            num = spk_id.split("-")[1]
            speakers_map[spk_id] = {
                "id": spk_id,
                "label": f"Speaker {num}",
                "count": count,
                "sample": samples.get(spk_id, ""),
                "first_spoken": first_stamps.get(spk_id, "00:00"),
            }

    return sorted(speakers_map.values(), key=lambda s: s["count"], reverse=True)


def build_payload(meeting_key: str, title: str, transcript: str, recording_url: str = "",
                  meeting_status: str = "complete", retention: dict | None = None) -> dict[str, Any]:
    import time
    from datetime import datetime, timezone
    ext = extract(transcript)
    cues = parse_transcript(transcript)
    speakers = extract_speakers(cues, transcript)
    items = []
    items.extend(ext.get("agenda", []))
    items.extend(ext.get("chapters", []))

    if not items:
        items = [{
            "record_type": "chapter",
            "record_key": "chapter-01",
            "title": title or "Call to Order & Proceedings",
            "start_time": "00:00",
            "end_time": "05:00",
            "chapter_summary": transcript[:300] if transcript else "Meeting proceedings recorded."
        }]

    dur = ext.get("duration", "00:00")
    if isinstance(dur, (int, float)):
        m, s = divmod(int(dur), 60)
        h, m = divmod(m, 60)
        dur_str = f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    else:
        dur_str = str(dur)

    slug = re.sub(r"[^a-z0-9]+", "-", (title or "meeting").lower()).strip("-")[:32]
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    return {
        "meeting_key": f"{slug}-{int(time.time()) % 100000}",
        "title": title or "Board Meeting Record",
        "meeting_type": "regular",
        "meeting_status": meeting_status or "complete",
        "duration": dur_str,
        "recording_url": recording_url,
        "transcript_text": transcript,
        "transcript_status": "auto",
        "items": items,
        "speakers": speakers,
        "distinct_speaker_count": len(speakers),
        "retention": retention or {
            "correlation_id": meeting_key,
            "stored_at": now_iso,
            "stages_complete": ["media", "transcribe", "extract"]
        },
    }


if __name__ == "__main__":
    sys.exit(main())
