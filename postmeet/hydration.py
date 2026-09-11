#!/usr/bin/env python3
"""Hydrate meeting/template layouts from validated payload + source metadata.

Deterministic. The template remains the schema: placeholders are filled only
from facts present in the accepted meeting payload, source descriptor, source
fields, or brand pack. Repeated meeting items retain every validated field
instead of being reduced to a hand-maintained subset.

    python3 tools/meeting_hydrate.py payload.json --preset path/to/meeting_lens_full.json -o out.json

When run inside SignalMesh repo, preset defaults to editor/presets/meeting_lens_full.json.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Set

from .media_ref import extract_youtube_id

PLACEHOLDER_RE = re.compile(r"\{([A-Z0-9_]+)\}")
_KEY_RE = re.compile(r"[^a-z0-9]+")

# Keys that are layout/configuration vocabulary rather than sourced content.
# A populated template may legitimately carry values for these; hydration must
# never overwrite them just because a payload happens to contain a similarly
# named key.
NON_DATA_PROPS = {
    "type", "id", "class", "style", "layout", "position", "width", "height",
    "margin", "padding", "transition", "transition_duration", "breakpoint",
    "heading_level", "title_element", "image_align", "image_margin",
    "image_position", "vertical_align", "sticky_breakpoint", "sticky_offset",
    "card_style", "status_style", "resource_style", "agenda_density",
    "show_icons", "show_search", "show_filters", "update_url", "url_mode",
    "url_parameter", "remember_position", "collapse_agenda", "sticky_media",
    "sync_enabled", "follow_playback", "scroll_active_item", "default_panel",
    "privacy_mode", "youtube_nocookie", "iframe_allowed_origins",
}


def _norm(key: str) -> str:
    return _KEY_RE.sub("_", str(key or "").lower()).strip("_")


def _placeholder_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def deep_fill(node: Any, mapping: Dict[str, str]) -> Any:
    if isinstance(node, str):
        def repl(m: re.Match) -> str:
            key = m.group(1)
            return mapping.get(key, m.group(0))
        return PLACEHOLDER_RE.sub(repl, node)
    if isinstance(node, list):
        return [deep_fill(x, mapping) for x in node]
    if isinstance(node, dict):
        return {k: deep_fill(v, mapping) for k, v in node.items()}
    return node


def item_to_child(item: Dict[str, Any]) -> Dict[str, Any]:
    """Map a validated item to an xs_meeting_lens_item without dropping fields.

    The old adapter manually copied a short list of known keys. That meant a
    template could declare a field that existed in the canonical item and still
    receive an empty value. Validation is the authority on accepted item data;
    hydration should project it, not silently narrow it.
    """
    props: Dict[str, Any] = {
        str(k): copy.deepcopy(v)
        for k, v in item.items()
        if not str(k).startswith("_")
    }
    rt = props.get("record_type")
    props.setdefault("record_key", "")
    props.setdefault("title", "")
    if rt == "agenda":
        props.setdefault("agenda_kind", "information")
        props.setdefault("outcome", "discussed")
        props.setdefault("highlight", False)
    elif rt == "resource":
        props.setdefault("resource_type", "other")
        props.setdefault("language", "en")
        props.setdefault("availability", "published")
        props.setdefault("open_new", True)
        props.setdefault("default_track", False)
    return {"type": "xs_meeting_lens_item", "props": props}


def projection_context(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Flatten the accepted data surfaces into template-facing field names.

    Precedence is deliberate: canonical meeting payload > source_fields >
    source_media > brand. A specialist can therefore correct a source title or
    poster without the platform metadata overwriting it later.
    """
    p = dict(payload or {})
    context: Dict[str, Any] = {}

    def absorb(data: Mapping[str, Any], *, overwrite: bool = False) -> None:
        for key, value in (data or {}).items():
            nk = _norm(str(key))
            if not nk:
                continue
            if overwrite or nk not in context or context[nk] in (None, "", []):
                context[nk] = value

    absorb(p.get("brand") or {})
    absorb(p.get("source_media") or {})
    absorb(p.get("source_fields") or {})
    absorb(p, overwrite=True)

    items = list(p.get("items") or [])
    context.setdefault("items", items)
    for record_type in ("agenda", "resource", "chapter"):
        rows = [x for x in items if isinstance(x, dict) and x.get("record_type") == record_type]
        context.setdefault(record_type + "_items", rows)
        context.setdefault(record_type + "_count", len(rows))
        # Common template noun: chapters/resources/agendas.
        plural = {"agenda": "agenda", "resource": "resources", "chapter": "chapters"}[record_type]
        context.setdefault(plural, rows)
    context.setdefault("item_count", len(items))

    yt_candidate = (
        p.get("youtube_url")
        or context.get("youtube_url")
        or (p.get("source_fields") or {}).get("youtube_url")
        or (p.get("source_media") or {}).get("youtube_url")
    )
    if yt_candidate:
        yt_id = extract_youtube_id(yt_candidate)
        if yt_id:
            embed_url = f"https://www.youtube-nocookie.com/embed/{yt_id}?enablejsapi=1"
            context["youtube_url"] = yt_candidate
            context["youtube_id"] = yt_id
            context["recording_url"] = embed_url
            context["video_url"] = embed_url
            context["media_provider"] = "youtube"

    # Stable aliases used by Vlog/channel templates in addition to Meeting Lens.
    aliases = {
        "youtube_url": context.get("youtube_url") or context.get("video_url") or context.get("source_url") or context.get("recording_url"),
        "video": context.get("video_url") or context.get("recording_url"),
        "video_title": context.get("video_title") or context.get("source_title") or context.get("title"),
        "channel_name": context.get("channel_name") or context.get("channel") or context.get("creator"),
        "creator": context.get("creator") or context.get("channel") or context.get("channel_name"),
        "thumbnail": context.get("thumbnail") or context.get("poster"),
        "poster": context.get("poster") or context.get("thumbnail"),
        "description": context.get("source_description") or context.get("description") or context.get("summary"),
        "published_at": context.get("source_published_at") or context.get("published_at") or context.get("starts_at"),
    }
    for key, value in aliases.items():
        if value not in (None, "", []):
            context.setdefault(key, value)
    return context


