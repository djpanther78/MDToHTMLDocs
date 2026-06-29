#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import html
import http.server
import json
import mimetypes
import os
import re
import socketserver
import sys
import textwrap
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _need(pkg, pip_name=None):
    try:
        return __import__(pkg)
    except ImportError:
        sys.stderr.write(
            f"\nMissing dependency '{pkg}'. Install with:\n"
            f"    pip install {pip_name or pkg}\n\n"
        )
        sys.exit(1)


markdown = _need("markdown")
yaml = _need("yaml", "pyyaml")
_need("pygments")
from pygments.formatters import HtmlFormatter


THEME_PRESETS = {
    "default": {
        "accent": "#5B6CFF", "accent_dark": "#8B97FF",
        "bg": "#FFFFFF", "bg_alt": "#F7F8FA", "bg_code": "#F4F4F7",
        "text": "#1F2330", "text_muted": "#6B7280", "border": "#E5E7EB",
        "bg_dark": "#0F1117", "bg_alt_dark": "#161922", "bg_code_dark": "#1B1F2A",
        "text_dark": "#E5E7EB", "text_muted_dark": "#9AA0AA", "border_dark": "#272B36",
    },
    "slate": {
        "accent": "#0EA5E9", "accent_dark": "#38BDF8",
        "bg": "#FFFFFF", "bg_alt": "#F1F5F9", "bg_code": "#EEF2F7",
        "text": "#0F172A", "text_muted": "#64748B", "border": "#E2E8F0",
        "bg_dark": "#0B1220", "bg_alt_dark": "#111827", "bg_code_dark": "#1A2233",
        "text_dark": "#E2E8F0", "text_muted_dark": "#94A3B8", "border_dark": "#1F2937",
    },
    "warm": {
        "accent": "#E26A2C", "accent_dark": "#F08A4B",
        "bg": "#FFFBF6", "bg_alt": "#FAF3E8", "bg_code": "#F4ECDD",
        "text": "#2A1F14", "text_muted": "#7A6A55", "border": "#EADFCB",
        "bg_dark": "#1A140C", "bg_alt_dark": "#231A11", "bg_code_dark": "#2C2117",
        "text_dark": "#F0E6D6", "text_muted_dark": "#B8A88E", "border_dark": "#3A2D1F",
    },
    "mint": {
        "accent": "#10B981", "accent_dark": "#34D399",
        "bg": "#FFFFFF", "bg_alt": "#F1FBF7", "bg_code": "#E7F6EF",
        "text": "#0A1F18", "text_muted": "#5C7268", "border": "#DCEAE3",
        "bg_dark": "#0A1A14", "bg_alt_dark": "#0F2820", "bg_code_dark": "#15332A",
        "text_dark": "#DDF2EA", "text_muted_dark": "#8FB0A4", "border_dark": "#1F3D32",
    },
    "sand": {
        "accent": "#A66B3A", "accent_dark": "#D29463",
        "bg": "#FAF7F1", "bg_alt": "#F2EDE2", "bg_code": "#ECE4D3",
        "text": "#2B2419", "text_muted": "#7A6A52", "border": "#E0D6C1",
        "bg_dark": "#1F1A12", "bg_alt_dark": "#28221A", "bg_code_dark": "#322A1F",
        "text_dark": "#F0E6D2", "text_muted_dark": "#B8A88A", "border_dark": "#3D3324",
    },
}

DEFAULT_CONFIG: dict[str, Any] = {
    "site": {
        "title": "Documentation",
        "description": "",
        "logo": None,
        "favicon": None,
        "footer": "Built with mdtohtml.py",
        "lang": "en",
        "extra_head": "",
    },
    "source": "docs",
    "output": "site.html",
    "theme": {
        "preset": "default",
        "mode": "auto",
        "density": "normal",
        "font_body": "Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif",
        "font_heading": "Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif",
        "font_mono": "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
        "google_fonts": ["Inter:wght@400;500;600;700", "JetBrains+Mono:wght@400;500"],
        "radius": 10,
        "sidebar_width": 280,
        "content_max": 820,
        "pygments_style_light": "default",
        "pygments_style_dark": "monokai",
        "extra_css": "",
        "extra_js": "",
    },
    "nav": {
        "order": [],
        "hide": [],
        "rename": {},
        "show_root_readme_as_home": True,
        "collapse_depth": 1,
        "default_folder_index": ["index.md", "README.md", "readme.md"],
        "header_links": [],
        "footer_links": [],
    },
    "features": {
        "search": True,
        "toc": True,
        "dark_mode_toggle": True,
        "copy_code": True,
        "breadcrumbs": True,
        "prev_next": True,
        "page_anchors": True,
        "external_link_icons": True,
        "edit_link": None,
        "show_last_built": True,
        "reading_progress": True,
        "scroll_top_button": True,
        "estimated_read_time": True,
        "last_updated": True,
        "anchor_copy": True,
        "code_titles": True,
    },
    "markdown": {
        "extensions": [
            "extra", "codehilite", "toc", "admonition",
            "tables", "fenced_code", "footnotes",
            "attr_list", "def_list", "sane_lists", "meta",
        ],
        "extension_configs": {
            "codehilite": {"guess_lang": False, "css_class": "highlight"},
            "toc": {"permalink": False, "anchorlink": False},
        },
    },
    "embed": {
        "images": True,
        "max_image_mb": 10,
        "inline_remote": False,
    },
    "icons": {
        "source": "iconify",
        "cache_dir": ".icon_cache",
        "pages": {},
        "folders": {},
    },
    "endpoints": {
        "base_url": "https://api.example.com",
        "auth_header": "Authorization: Bearer $TOKEN",
        "code_samples": ["curl", "python", "javascript"],
        "try_it": True,
    },
}

INDEX_BASENAMES = ("index.md", "README.md", "readme.md", "Readme.md")


BUILTIN_ICONS = {
    "home":     '<svg viewBox="0 0 24 24" fill="none"><path d="M3 12l9-9 9 9M5 10v10h14V10" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "book":     '<svg viewBox="0 0 24 24" fill="none"><path d="M4 4h6a3 3 0 0 1 3 3v13a2 2 0 0 0-2-2H4zM20 4h-6a3 3 0 0 0-3 3v13a2 2 0 0 1 2-2h7z" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "rocket":   '<svg viewBox="0 0 24 24" fill="none"><path d="M14 3c4 0 7 3 7 7-1 1-3 3-7 4l-4-4c1-4 3-6 4-7zM6 14l-3 1 1 4 4 1 1-3M14 10a1 1 0 1 1 0-.01" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "settings": '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.7"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.5-2.4.9a7 7 0 0 0-2-1.2L14 3h-4l-.5 2.5a7 7 0 0 0-2 1.2L5 5.8 3 9.3l2 1.5a7 7 0 0 0 0 2.4l-2 1.5 2 3.5 2.5-.9a7 7 0 0 0 2 1.2L10 21h4l.5-2.5a7 7 0 0 0 2-1.2l2.4.9 2-3.5-2-1.5c.06-.4.1-.8.1-1.2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>',
    "network":  '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.7"/><circle cx="5" cy="5" r="2" stroke="currentColor" stroke-width="1.7"/><circle cx="19" cy="5" r="2" stroke="currentColor" stroke-width="1.7"/><circle cx="5" cy="19" r="2" stroke="currentColor" stroke-width="1.7"/><circle cx="19" cy="19" r="2" stroke="currentColor" stroke-width="1.7"/><path d="M7 6l3 4M17 6l-3 4M7 18l3-4M17 18l-3-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
    "code":     '<svg viewBox="0 0 24 24" fill="none"><path d="M8 9l-4 3 4 3M16 9l4 3-4 3M14 5l-4 14" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "globe":    '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.7"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" stroke="currentColor" stroke-width="1.5"/></svg>',
    "database": '<svg viewBox="0 0 24 24" fill="none"><ellipse cx="12" cy="5" rx="8" ry="2.5" stroke="currentColor" stroke-width="1.7"/><path d="M4 5v6c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5V5M4 11v6c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5v-6" stroke="currentColor" stroke-width="1.7"/></svg>',
    "terminal": '<svg viewBox="0 0 24 24" fill="none"><rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" stroke-width="1.7"/><path d="M7 9l3 3-3 3M13 15h4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "key":      '<svg viewBox="0 0 24 24" fill="none"><circle cx="8" cy="15" r="4" stroke="currentColor" stroke-width="1.7"/><path d="M11 12l8-8M16 7l3 3M14 9l2 2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "tag":      '<svg viewBox="0 0 24 24" fill="none"><path d="M3 11V4h7l11 11-7 7zM7 8a1 1 0 1 0 0-.01" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "file":     '<svg viewBox="0 0 24 24" fill="none"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "folder":   '<svg viewBox="0 0 24 24" fill="none"><path d="M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
    "package":  '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3l9 5v8l-9 5-9-5V8zM3 8l9 5 9-5M12 13v10" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
    "shield":   '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3l8 3v6c0 5-4 8-8 9-4-1-8-4-8-9V6z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
    "layers":   '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 17l9 5 9-5" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
    "search":   '<svg viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="7" stroke="currentColor" stroke-width="1.7"/><path d="M17 17l4 4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
    "info":     '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.7"/><path d="M12 8h.01M11 12h1v5h1" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "moon":     '<svg viewBox="0 0 24 24" fill="none"><path d="M20 14.5A8.5 8.5 0 1 1 9.5 4 7 7 0 0 0 20 14.5z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
    "sun":      '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="1.7"/><path d="M12 3v2M12 19v2M5.2 5.2l1.4 1.4M17.4 17.4l1.4 1.4M3 12h2M19 12h2M5.2 18.8l1.4-1.4M17.4 6.6l1.4-1.4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
    "github":   '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 .5C5.6.5.5 5.6.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2.1c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.8-1.6-2.5-.3-5.2-1.3-5.2-5.6 0-1.2.4-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.2 1.2.9-.3 1.9-.4 3-.4s2 .1 3 .4c2.2-1.5 3.2-1.2 3.2-1.2.6 1.6.2 2.8.1 3.1.7.8 1.2 1.9 1.2 3.1 0 4.4-2.7 5.3-5.2 5.6.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6 4.6-1.5 7.9-5.9 7.9-10.9C23.5 5.6 18.4.5 12 .5z"/></svg>',
    "bug":      '<svg viewBox="0 0 24 24" fill="none"><rect x="6" y="7" width="12" height="11" rx="5" stroke="currentColor" stroke-width="1.7"/><path d="M9 3l2 3M15 3l-2 3M3 11h3M18 11h3M3 16h3M18 16h3M3 21h3M18 21h3M12 11v8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "discord":  '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19.3 5.3a17 17 0 0 0-4.3-1.4l-.2.4a16 16 0 0 0-5.6 0l-.2-.4A17 17 0 0 0 4.7 5.3C2.3 9.1 1.6 12.8 1.9 16.4c1.9 1.4 3.7 2.2 5.4 2.8.4-.6.8-1.2 1.1-1.9-.7-.3-1.3-.6-1.9-1l.4-.4c3.6 1.7 7.6 1.7 11.2 0 .2.1.3.3.5.4-.6.4-1.2.7-1.9 1 .3.7.7 1.3 1.1 1.9 1.7-.6 3.5-1.4 5.4-2.8.3-3.9-.5-7.5-2.9-11zM8.5 14.3c-1.1 0-1.9-1-1.9-2.2s.9-2.2 1.9-2.2 1.9 1 1.9 2.2c0 1.3-.9 2.2-1.9 2.2zm7 0c-1.1 0-1.9-1-1.9-2.2s.9-2.2 1.9-2.2 1.9 1 1.9 2.2c0 1.3-.9 2.2-1.9 2.2z"/></svg>',
    "copy":     '<svg viewBox="0 0 24 24" fill="none"><rect x="9" y="9" width="11" height="11" rx="2" stroke="currentColor" stroke-width="1.7"/><path d="M5 15V5a2 2 0 0 1 2-2h10" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "check":    '<svg viewBox="0 0 24 24" fill="none"><path d="M5 13l4 4 10-10" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "x":        '<svg viewBox="0 0 24 24" fill="none"><path d="M5 5l14 14M19 5L5 19" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
    "menu":     '<svg viewBox="0 0 24 24" fill="none"><path d="M4 6h16M4 12h16M4 18h16" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/></svg>',
    "arrow-up": '<svg viewBox="0 0 24 24" fill="none"><path d="M12 19V5M5 12l7-7 7 7" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "chevron-right": '<svg viewBox="0 0 24 24" fill="none"><path d="M9 6l6 6-6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "link":     '<svg viewBox="0 0 24 24" fill="none"><path d="M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "play":     '<svg viewBox="0 0 24 24" fill="none"><path d="M6 4l14 8-14 8z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
    "send":     '<svg viewBox="0 0 24 24" fill="none"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4z" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "zap":      '<svg viewBox="0 0 24 24" fill="none"><path d="M13 2L3 14h9l-1 8 10-12h-9z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
}


