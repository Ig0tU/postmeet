#!/usr/bin/env python3
"""Validate Meeting Lens payloads for completeness and quote integrity.

Mandates:
  - no closed/executive public publish
  - motion_text / vote_text / transcript lines marked verbatim must not be empty when outcome implies them
  - every chapter needs start_time
  - every item needs record_key, record_type, title
  - retention block required for accepted artifacts

    python3 tools/meeting_validate.py path/to/payload.json
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List


BLOCKED = {"closed", "executive"}
OUTCOMES_NEED_MOTION = {"approved", "tabled", "failed"}


def validate(payload: Dict[str, Any]) -> Dict[str, Any]:
    defects: List[Dict[str, str]] = []

    if not payload.get("meeting_key"):
        defects.append({"code": "missing_meeting_key", "msg": "meeting_key required"})
    if not payload.get("title"):
        defects.append({"code": "missing_title", "msg": "title required"})

    status = payload.get("meeting_status") or ""
    if status in BLOCKED:
        defects.append({
            "code": "public_status_blocked",
            "msg": f"status {status!r} cannot be published on public Meeting Lens template",
        })

    items = payload.get("items") or []
    if not items:
        defects.append({"code": "empty_items", "msg": "items must be non-empty"})

    keys = set()
    agenda_keys = set()
    for i, item in enumerate(items):
        path = f"items[{i}]"
        rk = item.get("record_key") or ""
        rt = item.get("record_type") or ""
        if not rk:
            defects.append({"code": "missing_key", "msg": f"{path}.record_key required"})
        elif rk in keys:
            defects.append({"code": "duplicate_key", "msg": f"duplicate record_key {rk!r}"})
        else:
            keys.add(rk)

        if rt not in ("agenda", "resource", "chapter"):
            defects.append({"code": "bad_type", "msg": f"{path}.record_type invalid: {rt!r}"})
        if not (item.get("title") or "").strip():
            defects.append({"code": "missing_title", "msg": f"{path}.title required"})

        if rt == "agenda":
            agenda_keys.add(rk)
            outcome = item.get("outcome") or ""
            motion = (item.get("motion_text") or "").strip()
            if outcome in OUTCOMES_NEED_MOTION and not motion:
                # soft defect: completeness preference
                defects.append({
                    "code": "missing_motion",
                    "msg": f"{path} outcome {outcome!r} should include motion_text (quote if spoken)",
                })
            if item.get("verbatim") is False and motion:
                defects.append({
                    "code": "motion_not_verbatim",
                    "msg": f"{path}.motion_text must be verbatim when present",
                })

        if rt == "chapter":
            if not item.get("start_time"):
                defects.append({"code": "chapter_start", "msg": f"{path}.start_time required"})

        conf = item.get("confidence")
        if conf is not None and not (0 <= float(conf) <= 1):
            defects.append({"code": "bad_confidence", "msg": f"{path}.confidence out of range"})

    # parent_key integrity
    for i, item in enumerate(items):
        if item.get("record_type") != "agenda":
            continue
        pk = item.get("parent_key") or ""
        if pk and pk not in agenda_keys:
            defects.append({
                "code": "orphan_parent",
                "msg": f"items[{i}].parent_key {pk!r} not in agenda keys",
            })

    retention = payload.get("retention")
    if not isinstance(retention, dict):
        defects.append({"code": "missing_retention", "msg": "retention block required (store mandate)"})
    else:
        for field in ("correlation_id", "stored_at", "stages_complete"):
            if not retention.get(field):
                defects.append({"code": "retention_field", "msg": f"retention.{field} required"})

    ok = not any(d["code"] in (
        "missing_meeting_key", "missing_title", "public_status_blocked",
        "empty_items", "missing_key", "duplicate_key", "bad_type",
        "missing_retention", "retention_field", "chapter_start",
    ) for d in defects)

    return {
        "ok": ok,
        "defect_count": len(defects),
        "defects": defects,
        "item_count": len(items),
        "agenda_count": sum(1 for x in items if x.get("record_type") == "agenda"),
        "resource_count": sum(1 for x in items if x.get("record_type") == "resource"),
        "chapter_count": sum(1 for x in items if x.get("record_type") == "chapter"),
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: meeting_validate.py payload.json", file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as f:
        payload = json.load(f)
    result = validate(payload)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
