#!/usr/bin/env python3
"""Deterministically hydrate a YOOtheme/Meeting Lens preset from accepted data."""
from __future__ import annotations
import copy, json, re
from typing import Any, Dict, List, Mapping, Set

PLACEHOLDER_RE = re.compile(r"\{([A-Z0-9_]+)\}")
_KEY_RE = re.compile(r"[^a-z0-9]+")
NON_DATA_PROPS = {"type","id","class","style","layout","position","width","height","margin","padding","transition","transition_duration","breakpoint","heading_level","title_element","image_align","image_margin","image_position","vertical_align","sticky_breakpoint","sticky_offset","card_style","status_style","resource_style","agenda_density","show_icons","show_search","show_filters","update_url","url_mode","url_parameter","remember_position","collapse_agenda","sticky_media","sync_enabled","follow_playback","scroll_active_item","default_panel","privacy_mode","youtube_nocookie","iframe_allowed_origins"}

def _norm(key: str) -> str: return _KEY_RE.sub("_", str(key or "").lower()).strip("_")
def _value(value: Any) -> str:
    if value is None: return ""
    if isinstance(value, bool): return "true" if value else "false"
    if isinstance(value, (dict,list,tuple)): return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)

def deep_fill(node: Any, mapping: Dict[str,str]) -> Any:
    if isinstance(node,str): return PLACEHOLDER_RE.sub(lambda m:mapping.get(m.group(1),m.group(0)),node)
    if isinstance(node,list): return [deep_fill(x,mapping) for x in node]
    if isinstance(node,dict): return {k:deep_fill(v,mapping) for k,v in node.items()}
    return node

def item_to_child(item: Dict[str,Any]) -> Dict[str,Any]:
    props={str(k):copy.deepcopy(v) for k,v in item.items() if not str(k).startswith("_")}
    rt=props.get("record_type"); props.setdefault("record_key",""); props.setdefault("title","")
    if rt=="agenda": props.setdefault("agenda_kind","information"); props.setdefault("outcome","discussed"); props.setdefault("highlight",False)
    elif rt=="resource": props.setdefault("resource_type","other"); props.setdefault("language","en"); props.setdefault("availability","published"); props.setdefault("open_new",True); props.setdefault("default_track",False)
    return {"type":"xs_meeting_lens_item","props":props}

def projection_context(payload: Mapping[str,Any]) -> Dict[str,Any]:
    p=dict(payload or {}); context={}
    def absorb(data: Mapping[str,Any], overwrite=False):
        for key,value in (data or {}).items():
            nk=_norm(str(key))
            if nk and (overwrite or nk not in context or context[nk] in (None,"",[])): context[nk]=value
    absorb(p.get("brand") or {}); absorb(p.get("source_media") or {}); absorb(p.get("source_fields") or {}); absorb(p,overwrite=True)
    items=list(p.get("items") or []); context.setdefault("items",items)
    for rt in ("agenda","resource","chapter"):
        rows=[x for x in items if isinstance(x,dict) and x.get("record_type")==rt]
        context.setdefault(rt+"_items",rows); context.setdefault(rt+"_count",len(rows))
        context.setdefault({"agenda":"agenda","resource":"resources","chapter":"chapters"}[rt],rows)
    context.setdefault("item_count",len(items))
    aliases={"youtube_url":context.get("video_url") or context.get("source_url") or context.get("recording_url"),"video":context.get("video_url") or context.get("recording_url"),"video_title":context.get("video_title") or context.get("source_title") or context.get("title"),"channel_name":context.get("channel_name") or context.get("channel") or context.get("creator"),"creator":context.get("creator") or context.get("channel") or context.get("channel_name"),"thumbnail":context.get("thumbnail") or context.get("poster"),"poster":context.get("poster") or context.get("thumbnail"),"description":context.get("source_description") or context.get("description") or context.get("summary"),"published_at":context.get("source_published_at") or context.get("published_at") or context.get("starts_at")}
    for k,v in aliases.items():
        if v not in (None,"",[]): context.setdefault(k,v)
    return context

def data_prop_keys(payload: Mapping[str,Any], context: Mapping[str,Any]) -> Set[str]:
    p=dict(payload or {}); keys=set()
    for data in (p,p.get("source_fields") or {},p.get("source_media") or {}):
        for key,value in data.items():
            nk=_norm(str(key))
            if not nk or nk in NON_DATA_PROPS: continue
            if isinstance(value,(dict,list)) and nk not in {"items","agenda","agenda_items","resources","resource_items","chapters","chapter_items","tags","categories"}: continue
            keys.add(nk)
    for key in ("youtube_url","video","video_url","video_id","video_title","source_url","source_title","source_description","source_published_at","source_provider","provider","channel","channel_name","channel_id","channel_url","creator","uploader","uploader_id","uploader_url","thumbnail","poster","duration","duration_seconds","description","published_at","upload_date","live_status","view_count","like_count","comment_count","tags","categories","license","recording_url"):
        if context.get(key) not in (None,"",[]): keys.add(key)
    return keys-NON_DATA_PROPS