def fetch_icon(name, cfg):
    if not name:
        return None
    if name in BUILTIN_ICONS:
        return BUILTIN_ICONS[name]

    icons_cfg = cfg.get("icons", {}) or {}
    if icons_cfg.get("source") != "iconify":
        return None

    cache_dir = Path(icons_cfg.get("cache_dir", ".icon_cache"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-z0-9_-]+", "_", name.lower())
    cached = cache_dir / f"{safe}.svg"
    if cached.exists():
        return cached.read_text(encoding="utf-8")

    iconify_name = name.split("iconify:", 1)[-1] if name.startswith("iconify:") else name
    url = f"https://api.iconify.design/{iconify_name}.svg?color=currentColor"
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=10) as r:
            svg = r.read().decode("utf-8")
        svg = re.sub(r'\s(width|height)="[^"]+"', "", svg, count=2)
        cached.write_text(svg, encoding="utf-8")
        return svg
    except Exception as e:
        print(f"  icon fetch failed: {name} ({e})")
        return None


def icon_for(path, cfg, is_folder=False):
    lookup = (cfg.get("icons", {}) or {}).get("folders" if is_folder else "pages", {}) or {}
    name = lookup.get(path)
    return fetch_icon(name, cfg) if name else None


def deep_merge(base, override):
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path):
    cfg = DEFAULT_CONFIG
    if path and Path(path).exists():
        with open(path, "r", encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
        cfg = deep_merge(DEFAULT_CONFIG, user)

    preset_name = cfg["theme"].get("preset", "default")
    preset = THEME_PRESETS.get(preset_name, THEME_PRESETS["default"])
    for key, value in preset.items():
        cfg["theme"].setdefault(key, value)
    return cfg


@dataclass
class Page:
    src: Path
    rel: str
    title: str
    order: int = 10_000
    hidden: bool = False
    description: str = ""
    html: str = ""
    toc: list = field(default_factory=list)
    raw: str = ""
    word_count: int = 0
    last_updated: str = ""
    searchable: bool = True


@dataclass
class NavNode:
    name: str
    path: str | None = None
    children: list = field(default_factory=list)
    is_folder: bool = False
    order: int = 10_000
    folder_dir: str = ""


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text):
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except Exception:
        data = {}
    return data, text[m.end():]


def _is_remote(url):
    return urlparse(url).scheme in ("http", "https", "data")


def _data_uri(data, ctype):
    return f"data:{ctype};base64,{base64.b64encode(data).decode('ascii')}"


def embed_image(src_url, page_dir, source_root, cfg):
    if not cfg["embed"]["images"]:
        return src_url
    if _is_remote(src_url):
        if not cfg["embed"]["inline_remote"]:
            return src_url
        try:
            import urllib.request
            with urllib.request.urlopen(src_url, timeout=10) as r:
                data = r.read()
                ctype = r.headers.get_content_type() or "application/octet-stream"
            return _data_uri(data, ctype)
        except Exception as e:
            print(f"  remote image fetch failed: {src_url} ({e})")
            return src_url

    if src_url.startswith("/"):
        candidates = [source_root / src_url.lstrip("/")]
    else:
        candidates = [page_dir / src_url, source_root / src_url]
    img_path = next((c for c in candidates if c.exists() and c.is_file()), None)
    if not img_path:
        print(f"  image not found: {src_url}")
        return src_url

    size_mb = img_path.stat().st_size / (1024 * 1024)
    if size_mb > cfg["embed"]["max_image_mb"]:
        print(f"  image {img_path.name} is {size_mb:.1f}MB, leaving as plain URL")
        return src_url

    ctype, _ = mimetypes.guess_type(img_path.name)
    return _data_uri(img_path.read_bytes(), ctype or "application/octet-stream")


IMG_TAG_RE = re.compile(r'<img\b([^>]*?)\bsrc="([^"]+)"([^>]*)>', re.IGNORECASE)


def rewrite_images(html_text, page_dir, source_root, cfg):
    def repl(m):
        pre, src, post = m.group(1), m.group(2), m.group(3)
        new_src = embed_image(src, page_dir, source_root, cfg)
        return f'<img{pre}src="{html.escape(new_src, quote=True)}"{post}>'
    return IMG_TAG_RE.sub(repl, html_text)


def slugify(text):
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    s = re.sub(r"[\s_-]+", "-", s)
    return s or "section"


HEADING_RE = re.compile(r'<h([23])>(.*?)</h\1>', re.IGNORECASE | re.DOTALL)


def inject_anchors(html_text):
    toc = []
    seen = {}

    def repl(m):
        level = int(m.group(1))
        inner = m.group(2)
        text = re.sub(r"<[^>]+>", "", inner).strip()
        base = slugify(text)
        n = seen.get(base, 0)
        seen[base] = n + 1
        slug = base if n == 0 else f"{base}-{n}"
        toc.append({"id": slug, "text": text, "level": level})
        return (
            f'<h{level} id="{slug}" class="md-h{level}">'
            f'<a class="md-anchor" href="#{slug}" data-anchor-link="{slug}" aria-label="Permalink"></a>'
            f'{inner}</h{level}>'
        )

    return HEADING_RE.sub(repl, html_text), toc


CODE_BLOCK_TITLE_RE = re.compile(
    r'<div class="highlight">(<pre[^>]*>)',
    re.IGNORECASE,
)


def apply_code_titles(md_text, html_text, cfg):
    if not cfg["features"].get("code_titles", True):
        return html_text

    titles = []
    for m in re.finditer(r'^```(\w+)?\s+title=("([^"]+)"|\'([^\']+)\'|(\S+))', md_text, re.MULTILINE):
        titles.append(m.group(3) or m.group(4) or m.group(5))
    if not titles:
        return html_text

    iter_titles = iter(titles)

    def repl(m):
        try:
            t = next(iter_titles)
        except StopIteration:
            return m.group(0)
        return (
            f'<div class="code-block">'
            f'<div class="code-block-title">{html.escape(t)}</div>'
            f'<div class="highlight">{m.group(1)}'
        )

    out = CODE_BLOCK_TITLE_RE.sub(repl, html_text, count=len(titles))
    return out.replace("</pre></div>", "</pre></div></div>", len(titles))


ENDPOINT_RE = re.compile(
    r'<div class="admonition endpoint">\s*<p class="admonition-title">([^<]+)</p>(.*?)</div>',
    re.DOTALL | re.IGNORECASE,
)
HTTP_METHOD_RE = re.compile(r'^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(.+)$', re.IGNORECASE)
REQUEST_BODY_RE = re.compile(
    r'<div class="code-block-title">Request[^<]*</div>\s*<div class="highlight">\s*<pre[^>]*>\s*<code[^>]*>(.*?)</code>',
    re.DOTALL | re.IGNORECASE,
)


def _extract_request_body(body_html):
    m = REQUEST_BODY_RE.search(body_html)
    if not m:
        return None
    raw = html.unescape(m.group(1)).strip()
    try:
        return json.dumps(json.loads(raw), indent=2)
    except Exception:
        return raw


def _gen_curl(method, url, body, auth):
    parts = [f"curl -X {method} \\", f"  '{url}'"]
    if auth:
        parts[-1] += " \\"
        parts.append(f"  -H '{auth}'")
    if body and method in ("POST", "PUT", "PATCH"):
        parts[-1] += " \\"
        parts.append("  -H 'Content-Type: application/json' \\")
        body_inline = body.replace("'", "'\\''")
        parts.append(f"  -d '{body_inline}'")
    return "\n".join(parts)


def _split_auth(auth):
    if ":" in auth:
        k, v = auth.split(":", 1)
        return k.strip(), v.strip()
    return "Authorization", auth.strip()


def _gen_python(method, url, body, auth):
    key, val = _split_auth(auth) if auth else ("", "")
    lines = ["import requests", ""]
    lines.append(f"r = requests.{method.lower()}(")
    lines.append(f'    "{url}",')
    if auth:
        lines.append(f'    headers={{"{key}": "{val}"}},')
    if body and method in ("POST", "PUT", "PATCH"):
        try:
            data = json.loads(body)
            lines.append(f"    json={data!r},")
        except Exception:
            lines.append(f"    data={body!r},")
    lines.append(")")
    lines.append("print(r.json())")
    return "\n".join(lines)


def _gen_javascript(method, url, body, auth):
    key, val = _split_auth(auth) if auth else ("", "")
    lines = [f"const r = await fetch('{url}', {{"]
    lines.append(f"  method: '{method}',")
    if auth:
        lines.append(f"  headers: {{ '{key}': '{val}'" + (", 'Content-Type': 'application/json'" if body and method in ("POST", "PUT", "PATCH") else "") + " },")
    if body and method in ("POST", "PUT", "PATCH"):
        try:
            data = json.loads(body)
            pretty = json.dumps(data, indent=2)
            indented = pretty.replace("\n", "\n  ")
            lines.append(f"  body: JSON.stringify({indented}),")
        except Exception:
            lines.append(f"  body: {body!r},")
    lines.append("});")
    lines.append("const data = await r.json();")
    return "\n".join(lines)


def _gen_node(method, url, body, auth):
    return _gen_javascript(method, url, body, auth)


def _gen_go(method, url, body, auth):
    lines = ['package main', '', 'import (', '\t"fmt"', '\t"io"', '\t"net/http"']
    if body:
        lines.append('\t"strings"')
    lines += [')', '', 'func main() {']
    if body:
        body_go = body.replace('`', '`+"`"+`')
        lines.append(f'\tbody := strings.NewReader(`{body_go}`)')
        lines.append(f'\treq, _ := http.NewRequest("{method}", "{url}", body)')
        lines.append('\treq.Header.Set("Content-Type", "application/json")')
    else:
        lines.append(f'\treq, _ := http.NewRequest("{method}", "{url}", nil)')
    if auth:
        key, val = _split_auth(auth)
        lines.append(f'\treq.Header.Set("{key}", "{val}")')
    lines += [
        '\tres, _ := http.DefaultClient.Do(req)',
        '\tdefer res.Body.Close()',
        '\tdata, _ := io.ReadAll(res.Body)',
        '\tfmt.Println(string(data))',
        '}',
    ]
    return "\n".join(lines)