def data_prop_keys(payload: Mapping[str, Any], context: Mapping[str, Any]) -> Set[str]:
    """Fields a populated template is allowed to have replaced by source data.

    This set is derived from the canonical payload/source objects rather than a
    fixed Vlog field list, so a site's template can add a future YouTube/source
    field without requiring another hydrator edit. Container and style keys are
    excluded explicitly.
    """
    p = dict(payload or {})
    keys: Set[str] = set()
    for data in (p, p.get("source_fields") or {}, p.get("source_media") or {}):
        for key, value in data.items():
            nk = _norm(str(key))
            if not nk or nk in NON_DATA_PROPS:
                continue
            if isinstance(value, (dict, list)) and nk not in {
                "items", "agenda", "agenda_items", "resources", "resource_items",
                "chapters", "chapter_items", "tags", "categories",
            }:
                continue
            keys.add(nk)

    # Derived aliases are also canonical template-facing facts.
    for key in (
        "youtube_url", "video", "video_url", "video_id", "video_title",
        "source_url", "source_title", "source_description", "source_published_at",
        "source_provider", "provider", "channel", "channel_name", "channel_id",
        "channel_url", "creator", "uploader", "uploader_id", "uploader_url",
        "thumbnail", "poster", "duration", "duration_seconds", "description",
        "published_at", "upload_date", "live_status", "view_count", "like_count",
        "comment_count", "tags", "categories", "license", "recording_url",
    ):
        if context.get(key) not in (None, "", []):
            keys.add(key)
    return keys - NON_DATA_PROPS


def build_mapping(payload: Dict[str, Any]) -> Dict[str, str]:
    """Return placeholder values for every accepted field, not a fixed whitelist."""
    context = projection_context(payload)
    mapping = {
        key.upper(): _placeholder_value(value)
        for key, value in context.items()
        if key and value is not None
    }

    # Backward-compatible explicit names. These also document the canonical
    # Meeting Lens contract and provide defaults where a source has no value.
    brand = payload.get("brand") or {}
    yt_candidate = (
        payload.get("youtube_url")
        or context.get("youtube_url")
        or (payload.get("source_fields") or {}).get("youtube_url")
        or (payload.get("source_media") or {}).get("youtube_url")
    )
    rec_url = context.get("recording_url") or payload.get("recording_url", "")
    if yt_candidate:
        yt_id = extract_youtube_id(yt_candidate)
        if yt_id:
            rec_url = f"https://www.youtube-nocookie.com/embed/{yt_id}?enablejsapi=1"

    explicit = {
        "MEETING_KEY": payload.get("meeting_key", ""),
        "MEETING_TITLE": payload.get("title", ""),
        "BODY_NAME": payload.get("body_name", ""),
        "MEETING_TYPE": payload.get("meeting_type", "regular"),
        "MEETING_STATUS": payload.get("meeting_status", "complete"),
        "STARTS_AT": payload.get("starts_at", ""),
        "ENDS_AT": payload.get("ends_at", ""),
        "TIMEZONE_LABEL": payload.get("timezone_label", ""),
        "LOCATION": payload.get("location", ""),
        "LOCATION_LINK": payload.get("location_link", ""),
        "ADDRESS": payload.get("address", ""),
        "SUMMARY": payload.get("summary", ""),
        "PUBLIC_NOTICE": payload.get("public_notice", ""),
        "ACCOMMODATION_TEXT": payload.get("accommodation_text", ""),
        "CONTACT_NAME": payload.get("contact_name", ""),
        "CONTACT_LINK": payload.get("contact_link", ""),
        "DURATION": payload.get("duration", ""),
        "RECORDING_URL": rec_url,
        "POSTER": payload.get("poster", "") or context.get("thumbnail", ""),
        "CAPTIONS_URL": payload.get("captions_url", ""),
        "TRANSCRIPT_URL": payload.get("transcript_url", ""),
        "TRANSCRIPT_STATUS": payload.get("transcript_status", "reviewed"),
        "TRANSCRIPT_LANGUAGE": payload.get("transcript_language", "en"),
        "TRANSCRIPT_TEXT": payload.get("transcript_text", ""),
        "PRIMARY_RECORDING_KEY": payload.get("primary_recording_key", ""),
        "INITIAL_AGENDA_KEY": payload.get("initial_agenda_key", ""),
        "MEDIA_MODE": payload.get("media_mode", "recording"),
        "MEDIA_PROVIDER": payload.get("media_provider", "native"),
        "PRIMARY": brand.get("primary", "#1e3a5f"),
        "SECONDARY": brand.get("secondary", "#4a90a4"),
        "ACCENT": brand.get("accent", "#c4a35a"),
        "LOGO_URL": brand.get("logo_url", ""),
        "MASCOT_URL": brand.get("mascot_url", ""),
        "FONT_DISPLAY": brand.get("font_display", "Inter"),
        "FONT_BODY": brand.get("font_body", "Inter"),
        "SOURCE_SITE": brand.get("source_site", ""),
    }
    mapping.update({k: _placeholder_value(v) for k, v in explicit.items()})
    return mapping


