#!/usr/bin/env python3
"""Extract color theme, logo, and mascot/insignia from a public site.

Rules-first (no LLM required). Broadcast-ready pack for meeting.brand frequency.

    python3 tools/brand_extract.py https://maplewood.mamboschools.com/
    python3 tools/brand_extract.py https://example.org --json

Does not invent brand colors: only tokens found in HTML/CSS/meta.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Dict, List, Optional, Set, Tuple

UA = {"User-Agent": "SignalMesh-BrandExtract/1.0"}

COLOR_RE = re.compile(
    r"#(?:[0-9a-fA-F]{3,4}){1,2}\b"
    r"|rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+(?:\s*,\s*[\d.]+)?\s*\)"
    r"|hsla?\(\s*\d+\s*,\s*[\d.]+%\s*,\s*[\d.]+%(?:\s*,\s*[\d.]+)?\s*\)",
    re.I,
)
VAR_COLOR_RE = re.compile(
    r"--(?:primary|secondary|accent|brand|theme|main|color-primary|color-secondary)"
    r"[-\w]*\s*:\s*([^;}+]+)",
    re.I,
)
FONT_RE = re.compile(r"font-family\s*:\s*([^;}+]+)", re.I)
LOGO_HINT = re.compile(r"logo|brand|site-title|navbar-brand", re.I)
MASCOT_HINT = re.compile(r"mascot|spirit|insignia|seal|crest|athletics|warrior|eagle|tiger|knight", re.I)


def fetch(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def abs_url(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, href)


class AssetCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stylesheets: List[str] = []
        self.icons: List[str] = []
        self.images: List[Tuple[str, str, str]] = []  # src, alt, class
        self.theme_color: Optional[str] = None
        self.og_image: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag == "link":
            rel = a.get("rel", "").lower()
            href = a.get("href", "")
            if "stylesheet" in rel and href:
                self.stylesheets.append(href)
            if any(x in rel for x in ("icon", "apple-touch-icon", "shortcut")) and href:
                self.icons.append(href)
        if tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            content = a.get("content", "")
            if name in ("theme-color", "msapplication-tilecolor") and content:
                self.theme_color = content.strip()
            if name in ("og:image", "twitter:image") and content:
                self.og_image = content.strip()
        if tag == "img":
            src = a.get("src") or a.get("data-src") or ""
            if src:
                self.images.append((src, a.get("alt", ""), a.get("class", "")))


def score_image(src: str, alt: str, cls: str, hint: re.Pattern) -> int:
    blob = f"{src} {alt} {cls}"
    if not hint.search(blob):
        return 0
    score = 2
    if LOGO_HINT.search(blob) and hint is LOGO_HINT:
        score += 3
    if MASCOT_HINT.search(blob) and hint is MASCOT_HINT:
        score += 3
    if src.lower().endswith(".svg"):
        score += 1
    return score


def pick_best(images: List[Tuple[str, str, str]], base: str, hint: re.Pattern) -> Optional[str]:
    ranked = sorted(
        ((score_image(s, a, c, hint), abs_url(base, s)) for s, a, c in images),
        key=lambda x: -x[0],
    )
    for score, url in ranked:
        if score > 0:
            return url
    return None


def extract_colors(css_blobs: List[str], theme_color: Optional[str]) -> Dict[str, str]:
    primary = secondary = accent = None
    if theme_color and COLOR_RE.search(theme_color):
        primary = theme_color.strip()

    for blob in css_blobs:
        for m in VAR_COLOR_RE.finditer(blob):
            name = m.group(0).split(":")[0].strip().lower()
            val = m.group(1).strip()
            col = COLOR_RE.search(val)
            if not col:
                continue
            c = col.group(0)
            if "primary" in name or "brand" in name or name.endswith("main"):
                primary = primary or c
            elif "secondary" in name:
                secondary = secondary or c
            elif "accent" in name:
                accent = accent or c

    # Fallback: first saturated-looking hexes in CSS (skip pure white/black/gray-ish)
    if not primary:
        found: List[str] = []
        for blob in css_blobs:
            found.extend(COLOR_RE.findall(blob))
        for c in found:
            cl = c.lower()
            if cl in ("#fff", "#ffffff", "#000", "#000000", "rgb(255,255,255)", "rgb(0,0,0)"):
                continue
            if re.match(r"#([0-9a-f])\1([0-9a-f])\2([0-9a-f])\3$", cl):
                continue
            primary = c
            break
        if len(found) > 1 and not secondary:
            secondary = found[1]
        if len(found) > 2 and not accent:
            accent = found[2]

    out = {}
    if primary:
        out["primary"] = primary
    if secondary:
        out["secondary"] = secondary
    if accent:
        out["accent"] = accent
    return out


def extract_fonts(css_blobs: List[str]) -> Dict[str, str]:
    fonts: List[str] = []
    for blob in css_blobs:
        for m in FONT_RE.finditer(blob):
            family = m.group(1).strip().split(",")[0].strip().strip("'\"")
            if family and family.lower() not in ("inherit", "sans-serif", "serif", "monospace"):
                fonts.append(family)
    out = {}
    if fonts:
        out["font_display"] = fonts[0]
        out["font_body"] = fonts[1] if len(fonts) > 1 else fonts[0]
    return out


def extract(site_url: str) -> Dict:
    html = fetch(site_url)
    parser = AssetCollector()
    parser.feed(html)

    css_blobs = [html]
    for href in parser.stylesheets[:8]:
        try:
            css_blobs.append(fetch(abs_url(site_url, href)))
        except Exception:
            continue

    colors = extract_colors(css_blobs, parser.theme_color)
    fonts = extract_fonts(css_blobs)

    logo = pick_best(parser.images, site_url, LOGO_HINT)
    if not logo and parser.icons:
        logo = abs_url(site_url, parser.icons[0])
    if not logo and parser.og_image:
        logo = abs_url(site_url, parser.og_image)

    mascot = pick_best(parser.images, site_url, MASCOT_HINT)

    pack = {
        "source_site": site_url,
        **colors,
        **fonts,
        "logo_url": logo or "",
        "mascot_url": mascot or "",
        "icons": [abs_url(site_url, i) for i in parser.icons[:5]],
        "method": "rules-css-html",
    }
    return pack


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract brand pack from a public site")
    ap.add_argument("site_url")
    ap.add_argument("--json", action="store_true", help="print JSON only")
    args = ap.parse_args()
    try:
        pack = extract(args.site_url)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(pack, indent=2))
    else:
        print("Brand pack")
        for k, v in pack.items():
            print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