def _gen_ruby(method, url, body, auth):
    key, val = _split_auth(auth) if auth else ("", "")
    lines = ["require 'net/http'", "require 'json'", "require 'uri'", ""]
    lines.append(f"uri = URI('{url}')")
    method_class = method.title()
    lines.append(f"req = Net::HTTP::{method_class}.new(uri)")
    if auth:
        lines.append(f"req['{key}'] = '{val}'")
    if body and method in ("POST", "PUT", "PATCH"):
        lines.append("req['Content-Type'] = 'application/json'")
        lines.append(f"req.body = {body!r}")
    lines.append("res = Net::HTTP.start(uri.hostname, uri.port, use_ssl: uri.scheme == 'https') { |h| h.request(req) }")
    lines.append("puts res.body")
    return "\n".join(lines)


CODE_GENERATORS = {
    "curl": _gen_curl,
    "python": _gen_python,
    "javascript": _gen_javascript,
    "node": _gen_node,
    "go": _gen_go,
    "ruby": _gen_ruby,
}
CODE_LABELS = {
    "curl": "curl", "python": "Python", "javascript": "JavaScript",
    "node": "Node.js", "go": "Go", "ruby": "Ruby",
}


def _build_code_tabs(method, full_url, body, cfg):
    ep = cfg.get("endpoints", {}) or {}
    langs = ep.get("code_samples") or []
    if not langs:
        return ""
    auth = ep.get("auth_header", "")
    samples = []
    for lang in langs:
        gen = CODE_GENERATORS.get(lang)
        if not gen:
            continue
        try:
            samples.append((lang, gen(method, full_url, body, auth)))
        except Exception as e:
            print(f"  code sample failed for {lang}: {e}")
    if not samples:
        return ""

    headers = "".join(
        f'<button class="code-tab{" active" if i == 0 else ""}" type="button" data-tab="{lang}">{CODE_LABELS.get(lang, lang)}</button>'
        for i, (lang, _) in enumerate(samples)
    )
    panes = "".join(
        f'<div class="code-tab-pane{" active" if i == 0 else ""}" data-pane="{lang}"' + ("" if i == 0 else " hidden") + ">"
        f'<div class="highlight"><pre><code class="language-{lang}">{html.escape(code)}</code></pre></div>'
        '</div>'
        for i, (lang, code) in enumerate(samples)
    )
    return (
        '<div class="code-tabs" data-code-tabs>'
        '<div class="code-tabs-bar">'
        '<span class="code-tabs-label">Example request</span>'
        f'<div class="code-tab-headers" role="tablist">{headers}</div>'
        '</div>'
        f'{panes}</div>'
    )


def _build_try_it(method, full_url, body, cfg):
    ep = cfg.get("endpoints", {}) or {}
    if not ep.get("try_it"):
        return ""
    body_attr = html.escape(body or "", quote=True)
    auth = html.escape(ep.get("auth_header", ""), quote=True)
    body_disabled = method not in ("POST", "PUT", "PATCH")
    return (
        '<div class="tryit" data-tryit>'
        f'<button class="tryit-toggle" type="button" data-method="{method}">'
        f'{BUILTIN_ICONS["play"]}<span>Try this request</span></button>'
        '<div class="tryit-panel" hidden>'
        '<div class="tryit-row">'
        '<label class="tryit-field"><span>URL</span>'
        f'<input class="tryit-url" type="text" value="{html.escape(full_url, quote=True)}"></label>'
        '</div>'
        '<div class="tryit-row">'
        '<label class="tryit-field"><span>Auth header</span>'
        f'<input class="tryit-auth" type="text" value="{auth}" placeholder="Authorization: Bearer ..."></label>'
        '</div>'
        + ('' if body_disabled else
           '<div class="tryit-row">'
           '<label class="tryit-field"><span>Body (JSON)</span>'
           f'<textarea class="tryit-body" rows="6" spellcheck="false">{body_attr}</textarea></label>'
           '</div>'
        )
        + '<div class="tryit-row tryit-actions">'
          f'<button class="tryit-send" type="button">{BUILTIN_ICONS["send"]}<span>Send</span></button>'
          '<span class="tryit-hint">Cross-origin requests may be blocked by the target API.</span>'
          '</div>'
          '<div class="tryit-response" hidden>'
          '<div class="tryit-status"></div>'
          '<pre class="tryit-output"></pre>'
          '</div>'
          '</div></div>'
    )


def transform_endpoints(html_text, cfg):
    base = (cfg.get("endpoints", {}) or {}).get("base_url", "")

    def repl(m):
        title_raw = m.group(1).strip()
        body = m.group(2)
        match = HTTP_METHOD_RE.match(title_raw)
        if not match:
            return m.group(0)
        method = match.group(1).upper()
        path = match.group(2).strip()
        full_url = (base.rstrip("/") + path) if base else path
        request_body = _extract_request_body(body)
        samples = _build_code_tabs(method, full_url, request_body, cfg)
        try_it = _build_try_it(method, full_url, request_body, cfg)
        return (
            f'<div class="endpoint endpoint-{method.lower()}">'
            f'<div class="endpoint-header">'
            f'<span class="endpoint-method">{method}</span>'
            f'<code class="endpoint-path">{html.escape(path)}</code>'
            f'</div>'
            f'<div class="endpoint-body">{body}{samples}{try_it}</div>'
            f'</div>'
        )
    return ENDPOINT_RE.sub(repl, html_text)


def estimate_read_minutes(words):
    return max(1, round(words / 220))


def render_page(page, source_root, cfg):
    raw = page.src.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(raw)

    if "title" in fm:
        page.title = str(fm["title"])
    if "order" in fm:
        try:
            page.order = int(fm["order"])
        except Exception:
            pass
    if fm.get("hidden") in (True, "true", "True", 1):
        page.hidden = True
    if "description" in fm:
        page.description = str(fm["description"])
    if fm.get("search") in (False, "false", "False", 0):
        page.searchable = False
    if "last_updated" in fm:
        page.last_updated = str(fm["last_updated"])

    page.raw = body
    page.word_count = len(re.findall(r"\b\w+\b", body))

    if not page.last_updated and cfg["features"].get("last_updated", True):
        ts = page.src.stat().st_mtime
        page.last_updated = time.strftime("%b %d, %Y", time.localtime(ts))

    md = markdown.Markdown(
        extensions=cfg["markdown"]["extensions"],
        extension_configs=cfg["markdown"].get("extension_configs", {}),
        output_format="html5",
    )
    rendered = md.convert(body)
    rendered = apply_code_titles(body, rendered, cfg)
    rendered = transform_endpoints(rendered, cfg)
    rendered = rewrite_images(rendered, page.src.parent, source_root, cfg)
    rendered, toc = inject_anchors(rendered)
    rendered = re.sub(
        r'<a\s+href="(https?://github\.com/[^"]+)"',
        r'<a class="md-ext-github" target="_blank" rel="noopener noreferrer" href="\1"',
        rendered,
    )
    rendered = re.sub(
        r'<a\s+href="(https?://[^"]+)"',
        r'<a class="md-ext" target="_blank" rel="noopener noreferrer" href="\1"',
        rendered,
    )
    rendered = re.sub(r'<table>', r'<div class="md-table-wrap"><table>', rendered)
    rendered = rendered.replace('</table>', '</table></div>')

    page.html = rendered
    page.toc = toc


def title_from_filename(stem):
    s = stem.replace("_", " ").replace("-", " ").strip()
    return s[:1].upper() + s[1:] if s else stem


def title_from_first_heading(md_text):
    m = re.search(r'^\s*#\s+(.+?)\s*$', md_text, re.MULTILINE)
    return m.group(1).strip() if m else None


def scan_pages(source, cfg):
    pages = []
    hide_set = {p.strip("/").rstrip(".md") for p in cfg["nav"].get("hide", [])}
    rename = cfg["nav"].get("rename", {}) or {}
    order_list = cfg["nav"].get("order", []) or []
    order_index = {p.strip("/").rstrip(".md"): i for i, p in enumerate(order_list)}

    for md_path in sorted(source.rglob("*.md")):
        rel = md_path.relative_to(source).as_posix()[:-3]
        if rel in hide_set:
            continue
        raw_head = md_path.read_text(encoding="utf-8", errors="replace")[:4096]
        fm, body_preview = parse_frontmatter(raw_head)
        title = (
            rename.get(rel)
            or fm.get("title")
            or title_from_first_heading(body_preview)
            or title_from_filename(md_path.stem)
        )
        order = fm.get("order", order_index.get(rel, 10_000))
        try:
            order = int(order)
        except (TypeError, ValueError):
            order = 10_000
        pages.append(Page(src=md_path, rel=rel, title=str(title), order=order))
    return pages


def build_nav(pages, cfg):
    root_children = []
    folder_map = {}

    def get_folder(parts):
        if not parts:
            return root_children
        cur = root_children
        path = ""
        for part in parts:
            path = f"{path}/{part}" if path else part
            node = folder_map.get(path)
            if node is None:
                node = NavNode(name=title_from_filename(part), is_folder=True, folder_dir=path)
                folder_map[path] = node
                cur.append(node)
            cur = node.children
        return cur

    index_basenames = cfg["nav"].get("default_folder_index", list(INDEX_BASENAMES))

    for page in pages:
        if page.hidden:
            continue
        parts = page.rel.split("/")
        basename = parts[-1] + ".md"
        parent = parts[:-1]
        siblings = get_folder(parent)
        if basename in index_basenames and parent:
            folder = folder_map.get("/".join(parent))
            if folder:
                folder.path = page.rel
                folder.order = min(folder.order, page.order)
                continue
        siblings.append(NavNode(name=page.title, path=page.rel, order=page.order))

    def sort_tree(nodes):
        nodes.sort(key=lambda n: (n.order, n.name.lower()))
        for n in nodes:
            if n.children:
                sort_tree(n.children)

    sort_tree(root_children)
    return root_children


def find_home(pages, cfg):
    if not cfg["nav"].get("show_root_readme_as_home", True):
        return pages[0].rel if pages else None
    for base in cfg["nav"].get("default_folder_index", list(INDEX_BASENAMES)):
        stem = base[:-3]
        for p in pages:
            if p.rel == stem:
                return p.rel
    return pages[0].rel if pages else None


def render_nav(nodes, cfg, depth=0):
    if not nodes:
        return ""
    collapse_depth = int(cfg["nav"].get("collapse_depth", 1))
    folder_lookup = (cfg.get("icons", {}) or {}).get("folders", {}) or {}
    parts = ['<ul class="nav-list">']
    for n in nodes:
        if n.is_folder:
            details_open = "open" if depth < collapse_depth else ""
            folder_icon_name = folder_lookup.get(n.folder_dir)
            folder_icon = fetch_icon(folder_icon_name, cfg) if folder_icon_name else None
            icon_html = f'<span class="nav-icon">{folder_icon}</span>' if folder_icon else ""
            label = (
                f'<a class="nav-folder-link" data-page="{html.escape(n.path)}">{icon_html}{html.escape(n.name)}</a>'
                if n.path else
                f'<span class="nav-folder-label">{icon_html}{html.escape(n.name)}</span>'
            )
            parts.append(
                f'<li class="nav-folder"><details {details_open}>'
                f'<summary class="nav-folder-summary">'
                f'<svg class="nav-chev" viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">'
                f'<path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
                f'{label}</summary>'
                f'{render_nav(n.children, cfg, depth + 1)}'
                f'</details></li>'
            )
        else:
            page_icon = icon_for(n.path, cfg) if n.path else None
            icon_html = f'<span class="nav-icon">{page_icon}</span>' if page_icon else ""
            parts.append(
                f'<li class="nav-leaf"><a class="nav-link" data-page="{html.escape(n.path or "")}">'
                f'{icon_html}{html.escape(n.name)}</a></li>'
            )
    parts.append('</ul>')
    return "".join(parts)