def find_meeting_lens_nodes(layout: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Locate every xs_meeting_lens element in the layout tree."""
    found: List[Dict[str, Any]] = []
    stack: List[Any] = [layout]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            if n.get("type") == "xs_meeting_lens":
                found.append(n)
            stack.extend(n.get("children") or [])
        elif isinstance(n, list):
            stack.extend(n)
    return found


def find_meeting_lens_node(layout: Dict[str, Any]) -> Dict[str, Any] | None:
    """Backward-compatible singular lookup."""
    nodes = find_meeting_lens_nodes(layout)
    return nodes[0] if nodes else None


def _hydrate_declared_props(node: Any, context: Mapping[str, Any], replaceable: Set[str]) -> None:
    """Hydrate explicitly declared data props, including populated examples.

    Empty exact-name slots are safe to fill from context. Non-empty sample data
    is replaced only when the prop name is in ``replaceable``; styling/config
    props remain authored template data.
    """
    if isinstance(node, list):
        for child in node:
            _hydrate_declared_props(child, context, replaceable)
        return
    if not isinstance(node, dict):
        return
    props = node.get("props")
    if isinstance(props, dict):
        for key, current in list(props.items()):
            nk = _norm(str(key))
            if nk not in context or nk in NON_DATA_PROPS:
                continue
            value = context[nk]
            if value in (None, "", []):
                continue
            if current in (None, "", []) or nk in replaceable:
                props[key] = copy.deepcopy(value)
    for child in node.get("children") or []:
        _hydrate_declared_props(child, context, replaceable)


def hydrate(preset: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    context = projection_context(payload)
    replaceable = data_prop_keys(payload, context)
    layout = deep_fill(copy.deepcopy(preset), build_mapping(payload))
    _hydrate_declared_props(layout, context, replaceable)

    # A template may contain more than one lens (desktop/mobile variants). Keep
    # them consistent instead of silently hydrating only the first match.
    for lens in find_meeting_lens_nodes(layout):
        lens["children"] = [item_to_child(it) for it in payload.get("items") or []]
        props = lens.setdefault("props", {})
        for key in list(props):
            nk = _norm(str(key))
            if nk in context and context[nk] not in (None, "", []):
                # Only overwrite a declared prop. The template owns which fields
                # exist; accepted payload data owns their value.
                props[key] = copy.deepcopy(context[nk])

    from datetime import datetime, timezone
    layout["version"] = "5.0.43"
    layout["modified"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if payload.get("title"):
        layout["name"] = payload["title"]
    layout.pop("_template_meta", None)
    layout.pop("_hydration", None)
    return layout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("payload", help="validated meeting payload JSON")
    ap.add_argument("--preset", default="editor/presets/meeting_lens_full.json")
    ap.add_argument("-o", "--output", default="-")
    args = ap.parse_args()

    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    preset_path = Path(args.preset)
    if not preset_path.exists():
        # fallback to package-local
        alt = Path(__file__).resolve().parent.parent / "presets" / "meeting_lens_full.json"
        if alt.exists():
            preset_path = alt
        else:
            print(f"preset not found: {args.preset}", file=sys.stderr)
            return 1
    preset = json.loads(preset_path.read_text(encoding="utf-8"))
    layout = hydrate(preset, payload)
    text = json.dumps(layout, indent=2)
    if args.output == "-":
        print(text)
    else:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