def build_mapping(payload: Dict[str,Any]) -> Dict[str,str]:
    context=projection_context(payload); mapping={k.upper():_value(v) for k,v in context.items() if k and v is not None}; brand=payload.get("brand") or {}
    explicit={"MEETING_KEY":payload.get("meeting_key",""),"MEETING_TITLE":payload.get("title",""),"BODY_NAME":payload.get("body_name",""),"MEETING_TYPE":payload.get("meeting_type","regular"),"MEETING_STATUS":payload.get("meeting_status","complete"),"STARTS_AT":payload.get("starts_at",""),"ENDS_AT":payload.get("ends_at",""),"TIMEZONE_LABEL":payload.get("timezone_label",""),"LOCATION":payload.get("location",""),"LOCATION_LINK":payload.get("location_link",""),"ADDRESS":payload.get("address",""),"SUMMARY":payload.get("summary",""),"PUBLIC_NOTICE":payload.get("public_notice",""),"ACCOMMODATION_TEXT":payload.get("accommodation_text",""),"CONTACT_NAME":payload.get("contact_name",""),"CONTACT_LINK":payload.get("contact_link",""),"DURATION":payload.get("duration",""),"RECORDING_URL":payload.get("recording_url",""),"POSTER":payload.get("poster","") or context.get("thumbnail",""),"CAPTIONS_URL":payload.get("captions_url",""),"TRANSCRIPT_URL":payload.get("transcript_url",""),"TRANSCRIPT_STATUS":payload.get("transcript_status","reviewed"),"TRANSCRIPT_LANGUAGE":payload.get("transcript_language","en"),"TRANSCRIPT_TEXT":payload.get("transcript_text",""),"PRIMARY_RECORDING_KEY":payload.get("primary_recording_key",""),"INITIAL_AGENDA_KEY":payload.get("initial_agenda_key",""),"MEDIA_MODE":payload.get("media_mode","recording"),"MEDIA_PROVIDER":payload.get("media_provider","native"),"PRIMARY":brand.get("primary","#1e3a5f"),"SECONDARY":brand.get("secondary","#4a90a4"),"ACCENT":brand.get("accent","#c4a35a"),"LOGO_URL":brand.get("logo_url",""),"MASCOT_URL":brand.get("mascot_url",""),"FONT_DISPLAY":brand.get("font_display","Inter"),"FONT_BODY":brand.get("font_body","Inter"),"SOURCE_SITE":brand.get("source_site","")}
    mapping.update({k:_value(v) for k,v in explicit.items()}); return mapping

def _walk_props(node,context,replaceable):
    if isinstance(node,list):
        for x in node:_walk_props(x,context,replaceable)
    elif isinstance(node,dict):
        props=node.get("props")
        if isinstance(props,dict):
            for key,current in list(props.items()):
                nk=_norm(key); value=context.get(nk)
                if nk in context and nk not in NON_DATA_PROPS and value not in (None,"",[]) and (current in (None,"",[]) or nk in replaceable): props[key]=copy.deepcopy(value)
        for x in node.get("children") or []:_walk_props(x,context,replaceable)

def hydrate(preset: Dict[str,Any], payload: Dict[str,Any]) -> Dict[str,Any]:
    context=projection_context(payload); replaceable=data_prop_keys(payload,context); layout=deep_fill(copy.deepcopy(preset),build_mapping(payload)); _walk_props(layout,context,replaceable)
    stack=[layout]; lenses=[]
    while stack:
        n=stack.pop()
        if isinstance(n,dict):
            if n.get("type")=="xs_meeting_lens": lenses.append(n)
            stack.extend(n.get("children") or [])
        elif isinstance(n,list): stack.extend(n)
    for lens in lenses:
        lens["children"]=[item_to_child(it) for it in payload.get("items") or []]
        props=lens.setdefault("props",{})
        for key in list(props):
            nk=_norm(key)
            if nk in context and context[nk] not in (None,"",[]): props[key]=copy.deepcopy(context[nk])
    layout["_hydration"]={"meeting_key":payload.get("meeting_key"),"item_count":len(payload.get("items") or []),"brand_source":(payload.get("brand") or {}).get("source_site",""),"correlation_id":(payload.get("retention") or {}).get("correlation_id",""),"source_provider":context.get("provider") or context.get("source_provider") or "","video_id":context.get("video_id") or "","channel":context.get("channel") or context.get("channel_name") or "","declared_source_fields":sorted((payload.get("source_fields") or {}).keys()),"replaceable_data_props":sorted(replaceable)}
    return layout