def flatten_order(nodes, pages_by_id):
    out = []
    seen = set()

    def walk(ns):
        for n in ns:
            if n.path and n.path in pages_by_id and n.path not in seen:
                out.append(pages_by_id[n.path])
                seen.add(n.path)
            if n.children:
                walk(n.children)

    walk(nodes)
    for pid, p in pages_by_id.items():
        if pid not in seen and not p.hidden:
            out.append(p)
    return out


def make_breadcrumbs(rel, pages_by_id):
    parts = rel.split("/")
    crumbs = []
    for i in range(len(parts)):
        sub = "/".join(parts[:i + 1])
        page = pages_by_id.get(sub)
        crumbs.append({
            "name": page.title if page else title_from_filename(parts[i]),
            "path": page.rel if page else None,
        })
    return crumbs


def file_to_data_uri(path):
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    ctype, _ = mimetypes.guess_type(p.name)
    return f"data:{ctype or 'application/octet-stream'};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


HTML_TEMPLATE = r"""<!doctype html>
<html lang="{lang}" data-theme="{initial_theme}" data-density="{density}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{site_title}</title>
<meta name="description" content="{site_description}">
{favicon_tag}
{google_fonts_link}
{extra_head}
<style>
{base_css}
{pygments_css}
{theme_css}
{extra_css}
</style>
</head>
<body>
<div class="app">
  <header class="topbar">
    <button class="hamburger" id="hamburger" aria-label="Toggle navigation">
      <svg viewBox="0 0 20 20" width="18" height="18"><path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
    </button>
    <a class="brand" href="#/">
      {logo_html}
      <span class="brand-title">{site_title}</span>
    </a>
    <nav class="header-links">{header_links_html}</nav>
    <div class="topbar-spacer"></div>
    {search_html}
    {theme_toggle_html}
  </header>

  <aside class="sidebar" id="sidebar">
    <nav class="nav-root">{nav_html}</nav>
  </aside>
  <div class="sidebar-backdrop" id="sidebarBackdrop" aria-hidden="true"></div>

  <main class="content" id="content">
    <article class="page" id="page"></article>
    <footer class="page-footer">
      {prev_next_html}
      <div class="site-footer">
        <div class="site-footer-text">{footer_html}</div>
        <nav class="footer-links">{footer_links_html}</nav>
      </div>
    </footer>
  </main>

  <aside class="toc-rail" id="tocRail" aria-label="On this page"></aside>

  <button class="scroll-top" id="scrollTop" aria-label="Scroll to top" hidden>
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M8 12V3M3 7l5-4 5 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>
  </button>
</div>
<div class="reading-progress" id="readingProgress"></div>

<div class="search-overlay" id="searchOverlay" hidden>
  <div class="search-modal">
    <div class="search-header">
      <svg class="search-input-icon" viewBox="0 0 20 20" width="16" height="16" aria-hidden="true">
        <circle cx="9" cy="9" r="6" fill="none" stroke="currentColor" stroke-width="1.6"/>
        <path d="M14 14l4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
      </svg>
      <input type="text" id="searchInput" class="search-input" placeholder="Search documentation…" autocomplete="off" spellcheck="false">
      <button class="search-close" id="searchClose" type="button" aria-label="Close search">
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
      </button>
    </div>
    <div class="search-results" id="searchResults"></div>
    <div class="search-hint"><kbd>↑↓</kbd> navigate &nbsp; <kbd>↵</kbd> open &nbsp; <kbd>esc</kbd> close</div>
  </div>
</div>

<div class="toast" id="toast" hidden></div>

<script id="site-data" type="application/json">{site_data_json}</script>
<script>
{runtime_js}
</script>
{extra_js}
</body>
</html>
"""


BASE_CSS = r"""
*,*::before,*::after { box-sizing: border-box; }
[hidden] { display: none !important; }
html, body { margin:0; padding:0; height:100%; }
html { color-scheme: light dark; }
body {
  font-family: var(--font-body);
  color: var(--color-text);
  background:
    radial-gradient(ellipse 80% 60% at 0% 0%, color-mix(in oklab, var(--color-accent) 8%, transparent) 0%, transparent 50%),
    radial-gradient(ellipse 60% 50% at 100% 100%, color-mix(in oklab, var(--color-accent) 6%, transparent) 0%, transparent 50%),
    var(--color-bg);
  font-size: 16px;
  line-height: 1.65;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  overscroll-behavior-y: none;
}
a { color: var(--color-accent); text-decoration: none; }
a:hover { text-decoration: underline; }
kbd {
  font-family: var(--font-mono); font-size: 0.78em;
  padding: 1px 6px;
  border: 1px solid var(--color-border); border-bottom-width: 2px;
  border-radius: 4px;
  background: var(--color-bg-alt); color: var(--color-text-muted);
}

[data-density="compact"] { --row-gap: 4px; --para-gap: 0.7em; }
[data-density="normal"]  { --row-gap: 6px; --para-gap: 0.9em; }
[data-density="cozy"]    { --row-gap: 8px; --para-gap: 1.05em; }

.app {
  display: grid;
  grid-template-columns: var(--sidebar-w) minmax(0,1fr) var(--toc-w);
  grid-template-rows: 56px 1fr;
  grid-template-areas:
    "topbar  topbar   topbar"
    "sidebar content  tocrail";
  height: 100vh;
}

.topbar {
  grid-area: topbar;
  display: flex; align-items: center; gap: 12px;
  padding: 0 18px;
  background: linear-gradient(180deg, color-mix(in oklab, var(--color-accent) 5%, var(--color-bg)) 0%, var(--color-bg) 60%);
  border-bottom: 1px solid var(--color-border);
  position: sticky; top: 0; z-index: 30;
}
.brand { display: flex; align-items: center; gap: 10px; color: inherit; }
.brand:hover { text-decoration: none; }
.brand-logo { width: 24px; height: 24px; display: block; }
.brand-title {
  font-weight: 700; letter-spacing: -0.02em; font-size: 15px;
  background: linear-gradient(135deg, var(--color-accent), var(--color-text) 60%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.topbar-spacer { flex: 1; }
.hamburger {
  display: none; border: 0; background: transparent; color: var(--color-text);
  padding: 6px; border-radius: 6px; cursor: pointer;
}
.hamburger:hover { background: var(--color-bg-alt); }

.header-links { display: flex; gap: 4px; margin-left: 8px; }
.header-links a {
  padding: 6px 10px; border-radius: 6px;
  font-size: 13.5px; color: var(--color-text-muted);
}
.header-links a:hover { color: var(--color-text); background: var(--color-bg-alt); text-decoration: none; }

.topbar-search {
  display: flex; align-items: center; gap: 8px;
  width: 280px; max-width: 36vw;
  padding: 6px 10px;
  border: 1px solid var(--color-border); border-radius: 8px;
  background: var(--color-bg-alt); color: var(--color-text-muted);
  cursor: text; font-size: 13px;
  transition: background 0.15s, border-color 0.15s, box-shadow 0.15s;
  font-family: var(--font-body);
}
.topbar-search:hover { border-color: color-mix(in oklab, var(--color-accent) 50%, var(--color-border)); }
.topbar-search:focus-within { border-color: var(--color-accent); box-shadow: 0 0 0 3px color-mix(in oklab, var(--color-accent) 15%, transparent); }
.topbar-search kbd { margin-left: auto; }

.theme-toggle {
  width: 34px; height: 34px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--color-border); background: var(--color-bg);
  border-radius: 8px; color: var(--color-text); cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.theme-toggle:hover { background: var(--color-bg-alt); border-color: color-mix(in oklab, var(--color-accent) 40%, var(--color-border)); }
.theme-toggle .icon-moon, .theme-toggle .icon-sun {
  display: inline-flex; width: 16px; height: 16px;
}
.theme-toggle svg { width: 100%; height: 100%; }
.theme-toggle .icon-sun { display: none; }
[data-theme="dark"] .theme-toggle .icon-sun { display: inline-flex; }
[data-theme="dark"] .theme-toggle .icon-moon { display: none; }

.brand-logo-default {
  display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 24px;
  color: var(--color-accent);
}
.brand-logo-default svg { width: 100%; height: 100%; }

.link-icon {
  display: inline-flex; align-items: center;
  width: 14px; height: 14px;
  margin-right: 6px;
  vertical-align: -2px;
}
.link-icon svg { width: 100%; height: 100%; }

.sidebar {
  grid-area: sidebar;
  background: linear-gradient(180deg, color-mix(in oklab, var(--color-accent) 5%, var(--color-bg)) 0%, var(--color-bg-alt) 30%);
  border-right: 1px solid var(--color-border);
  overflow-y: auto;
  padding: 18px 12px 40px 18px;
  contain: layout style;
}
.nav-list { list-style: none; margin: 0; padding: 0; }
.nav-list .nav-list { margin-left: 14px; border-left: 1px solid color-mix(in oklab, var(--color-accent) 20%, var(--color-border)); padding-left: 8px; }
.nav-folder summary {
  list-style: none; cursor: pointer;
  display: flex; align-items: center; gap: 4px;
  padding: 5px 8px; border-radius: 6px;
  color: var(--color-text); font-weight: 550; font-size: 13px;
  user-select: none;
  transition: background 0.15s;
}
.nav-folder summary::-webkit-details-marker { display: none; }
.nav-folder summary:hover { background: color-mix(in oklab, var(--color-accent) 6%, transparent); }
.nav-folder[open] > summary > .nav-chev { transform: rotate(90deg); }
.nav-chev { transition: transform 0.15s; flex-shrink: 0; color: var(--color-text-muted); }
.nav-folder-label, .nav-folder-link { padding-left: 4px; }
.nav-link, .nav-folder-link {
  display: block;
  padding: 4px 8px 4px 22px;
  border-radius: 6px;
  color: var(--color-text-muted);
  font-size: 13.5px; line-height: 1.5;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.nav-folder-link { padding-left: 4px; color: var(--color-text); }
.nav-link:hover, .nav-folder-link:hover { background: color-mix(in oklab, var(--color-accent) 6%, transparent); color: var(--color-text); text-decoration: none; }
.nav-link.active, .nav-folder-link.active {
  background: color-mix(in oklab, var(--color-accent) 10%, transparent);
  color: var(--color-accent); font-weight: 600;
  box-shadow: inset 2px 0 0 var(--color-accent);
}

.nav-icon {
  display: inline-flex; align-items: center; justify-content: center;
  width: 16px; height: 16px; margin-right: 8px;
  flex-shrink: 0;
  color: var(--color-text-muted);
  vertical-align: -3px;
}
.nav-icon svg { width: 100%; height: 100%; display: block; }
.nav-link, .nav-folder-link { display: inline-flex; align-items: center; width: 100%; }
.nav-link .nav-icon, .nav-folder-link .nav-icon { transition: color 0.15s; }
.nav-link:hover .nav-icon, .nav-folder-link:hover .nav-icon { color: var(--color-text); }
.nav-link.active .nav-icon, .nav-folder-link.active .nav-icon { color: var(--color-accent); }

.content {
  grid-area: content;
  overflow-y: auto;
  padding: 32px 56px 80px;
  scroll-padding-top: 72px;
  position: relative;
  background:
    radial-gradient(ellipse 80% 50% at 50% 0%, color-mix(in oklab, var(--color-accent) 6%, transparent), transparent 60%),
    linear-gradient(180deg, var(--color-bg) 0%, color-mix(in oklab, var(--color-accent) 2%, var(--color-bg)) 50%, var(--color-bg) 100%);
}
.reading-progress {
  position: fixed;
  top: 56px; left: 0; right: 0;
  height: 3px;
  background: transparent;
  z-index: 31;
  pointer-events: none;
}
.reading-progress::after {
  content: '';
  position: absolute; inset: 0;
  background: var(--color-accent);
  transform: scaleX(var(--progress, 0));
  transform-origin: left center;
  transition: transform 0.1s linear;
}
.page { max-width: var(--content-max); margin: 0 auto; }

.breadcrumbs {
  font-size: 13px; color: var(--color-text-muted);
  margin-bottom: 14px;
  display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
}
.breadcrumbs a { color: var(--color-text-muted); }
.breadcrumbs a:hover { color: var(--color-accent); }
.breadcrumbs .sep { opacity: 0.5; }
.breadcrumbs .last { color: var(--color-text); }

.page-info {
  display: flex; gap: 16px; align-items: center; flex-wrap: wrap;
  font-size: 13px; color: var(--color-text-muted);
  margin: 6px 0 18px;
}
.page-info .dot { width: 3px; height: 3px; border-radius: 50%; background: currentColor; opacity: 0.5; }
.page-meta {
  display: flex; gap: 16px; align-items: center; flex-wrap: wrap;
  margin-top: 28px; font-size: 13px; color: var(--color-text-muted);
  padding-top: 14px; border-top: 1px solid var(--color-border);
}
.page-meta a { color: var(--color-text-muted); }

.page h1, .page h2, .page h3, .page h4, .page h5, .page h6 {
  font-family: var(--font-heading);
  letter-spacing: -0.01em;
  line-height: 1.25;
  margin: 1.8em 0 0.6em;
}
.page > h1:first-child { margin-top: 0.4em; }
.page h1 { font-size: 2.1rem; font-weight: 700; padding-bottom: 0.3em; background: linear-gradient(90deg, color-mix(in oklab, var(--color-accent) 30%, transparent), transparent); background-size: 100% 2px; background-repeat: no-repeat; background-position: bottom; }
.page h2 { font-size: 1.45rem; font-weight: 650; padding-bottom: 0.3em; border-bottom: 1px solid var(--color-border); }
.page h3 { font-size: 1.15rem; font-weight: 650; }
.page h4 { font-size: 1rem; font-weight: 650; }
.page p { margin: var(--para-gap, 0.9em) 0; }
.page ul, .page ol { padding-left: 1.6em; margin: var(--para-gap, 0.9em) 0; }
.page li { margin: var(--row-gap, 6px) 0; }
.page li > p { margin: 0.3em 0; }
.page blockquote {
  border-left: 3px solid var(--color-accent);
  margin: 1.2em 0; padding: 0.4em 1em;
  background: color-mix(in oklab, var(--color-accent) 6%, transparent);
  color: var(--color-text);
  border-radius: 0 var(--radius) var(--radius) 0;
}
.page blockquote > p:first-child { margin-top: 0; }
.page blockquote > p:last-child { margin-bottom: 0; }
.page hr { border: 0; height: 1px; background: linear-gradient(90deg, transparent, var(--color-border) 20%, var(--color-border) 80%, transparent); margin: 2em 0; }

.page img { max-width: 100%; height: auto; border-radius: var(--radius); display: block; margin: 1.2em auto; }
.page figure { margin: 1.2em 0; }
.page figcaption { font-size: 0.9em; color: var(--color-text-muted); text-align: center; margin-top: 4px; }

.md-anchor {
  margin-left: -1.1em; padding-right: 0.3em;
  display: inline-block; width: 0.9em;
  opacity: 0; transition: opacity 0.1s;
  position: relative;
  cursor: pointer;
}
.md-anchor::before { content: "#"; color: var(--color-text-muted); font-weight: 400; }
.page h2:hover .md-anchor, .page h3:hover .md-anchor, .page h4:hover .md-anchor { opacity: 1; }

.md-ext::after {
  content: "";
  display: inline-block;
  width: 0.7em; height: 0.7em;
  margin-left: 3px;
  background-color: currentColor;
  -webkit-mask: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'><path d='M5 1H1v10h10V7M7 1h4v4M5 7l6-6' fill='none' stroke='black' stroke-width='1.4' stroke-linecap='round' stroke-linejoin='round'/></svg>") no-repeat center/contain;
          mask: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'><path d='M5 1H1v10h10V7M7 1h4v4M5 7l6-6' fill='none' stroke='black' stroke-width='1.4' stroke-linecap='round' stroke-linejoin='round'/></svg>") no-repeat center/contain;
  opacity: 0.7;
}
.md-ext-github::after {
  content: "";
  display: inline-block;
  width: 0.8em; height: 0.8em;
  margin-left: 3px;
  background-color: currentColor;
  -webkit-mask: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><path d='M12 .5C5.6.5.5 5.6.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2.1c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.8-1.6-2.5-.3-5.2-1.3-5.2-5.6 0-1.2.4-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.2 1.2.9-.3 1.9-.4 3-.4s2 .1 3 .4c2.2-1.5 3.2-1.2 3.2-1.2.6 1.6.2 2.8.1 3.1.7.8 1.2 1.9 1.2 3.1 0 4.4-2.7 5.3-5.2 5.6.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6 4.6-1.5 7.9-5.9 7.9-10.9C23.5 5.6 18.4.5 12 .5z'/></svg>") no-repeat center/contain;
          mask: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><path d='M12 .5C5.6.5.5 5.6.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.6v-2.1c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.8-1.6-2.5-.3-5.2-1.3-5.2-5.6 0-1.2.4-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.2 1.2.9-.3 1.9-.4 3-.4s2 .1 3 .4c2.2-1.5 3.2-1.2 3.2-1.2.6 1.6.2 2.8.1 3.1.7.8 1.2 1.9 1.2 3.1 0 4.4-2.7 5.3-5.2 5.6.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6 4.6-1.5 7.9-5.9 7.9-10.9C23.5 5.6 18.4.5 12 .5z'/></svg>") no-repeat center/contain;
  opacity: 0.7;
}

.page :not(pre) > code {
  font-family: var(--font-mono);
  font-size: 0.86em;
  padding: 2px 6px;
  background: var(--color-bg-code);
  border: 1px solid var(--color-border);
  border-radius: 5px;
  color: var(--color-text);
}
.page pre {
  font-family: var(--font-mono); font-size: 0.86em; line-height: 1.55;
  background: linear-gradient(160deg, var(--color-bg-code) 0%, color-mix(in oklab, var(--color-accent) 4%, var(--color-bg-code)) 100%);
  color: var(--color-text);
  padding: 14px 16px;
  border-radius: var(--radius);
  border: 1px solid var(--color-border);
  border-left: 3px solid color-mix(in oklab, var(--color-accent) 40%, var(--color-border));
  overflow-x: auto;
  position: relative;
  margin: 1.2em 0;
}
.page pre code { background: transparent; border: 0; padding: 0; font-size: 1em; }
.page .highlight { position: relative; }

.code-block { margin: 1.2em 0; }
.code-block .code-block-title {
  font-family: var(--font-mono); font-size: 0.78em;
  padding: 8px 14px;
  background: var(--color-bg-alt);
  border: 1px solid var(--color-border);
  border-bottom: 0;
  border-radius: var(--radius) var(--radius) 0 0;
  color: var(--color-text-muted);
}
.code-block .highlight pre { margin: 0; border-radius: 0 0 var(--radius) var(--radius); }

.copy-btn {
  position: absolute; top: 8px; right: 8px;
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  color: var(--color-text-muted);
  font-size: 11px; padding: 3px 8px;
  border-radius: 5px; cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s, background 0.15s;
  font-family: var(--font-body);
}
.page pre:hover .copy-btn { opacity: 1; }
.copy-btn:hover { color: var(--color-text); background: var(--color-bg-alt); }
.copy-btn.copied { color: #10b981; border-color: #10b981; }

.md-table-wrap { overflow-x: auto; margin: 1.2em 0; border: 1px solid var(--color-border); border-radius: var(--radius); }
.page table { border-collapse: collapse; width: 100%; font-size: 0.92em; }
.page th, .page td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--color-border); }
.page th { background: var(--color-bg-alt); font-weight: 650; font-size: 0.85em; text-transform: uppercase; letter-spacing: 0.04em; color: var(--color-text-muted); }
.page tr:last-child td { border-bottom: 0; }
.page tr:hover td { background: color-mix(in oklab, var(--color-accent) 3%, transparent); }

.admonition {
  margin: 1.4em 0; padding: 12px 16px;
  border-left: 3px solid var(--color-accent);
  background: color-mix(in oklab, var(--color-accent) 5%, transparent);
  border-radius: 0 var(--radius) var(--radius) 0;
}
.admonition-title { font-weight: 650; margin-bottom: 4px; text-transform: uppercase; font-size: 0.78em; letter-spacing: 0.06em; color: var(--color-accent); }
.admonition.warning { border-left-color: #f59e0b; background: rgba(245,158,11,0.08); }
.admonition.warning .admonition-title { color: #f59e0b; }
.admonition.danger, .admonition.error { border-left-color: #ef4444; background: rgba(239,68,68,0.08); }
.admonition.danger .admonition-title, .admonition.error .admonition-title { color: #ef4444; }
.admonition.tip, .admonition.success { border-left-color: #10b981; background: rgba(16,185,129,0.08); }
.admonition.tip .admonition-title, .admonition.success .admonition-title { color: #10b981; }
.admonition.note, .admonition.info { border-left-color: #3b82f6; background: rgba(59,130,246,0.08); }
.admonition.note .admonition-title, .admonition.info .admonition-title { color: #3b82f6; }

.admonition-title::before {
  content: '';
  display: inline-block;
  width: 13px; height: 13px;
  margin-right: 6px;
  vertical-align: -2px;
  background-color: currentColor;
  -webkit-mask: var(--adm-icon, none) no-repeat center/contain;
          mask: var(--adm-icon, none) no-repeat center/contain;
}
.admonition.tip .admonition-title, .admonition.success .admonition-title {
  --adm-icon: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><path d='M4 9l3 3 5-6' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/></svg>");
}
.admonition.warning .admonition-title {
  --adm-icon: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><path d='M8 2l7 12H1z M8 6v4 M8 12h.01' fill='none' stroke='black' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/></svg>");
}
.admonition.danger .admonition-title, .admonition.error .admonition-title {
  --adm-icon: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><circle cx='8' cy='8' r='6' fill='none' stroke='black' stroke-width='1.6'/><path d='M5 5l6 6 M11 5l-6 6' stroke='black' stroke-width='1.6' stroke-linecap='round'/></svg>");
}
.admonition.note .admonition-title, .admonition.info .admonition-title {
  --adm-icon: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><circle cx='8' cy='8' r='6' fill='none' stroke='black' stroke-width='1.6'/><path d='M8 7v5 M8 4v.01' stroke='black' stroke-width='1.6' stroke-linecap='round'/></svg>");
}

.endpoint {
  margin: 1.6em 0;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--color-bg);
}
.endpoint-header {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 14px;
  background: var(--color-bg-alt);
  border-bottom: 1px solid var(--color-border);
}
.endpoint-method {
  display: inline-block;
  padding: 3px 9px;
  font-family: var(--font-mono);
  font-size: 0.74em; font-weight: 700;
  letter-spacing: 0.04em;
  border-radius: 5px;
  color: #fff;
  flex-shrink: 0;
}
.endpoint-get    .endpoint-method { background: #10b981; }
.endpoint-post   .endpoint-method { background: #3b82f6; }
.endpoint-put    .endpoint-method { background: #f59e0b; }
.endpoint-patch  .endpoint-method { background: #8b5cf6; }
.endpoint-delete .endpoint-method { background: #ef4444; }
.endpoint-head .endpoint-method, .endpoint-options .endpoint-method { background: var(--color-text-muted); }
.endpoint-path {
  font-family: var(--font-mono); font-size: 0.95em;
  background: transparent !important; border: 0 !important; padding: 0 !important;
  color: var(--color-text);
  overflow-x: auto; white-space: nowrap;
}
.endpoint-body { padding: 14px 16px; }
.endpoint-body > :first-child { margin-top: 0; }
.endpoint-body > :last-child { margin-bottom: 0; }
.endpoint-body pre { margin: 1em 0; }

.toc-rail {
  grid-area: tocrail;
  overflow-y: auto;
  padding: 32px 20px 40px;
  font-size: 13px;
  border-left: 1px solid var(--color-border);
}
.toc-title { font-weight: 650; font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--color-text-muted); margin-bottom: 10px; }
.toc-rail ul { list-style: none; padding: 0; margin: 0; }
.toc-rail li { margin: 2px 0; }
.toc-rail a { display: block; padding: 3px 8px; border-left: 2px solid transparent; color: var(--color-text-muted); border-radius: 0 4px 4px 0; }
.toc-rail a.lvl-3 { padding-left: 18px; font-size: 12.5px; }
.toc-rail a:hover { color: var(--color-text); text-decoration: none; }
.toc-rail a.active { color: var(--color-accent); border-left-color: var(--color-accent); background: color-mix(in oklab, var(--color-accent) 6%, transparent); }

.prev-next {
  display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
  margin: 56px 0 24px;
}
.pn-card {
  display: flex; flex-direction: column;
  padding: 16px 20px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  text-decoration: none; color: inherit;
  background: color-mix(in oklab, var(--color-bg) 70%, var(--color-bg-alt));
  transition: border-color 0.2s, transform 0.2s, box-shadow 0.2s;
}
.pn-card:hover {
  border-color: var(--color-accent);
  text-decoration: none;
  transform: translateY(-2px);
  box-shadow: 0 4px 20px color-mix(in oklab, var(--color-accent) 8%, transparent);
}
.pn-card.next { text-align: right; }
.pn-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--color-text-muted); display: inline-flex; align-items: center; gap: 4px; }
.pn-arrow { flex-shrink: 0; }
.pn-title { font-weight: 600; margin-top: 4px; color: var(--color-text); }
.pn-empty { visibility: hidden; }

.site-footer {
  margin-top: 32px; padding-top: 18px;
  border-top: 1px solid transparent;
  border-image: linear-gradient(90deg, transparent 5%, var(--color-border) 30%, var(--color-border) 70%, transparent 95%) 1;
  font-size: 13px; color: var(--color-text-muted);
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;
}
.footer-links { display: flex; gap: 14px; }
.footer-links a { color: var(--color-text-muted); }
.footer-links a:hover { color: var(--color-accent); }

.scroll-top {
  position: fixed; bottom: 24px; right: 24px; z-index: 20;
  width: 38px; height: 38px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  border-radius: 50%;
  color: var(--color-text);
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(0,0,0,0.08);
  opacity: 0; transform: translateY(8px);
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.scroll-top.visible { opacity: 1; transform: translateY(0); }
.scroll-top:hover { background: var(--color-bg-alt); }

.search-overlay {
  position: fixed; inset: 0; z-index: 50;
  background: color-mix(in oklab, black 30%, transparent);
  display: flex; align-items: flex-start; justify-content: center;
  padding-top: 12vh;
}
.search-modal {
  width: min(640px, 92vw);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: 0 24px 64px rgba(0,0,0,0.25);
  overflow: hidden;
  display: flex; flex-direction: column;
}
.search-header {
  display: flex; align-items: center; gap: 10px;
  padding: 0 14px 0 18px;
  border-bottom: 1px solid var(--color-border);
}
.search-input-icon { color: var(--color-text-muted); flex-shrink: 0; }
.search-input {
  flex: 1;
  border: 0; padding: 16px 0;
  font-size: 16px;
  background: transparent; color: var(--color-text);
  font-family: var(--font-body); outline: none;
}
.search-close {
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  width: 28px; height: 28px;
  border: 0; background: var(--color-bg-alt);
  border-radius: 6px;
  color: var(--color-text-muted); cursor: pointer;
}
.search-close:hover { color: var(--color-text); background: var(--color-border); }
.search-results { max-height: 56vh; overflow-y: auto; padding: 8px; }
.search-result {
  display: block; padding: 10px 12px; border-radius: 8px; cursor: pointer;
  color: var(--color-text); text-decoration: none;
}
.search-result:hover, .search-result.active { background: color-mix(in oklab, var(--color-accent) 10%, transparent); text-decoration: none; }
.search-result-title { font-weight: 600; }
.search-result-path { font-size: 12px; color: var(--color-text-muted); margin-top: 2px; }
.search-result-snippet { font-size: 13px; color: var(--color-text-muted); margin-top: 4px; line-height: 1.4; }
.search-result-snippet mark { background: color-mix(in oklab, var(--color-accent) 30%, transparent); color: var(--color-text); padding: 0 2px; border-radius: 2px; }
.search-empty { padding: 24px; text-align: center; color: var(--color-text-muted); font-size: 14px; }
.search-hint { padding: 10px 16px; border-top: 1px solid var(--color-border); font-size: 12px; color: var(--color-text-muted); display: flex; gap: 16px; }

.toast {
  position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
  padding: 10px 16px;
  background: var(--color-text); color: var(--color-bg);
  border-radius: 8px;
  font-size: 13px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.2);
  z-index: 60;
  opacity: 0; transition: opacity 0.18s;
  pointer-events: none;
}
.toast.visible { opacity: 1; }

.sidebar-backdrop {
  display: none;
  position: fixed; inset: 56px 0 0 0; z-index: 24;
  background: rgba(0,0,0,0.4);
  opacity: 0; transition: opacity 0.18s ease;
  pointer-events: none;
}
.sidebar-backdrop.visible { opacity: 1; pointer-events: auto; }

@media (max-width: 1180px) {
  .app { grid-template-columns: var(--sidebar-w) minmax(0,1fr); grid-template-areas: "topbar topbar" "sidebar content"; }
  .toc-rail { display: none; }
  .content { padding: 28px 36px 80px; }
  .header-links { display: none; }
}
@media (max-width: 900px) {
  :root { --sidebar-w: 260px; }
  .content { padding: 24px 28px 60px; }
  .page h1 { font-size: 1.75rem; }
  .page h2 { font-size: 1.25rem; }
  .page h3 { font-size: 1.05rem; }
}
@media (max-width: 720px) {
  .app { grid-template-columns: 1fr; grid-template-areas: "topbar" "content"; }
  .hamburger { display: flex; }
  .sidebar {
    position: fixed; top: 56px; left: 0; bottom: 0;
    width: min(86vw, 320px); z-index: 25;
    transform: translateX(-100%);
    transition: transform 0.22s cubic-bezier(0.32, 0.72, 0, 1);
    will-change: transform;
    border-right: 1px solid var(--color-border);
  }
  .sidebar.open { transform: translateX(0); box-shadow: 0 8px 32px rgba(0,0,0,0.18); }
  .sidebar-backdrop { display: block; }
  .content { padding: 18px 18px 56px; }
  .page { font-size: 15.5px; }
  .page h1 { font-size: 1.6rem; }
  .page pre { font-size: 0.82em; padding: 12px 14px; }
  .prev-next { grid-template-columns: 1fr; gap: 10px; }
  .pn-card.next { text-align: left; }
  .topbar { padding: 0 12px; gap: 8px; }
  .topbar-search { width: 36px; padding: 6px 8px; justify-content: center; }
  .topbar-search span:not(.search-icon) { display: none; }
  .topbar-search kbd { display: none; }
  .brand-title { max-width: 50vw; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .search-overlay { padding-top: 4vh; }
  .search-modal { width: 96vw; max-height: 92vh; }
  .search-input { font-size: 16px; padding: 14px 16px; }
  .scroll-top { bottom: 16px; right: 16px; }
  .site-footer { flex-direction: column; align-items: flex-start; }
}
@media (max-width: 420px) {
  .content { padding: 16px 14px 48px; }
  .page h1 { font-size: 1.4rem; }
  .breadcrumbs { font-size: 12px; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; animation: none !important; }
}

@media print {
  .topbar, .sidebar, .sidebar-backdrop, .toc-rail, .prev-next, .copy-btn,
  .search-overlay, .scroll-top, .reading-progress, .toast { display: none !important; }
  .app { display: block; height: auto; }
  .content { padding: 0; overflow: visible; }
}
"""


def theme_css(cfg):
    t = cfg["theme"]
    return textwrap.dedent(f"""
    :root {{
      --color-bg: {t['bg']};
      --color-bg-alt: {t['bg_alt']};
      --color-bg-code: {t['bg_code']};
      --color-text: {t['text']};
      --color-text-muted: {t['text_muted']};
      --color-border: {t['border']};
      --color-accent: {t['accent']};
      --color-accent-dark: {t['accent_dark']};
      --font-body: {t['font_body']};
      --font-heading: {t['font_heading']};
      --font-mono: {t['font_mono']};
      --radius: {t['radius']}px;
      --sidebar-w: {t['sidebar_width']}px;
      --content-max: {t['content_max']}px;
      --toc-w: 240px;
    }}
    [data-theme="dark"] {{
      --color-bg: {t['bg_dark']};
      --color-bg-alt: {t['bg_alt_dark']};
      --color-bg-code: {t['bg_code_dark']};
      --color-text: {t['text_dark']};
      --color-text-muted: {t['text_muted_dark']};
      --color-border: {t['border_dark']};
      --color-accent: {t['accent_dark']};
    }}
    @media (prefers-color-scheme: dark) {{
      [data-theme="auto"] {{
        --color-bg: {t['bg_dark']};
        --color-bg-alt: {t['bg_alt_dark']};
        --color-bg-code: {t['bg_code_dark']};
        --color-text: {t['text_dark']};
        --color-text-muted: {t['text_muted_dark']};
        --color-border: {t['border_dark']};
        --color-accent: {t['accent_dark']};
      }}
    }}
    """).strip()


def pygments_css(cfg):
    light = HtmlFormatter(style=cfg["theme"]["pygments_style_light"]).get_style_defs(".highlight")
    dark = HtmlFormatter(style=cfg["theme"]["pygments_style_dark"]).get_style_defs(".highlight")
    dark_scoped = re.sub(r"\.highlight", "[data-theme='dark'] .highlight", dark)
    dark_auto = re.sub(r"\.highlight", "[data-theme='auto'] .highlight", dark)
    return (
        light + "\n"
        + dark_scoped + "\n"
        + "@media (prefers-color-scheme: dark) {\n" + dark_auto + "\n}\n"
    )


RUNTIME_JS = r"""
(function() {
  const SITE = JSON.parse(document.getElementById('site-data').textContent);
  const pageEl = document.getElementById('page');
  const tocRail = document.getElementById('tocRail');
  const sidebar = document.getElementById('sidebar');
  const backdrop = document.getElementById('sidebarBackdrop');
  const hamburger = document.getElementById('hamburger');
  const themeToggle = document.getElementById('themeToggle');
  const progressBar = document.getElementById('readingProgress');
  const scrollTopBtn = document.getElementById('scrollTop');
  const toastEl = document.getElementById('toast');

  const pagesById = {};
  SITE.pages.forEach(p => pagesById[p.id] = p);

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
  function escapeRegex(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  function toast(text) {
    if (!toastEl) return;
    toastEl.textContent = text;
    toastEl.hidden = false;
    requestAnimationFrame(() => toastEl.classList.add('visible'));
    clearTimeout(toast._t);
    toast._t = setTimeout(() => {
      toastEl.classList.remove('visible');
      setTimeout(() => { toastEl.hidden = true; }, 200);
    }, 1600);
  }

  function parseHash() {
    let h = location.hash.replace(/^#\/?/, '');
    let anchor = '';
    const idx = h.indexOf('#');
    if (idx >= 0) { anchor = h.slice(idx + 1); h = h.slice(0, idx); }
    return { page: h || SITE.home, anchor };
  }

  function go(pageId, anchor) {
    location.hash = '#/' + pageId + (anchor ? '#' + anchor : '');
  }

  function openSidebar() {
    sidebar.classList.add('open');
    if (backdrop) backdrop.classList.add('visible');
  }
  function closeSidebar() {
    sidebar.classList.remove('open');
    if (backdrop) backdrop.classList.remove('visible');
  }

  function render() {
    const { page, anchor } = parseHash();
    const p = pagesById[page] || pagesById[SITE.home];
    if (!p) { pageEl.innerHTML = '<h1>Page not found</h1>'; return; }
    document.title = p.title + ' · ' + SITE.title;

    let html = '';
    if (SITE.features.breadcrumbs && p.breadcrumbs && p.breadcrumbs.length > 1) {
      html += '<div class="breadcrumbs">';
      p.breadcrumbs.forEach((c, i) => {
        if (i > 0) html += '<span class="sep">/</span>';
        if (i === p.breadcrumbs.length - 1) html += '<span class="last">' + escapeHtml(c.name) + '</span>';
        else if (c.path) html += '<a href="#/' + c.path + '">' + escapeHtml(c.name) + '</a>';
        else html += '<span>' + escapeHtml(c.name) + '</span>';
      });
      html += '</div>';
    }

    const infoBits = [];
    if (SITE.features.estimated_read_time && p.read_time) infoBits.push(p.read_time + ' min read');
    if (SITE.features.last_updated && p.last_updated) infoBits.push('Updated ' + p.last_updated);
    if (infoBits.length) {
      html += '<div class="page-info">' + infoBits.map((b, i) =>
        (i > 0 ? '<span class="dot"></span>' : '') + '<span>' + escapeHtml(b) + '</span>'
      ).join('') + '</div>';
    }

    html += p.body;

    const metaBits = [];
    if (p.editUrl) metaBits.push('<a class="md-ext" href="' + p.editUrl + '" target="_blank" rel="noopener">Edit this page</a>');
    if (SITE.features.show_last_built && SITE.built_at) metaBits.push('<span>Last built: ' + SITE.built_at + '</span>');
    if (metaBits.length) html += '<div class="page-meta">' + metaBits.join('') + '</div>';

    pageEl.innerHTML = html;

    if (SITE.features.prev_next) {
      const idx = SITE.order.indexOf(p.id);
      const prev = idx > 0 ? pagesById[SITE.order[idx - 1]] : null;
      const next = idx >= 0 && idx < SITE.order.length - 1 ? pagesById[SITE.order[idx + 1]] : null;
      const pn = document.querySelector('.prev-next');
      if (pn) {
        pn.innerHTML =
          (prev ? '<a class="pn-card prev" href="#/' + prev.id + '"><span class="pn-label"><svg class="pn-arrow" viewBox="0 0 16 16" width="14" height="14"><path d="M11 3l-5 5 5 5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg> Previous</span><span class="pn-title">' + escapeHtml(prev.title) + '</span></a>' : '<span class="pn-card prev pn-empty"></span>') +
          (next ? '<a class="pn-card next" href="#/' + next.id + '"><span class="pn-label">Next <svg class="pn-arrow" viewBox="0 0 16 16" width="14" height="14"><path d="M5 3l5 5-5 5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></span><span class="pn-title">' + escapeHtml(next.title) + '</span></a>' : '<span class="pn-card next pn-empty"></span>');
      }
    }

    if (SITE.features.copy_code) {
      pageEl.querySelectorAll('pre').forEach(pre => {
        const btn = document.createElement('button');
        btn.className = 'copy-btn'; btn.type = 'button'; btn.textContent = 'Copy';
        btn.addEventListener('click', () => {
          const code = pre.querySelector('code') ? pre.querySelector('code').innerText : pre.innerText;
          navigator.clipboard.writeText(code).then(() => {
            btn.textContent = 'Copied'; btn.classList.add('copied');
            setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 1400);
          });
        });
        pre.appendChild(btn);
      });
    }

    if (SITE.features.anchor_copy) {
      pageEl.querySelectorAll('.md-anchor').forEach(a => {
        a.addEventListener('click', e => {
          e.preventDefault();
          const slug = a.getAttribute('data-anchor-link');
          go(p.id, slug);
          const url = location.origin + location.pathname + '#/' + p.id + '#' + slug;
          if (navigator.clipboard) navigator.clipboard.writeText(url).then(() => toast('Link copied'));
        });
      });
    }

    pageEl.querySelectorAll('a[href^="#"]').forEach(a => {
      const h = a.getAttribute('href');
      if (h === '#' || h.startsWith('#/')) return;
      if (h.startsWith('#')) a.setAttribute('href', '#/' + p.id + h);
    });

    renderToc(p);

    document.querySelectorAll('.nav-link, .nav-folder-link').forEach(el => {
      const isActive = el.dataset.page === p.id;
      el.classList.toggle('active', isActive);
      if (isActive) {
        let n = el.closest('details');
        while (n) { n.open = true; n = n.parentElement && n.parentElement.closest('details'); }
      }
    });

    closeSidebar();

    requestAnimationFrame(() => {
      const contentEl = document.querySelector('.content');
      if (anchor) {
        const target = document.getElementById(anchor);
        if (target) {
          const rect = target.getBoundingClientRect();
          contentEl.scrollTop = contentEl.scrollTop + rect.top - 80;
        }
      } else {
        contentEl.scrollTop = 0;
      }
      updateProgress();
    });
  }

  function renderToc(p) {
    if (!SITE.features.toc || !p.toc || p.toc.length === 0) {
      tocRail.innerHTML = ''; teardownScrollSpy(); return;
    }
    let html = '<div class="toc-title">On this page</div><ul>';
    p.toc.forEach(t => {
      html += '<li><a class="lvl-' + t.level + '" href="#/' + p.id + '#' + t.id + '" data-anchor="' + t.id + '">' + escapeHtml(t.text) + '</a></li>';
    });
    html += '</ul>';
    tocRail.innerHTML = html;
    setupScrollSpy(p);
  }

  let scrollSpy = null;
  function teardownScrollSpy() {
    if (scrollSpy) {
      scrollSpy.el.removeEventListener('scroll', scrollSpy.handler);
      scrollSpy = null;
    }
  }
  function setupScrollSpy() {
    teardownScrollSpy();
    const links = Array.from(tocRail.querySelectorAll('a[data-anchor]'));
    if (!links.length) return;
    const headings = links.map(l => document.getElementById(l.dataset.anchor)).filter(Boolean);
    const contentEl = document.querySelector('.content');
    let raf = 0;
    function compute() {
      raf = 0;
      let active = headings[0];
      for (const h of headings) {
        if (h.getBoundingClientRect().top < 120) active = h; else break;
      }
      const id = active && active.id;
      for (const l of links) {
        const want = l.dataset.anchor === id;
        if (l.classList.contains('active') !== want) l.classList.toggle('active', want);
      }
    }
    function handler() { if (!raf) raf = requestAnimationFrame(compute); }
    contentEl.addEventListener('scroll', handler, { passive: true });
    scrollSpy = { el: contentEl, handler };
    compute();
  }

  function updateProgress() {
    if (!progressBar && !scrollTopBtn) return;
    const el = document.querySelector('.content');
    const max = el.scrollHeight - el.clientHeight;
    const pct = max > 0 ? Math.min(1, Math.max(0, el.scrollTop / max)) : 0;
    if (progressBar) progressBar.style.setProperty('--progress', pct);
    if (scrollTopBtn) {
      const visible = el.scrollTop > 400;
      if (visible !== scrollTopBtn.classList.contains('visible')) {
        scrollTopBtn.classList.toggle('visible', visible);
        scrollTopBtn.hidden = !visible;
      }
    }
  }
  (function() {
    const el = document.querySelector('.content');
    let raf = 0;
    el.addEventListener('scroll', () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; updateProgress(); }); }, { passive: true });
  })();

  if (scrollTopBtn) scrollTopBtn.addEventListener('click', () => {
    document.querySelector('.content').scrollTo({ top: 0, behavior: 'smooth' });
  });

  document.querySelectorAll('.nav-link, .nav-folder-link').forEach(el => {
    el.addEventListener('click', e => {
      const p = el.dataset.page;
      if (!p) return;
      e.preventDefault();
      go(p);
    });
  });

  if (hamburger) hamburger.addEventListener('click', () => {
    if (sidebar.classList.contains('open')) closeSidebar(); else openSidebar();
  });
  if (backdrop) backdrop.addEventListener('click', closeSidebar);

  function applyTheme(mode) {
    document.documentElement.setAttribute('data-theme', mode);
    try { localStorage.setItem('mdh-theme', mode); } catch (e) {}
  }
  (function () {
    let saved = null;
    try { saved = localStorage.getItem('mdh-theme'); } catch (e) {}
    if (saved === 'light' || saved === 'dark') { applyTheme(saved); return; }
    const initial = document.documentElement.getAttribute('data-theme');
    if (initial === 'auto' || !initial) {
      const dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      applyTheme(dark ? 'dark' : 'light');
    }
  })();
  if (themeToggle) themeToggle.addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-theme');
    applyTheme(cur === 'dark' ? 'light' : 'dark');
  });

  const searchOverlay = document.getElementById('searchOverlay');
  const searchInput = document.getElementById('searchInput');
  const searchResults = document.getElementById('searchResults');
  const searchTrigger = document.querySelector('.topbar-search');
  let searchSel = 0;

  function openSearch() {
    if (!searchOverlay) return;
    searchOverlay.hidden = false;
    searchInput.value = '';
    searchResults.innerHTML = '<div class="search-empty">Start typing to search…</div>';
    setTimeout(() => searchInput.focus(), 0);
  }
  function closeSearch() { if (searchOverlay) searchOverlay.hidden = true; }
  if (searchTrigger) searchTrigger.addEventListener('click', () => {
    if (searchOverlay && !searchOverlay.hidden) closeSearch(); else openSearch();
  });
  const searchClose = document.getElementById('searchClose');
  if (searchClose) searchClose.addEventListener('click', closeSearch);

  // Backdrop close — track mousedown so a drag-out from the modal doesn't close it.
  let searchDownOnBackdrop = false;
  if (searchOverlay) {
    searchOverlay.addEventListener('mousedown', e => {
      searchDownOnBackdrop = (e.target === searchOverlay);
    });
    searchOverlay.addEventListener('mouseup', e => {
      if (searchDownOnBackdrop && e.target === searchOverlay) closeSearch();
      searchDownOnBackdrop = false;
    });
    searchOverlay.addEventListener('touchstart', e => {
      searchDownOnBackdrop = (e.target === searchOverlay);
    }, { passive: true });
    searchOverlay.addEventListener('touchend', e => {
      if (searchDownOnBackdrop && e.target === searchOverlay) closeSearch();
      searchDownOnBackdrop = false;
    });
  }

  document.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openSearch(); }
    else if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
      e.preventDefault(); openSearch();
    } else if (e.key === 'Escape') closeSearch();
  });

  if (searchInput) {
    let timer = 0;
    searchInput.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => runSearch(searchInput.value), 100);
    });
    searchInput.addEventListener('keydown', e => {
      const items = Array.from(searchResults.querySelectorAll('.search-result'));
      if (e.key === 'ArrowDown') { e.preventDefault(); searchSel = Math.min(items.length - 1, searchSel + 1); selectResult(items); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); searchSel = Math.max(0, searchSel - 1); selectResult(items); }
      else if (e.key === 'Enter') { e.preventDefault(); const it = items[searchSel]; if (it) it.click(); }
    });
  }
  function selectResult(items) {
    items.forEach((it, i) => it.classList.toggle('active', i === searchSel));
    const sel = items[searchSel]; if (sel) sel.scrollIntoView({ block: 'nearest' });
  }
  function runSearch(q) {
    q = q.trim();
    if (!q) { searchResults.innerHTML = '<div class="search-empty">Start typing to search…</div>'; return; }
    const ql = q.toLowerCase();
    const matches = [];
    SITE.pages.forEach(p => {
      if (p.searchable === false) return;
      const titleScore = p.title.toLowerCase().includes(ql) ? 5 : 0;
      const idx = p.search_text.toLowerCase().indexOf(ql);
      if (titleScore === 0 && idx < 0) return;
      let snippet = '';
      if (idx >= 0) {
        const s = Math.max(0, idx - 40);
        snippet = (s > 0 ? '…' : '') + p.search_text.slice(s, idx + ql.length + 80) + '…';
        snippet = escapeHtml(snippet).replace(new RegExp(escapeRegex(q), 'ig'), m => '<mark>' + m + '</mark>');
      }
      matches.push({ p, score: titleScore + (idx >= 0 ? 1 : 0), snippet });
    });
    matches.sort((a, b) => b.score - a.score);
    if (!matches.length) { searchResults.innerHTML = '<div class="search-empty">No results.</div>'; return; }
    searchResults.innerHTML = matches.slice(0, 25).map((m, i) =>
      '<a class="search-result' + (i === 0 ? ' active' : '') + '" href="#/' + m.p.id + '">' +
      '<div class="search-result-title">' + escapeHtml(m.p.title) + '</div>' +
      '<div class="search-result-path">' + escapeHtml(m.p.id) + '</div>' +
      (m.snippet ? '<div class="search-result-snippet">' + m.snippet + '</div>' : '') +
      '</a>'
    ).join('');
    searchSel = 0;
    Array.from(searchResults.querySelectorAll('.search-result')).forEach(it => {
      it.addEventListener('click', () => closeSearch());
    });
  }

  window.addEventListener('hashchange', render);
  render();
})();
"""


def build(cfg, source, output):
    if not source.exists():
        print(f"source folder does not exist: {source}")
        sys.exit(2)
    print(f"scanning {source}")
    pages = scan_pages(source, cfg)
    if not pages:
        print(f"no .md files found in {source}")
        sys.exit(2)
    print(f"rendering {len(pages)} pages")
    for p in pages:
        render_page(p, source, cfg)

    pages_by_id = {p.rel: p for p in pages if not p.hidden}
    nav = build_nav(pages, cfg)
    nav_html = render_nav(nav, cfg)
    flat = flatten_order(nav, pages_by_id)
    order_ids = [p.rel for p in flat]
    home = find_home(pages, cfg)

    edit_template = cfg["features"].get("edit_link")
    site_pages = []
    for p in pages:
        if p.hidden:
            continue
        crumbs = make_breadcrumbs(p.rel, pages_by_id)
        edit_url = None
        if edit_template:
            rel_md = p.src.relative_to(source).as_posix()
            edit_url = edit_template.format(path=rel_md)
        site_pages.append({
            "id": p.rel,
            "title": p.title,
            "description": p.description,
            "body": p.html,
            "toc": p.toc,
            "breadcrumbs": crumbs,
            "editUrl": edit_url,
            "read_time": estimate_read_minutes(p.word_count),
            "last_updated": p.last_updated,
            "searchable": p.searchable,
            "search_text": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", p.html))[:8000],
        })

    site_data = {
        "title": cfg["site"]["title"],
        "home": home,
        "order": order_ids,
        "pages": site_pages,
        "features": cfg["features"],
        "built_at": time.strftime("%Y-%m-%d %H:%M"),
    }

    logo_uri = file_to_data_uri(cfg["site"].get("logo"))
    logo_html = (
        f'<img class="brand-logo" src="{logo_uri}" alt="">'
        if logo_uri else
        f'<span class="brand-logo brand-logo-default">{BUILTIN_ICONS["book"]}</span>'
    )
    favicon_uri = file_to_data_uri(cfg["site"].get("favicon"))
    favicon_tag = f'<link rel="icon" href="{favicon_uri}">' if favicon_uri else ""

    google_fonts = cfg["theme"].get("google_fonts") or []
    google_fonts_link = ""
    if google_fonts:
        family = "&family=".join(google_fonts)
        url = f"https://fonts.googleapis.com/css2?family={family}&display=swap"
        google_fonts_link = (
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
            f'<link rel="stylesheet" href="{url}" media="print" onload="this.media=\'all\'">'
            f'<noscript><link rel="stylesheet" href="{url}"></noscript>'
        )

    search_html = (
        '<button class="topbar-search" type="button" aria-label="Search">'
        '<svg class="search-icon" viewBox="0 0 20 20" width="14" height="14" aria-hidden="true">'
        '<circle cx="9" cy="9" r="6" fill="none" stroke="currentColor" stroke-width="1.6"/>'
        '<path d="M14 14l4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>'
        '<span>Search docs</span>'
        '<kbd>⌘K</kbd></button>'
    ) if cfg["features"].get("search", True) else ""

    theme_toggle_html = (
        '<button class="theme-toggle" id="themeToggle" type="button" aria-label="Toggle theme">'
        f'<span class="icon-moon">{BUILTIN_ICONS["moon"]}</span>'
        f'<span class="icon-sun">{BUILTIN_ICONS["sun"]}</span>'
        '</button>'
    ) if cfg["features"].get("dark_mode_toggle", True) else ""

    prev_next_html = '<div class="prev-next"></div>' if cfg["features"].get("prev_next", True) else ""

    def render_links(items):
        out = []
        for it in items or []:
            text = html.escape(str(it.get("text", "")))
            url = html.escape(str(it.get("url", "#")), quote=True)
            external = url.startswith("http")
            cls = ' class="md-ext"' if external else ""
            tgt = ' target="_blank" rel="noopener noreferrer"' if external else ""
            icon_name = it.get("icon")
            icon_svg = fetch_icon(icon_name, cfg) if icon_name else None
            icon_html = f'<span class="link-icon">{icon_svg}</span>' if icon_svg else ""
            out.append(f'<a{cls} href="{url}"{tgt}>{icon_html}{text}</a>')
        return "".join(out)

    initial_theme = cfg["theme"].get("mode", "auto")
    if initial_theme not in ("auto", "light", "dark"):
        initial_theme = "auto"
    density = cfg["theme"].get("density", "normal")
    if density not in ("cozy", "normal", "compact"):
        density = "normal"

    extra_js = cfg["theme"].get("extra_js", "")
    if extra_js:
        extra_js = f"<script>{extra_js}</script>"

    page_html = HTML_TEMPLATE.format(
        lang=cfg["site"].get("lang", "en"),
        initial_theme=initial_theme,
        density=density,
        site_title=html.escape(str(cfg["site"]["title"])),
        site_description=html.escape(str(cfg["site"].get("description", ""))),
        favicon_tag=favicon_tag,
        google_fonts_link=google_fonts_link,
        extra_head=cfg["site"].get("extra_head", "") or "",
        base_css=BASE_CSS,
        pygments_css=pygments_css(cfg),
        theme_css=theme_css(cfg),
        extra_css=cfg["theme"].get("extra_css", "") or "",
        logo_html=logo_html,
        header_links_html=render_links(cfg["nav"].get("header_links", [])),
        footer_links_html=render_links(cfg["nav"].get("footer_links", [])),
        nav_html=nav_html,
        search_html=search_html,
        theme_toggle_html=theme_toggle_html,
        prev_next_html=prev_next_html,
        footer_html=html.escape(str(cfg["site"].get("footer", ""))),
        site_data_json=json.dumps(site_data, separators=(",", ":")).replace("</", "<\\/"),
        runtime_js=RUNTIME_JS,
        extra_js=extra_js,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page_html, encoding="utf-8")
    print(f"wrote {output} ({output.stat().st_size / 1024:,.1f} KB)")


EXAMPLE_CONFIG = """\
site:
  title: My Project Docs
  description: A short tagline shown in <meta description>.
  footer: © My Project · MIT License

source: docs
output: site.html

theme:
  preset: default       # default | slate | warm | mint | sand
  mode: auto            # auto | light | dark
  density: normal       # cozy | normal | compact

nav:
  show_root_readme_as_home: true
  collapse_depth: 1
  header_links:
    - { text: GitHub, url: https://github.com/me/myrepo }
  footer_links:
    - { text: Changelog, url: https://github.com/me/myrepo/releases }

features:
  search: true
  toc: true
  dark_mode_toggle: true
  reading_progress: true
  scroll_top_button: true
  estimated_read_time: true
  last_updated: true
  anchor_copy: true
  code_titles: true
"""

EXAMPLE_INTRO = """\
---
title: Welcome
order: 1
---

# Welcome

Replace this with your own content. Run `python mdtohtml.py` to rebuild.
"""

EXAMPLE_NESTED = """\
---
title: WebSocket Protocol
order: 1
---

# WebSocket Protocol

Nested pages live under `docs/<folder>/<page>.md`.
"""


def cmd_init(target):
    cfg = target / "config.yml"
    docs = target / "docs"
    if cfg.exists():
        print(f"{cfg} already exists, skipping")
    else:
        cfg.write_text(EXAMPLE_CONFIG, encoding="utf-8")
        print(f"wrote {cfg}")
    docs.mkdir(exist_ok=True)
    intro = docs / "intro.md"
    if not intro.exists():
        intro.write_text(EXAMPLE_INTRO, encoding="utf-8")
        print(f"wrote {intro}")
    proto = docs / "protocol"
    proto.mkdir(exist_ok=True)
    ws = proto / "websockets.md"
    if not ws.exists():
        ws.write_text(EXAMPLE_NESTED, encoding="utf-8")
        print(f"wrote {ws}")
    print("\ndone. Run: python mdtohtml.py")


def watch_loop(cfg_path, source, output):
    print("watching for changes (Ctrl-C to stop)")
    last = {}

    def snapshot():
        out = {}
        for p in list(source.rglob("*")) + [cfg_path]:
            try:
                out[p] = p.stat().st_mtime
            except FileNotFoundError:
                pass
        return out

    last = snapshot()
    try:
        while True:
            time.sleep(0.6)
            now = snapshot()
            if now != last:
                last = now
                try:
                    cfg = load_config(cfg_path)
                    build(cfg, source, output)
                except Exception as e:
                    print(f"build error: {e}")
    except KeyboardInterrupt:
        print()


def serve(directory, port):
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(directory), **kw)
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"http://localhost:{port}/  (Ctrl-C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print()


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="mdtohtml",
        description="Render a tree of Markdown into a single shareable HTML file.",
    )
    parser.add_argument("-c", "--config", default="config.yml")
    parser.add_argument("-s", "--source", default=None)
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("--init", action="store_true", help="Scaffold a starter project here")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--serve", type=int, nargs="?", const=8000, default=None, metavar="PORT")
    args = parser.parse_args(argv)

    if args.init:
        cmd_init(Path.cwd())
        return 0

    cfg = load_config(args.config)
    source = Path(args.source or cfg.get("source", "docs"))
    output = Path(args.output or cfg.get("output", "site.html"))

    build(cfg, source, output)

    if args.serve is not None:
        threading.Thread(target=serve, args=(output.parent.resolve(), args.serve), daemon=True).start()
    if args.watch:
        watch_loop(Path(args.config), source, output)
    elif args.serve is not None:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
