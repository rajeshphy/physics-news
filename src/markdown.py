from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    from .common import IST, POSTS, NewsItem, clean_text
    from .filter import (
        clean_summary,
        generic_title,
        infer_source_ids,
        item_map,
        readable_title,
        split_digest_header,
        split_digest_title,
        validate_source_ids,
        extract_source_ids,
        plain_text,
    )
except ImportError:
    from common import IST, POSTS, NewsItem, clean_text
    from filter import (
        clean_summary,
        generic_title,
        infer_source_ids,
        item_map,
        readable_title,
        split_digest_header,
        split_digest_title,
        validate_source_ids,
        extract_source_ids,
        plain_text,
    )


def yaml_escape(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def inline_markdown_to_html(text: str) -> str:
    placeholders: list[str] = []

    def link_replacer(match: re.Match[str]) -> str:
        label = html.escape(match.group(1))
        url = html.escape(match.group(2), quote=True)
        placeholders.append(f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>')
        return f"@@LINK{len(placeholders) - 1}@@"

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_replacer, text)
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    for index, replacement in enumerate(placeholders):
        escaped = escaped.replace(f"@@LINK{index}@@", replacement)
    return escaped


def source_chips_html(source_ids: list[str], lookup: dict[str, NewsItem]) -> str:
    links: list[str] = []
    seen: set[str] = set()
    for source_id in source_ids:
        if source_id in seen or source_id not in lookup:
            continue
        seen.add(source_id)
        item = lookup[source_id]
        label = html.escape(source_id)
        url = html.escape(item.url, quote=True)
        # item.url has already been resolved to the direct link in fetch.py/directlink.py.
        links.append(f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>')
    return f'<span class="source-chips">{" ".join(links)}</span>' if links else ""


def summary_to_html(summary: str, items: list[NewsItem], points_per_section: int = 5) -> str:
    _, body = split_digest_title(summary)
    lookup = item_map(items)
    current_section = ""
    total_count = 0
    max_points = min(5, points_per_section)
    html_lines: list[str] = []
    in_list = False

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        section_match = re.match(r"^SECTION\s*:\s*(.+)$", line, flags=re.I)
        if section_match:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            heading = clean_text(section_match.group(1))
            current_section = "india" if "india" in heading.lower() else "world"
            html_lines.append(f"<h2>{html.escape(heading)}</h2>")
            html_lines.append('<ul class="digest-points">')
            in_list = True
            continue

        if line.startswith(("- ", "* ")) and total_count < max_points:
            if not in_list:
                html_lines.append('<ul class="digest-points">')
                in_list = True
            bullet = line[2:].strip()
            item_text, source_ids = extract_source_ids(bullet)
            if current_section:
                source_ids = validate_source_ids(item_text, source_ids, lookup, current_section)
                if not source_ids:
                    source_ids = infer_source_ids(item_text, items, current_section)
            chips = source_chips_html(source_ids, lookup)
            html_lines.append(f"  <li>{inline_markdown_to_html(item_text)}{chips}</li>")
            total_count += 1
            continue

        if not line.startswith(("TITLE:", "SUMMARY:")):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<p>{inline_markdown_to_html(line)}</p>")

    if in_list:
        html_lines.append("</ul>")
    return "\n".join(html_lines)


def sources_to_html(items: list[NewsItem]) -> str:
    lines = ['<ul class="source-list">']
    for item in items[:12]:
        title = html.escape(readable_title(item.title))
        url = html.escape(item.url, quote=True)
        label = html.escape(item.item_id)
        lines.append(f'  <li><a href="{url}" target="_blank" rel="noopener noreferrer">[{label}] {title}</a></li>')
    lines.append("</ul>")
    return "\n".join(lines)


def post_title(summary: str, items: list[NewsItem]) -> str:
    title, _, _ = split_digest_header(summary)
    if title and not generic_title(title):
        return title
    for item in items:
        if item.title:
            return readable_title(item.title)[:80].rstrip(" ,;:")
    return "Physics News Brief"


def one_line_summary(summary: str, items: list[NewsItem]) -> str:
    _, teaser, _ = split_digest_header(summary)
    if teaser:
        return teaser
    body = plain_text(summary)
    if body:
        return clean_summary(body)
    if items:
        return clean_summary(items[0].title)
    return "Daily physics news for classroom and research awareness"


def build_post(summary: str, items: list[NewsItem], used_ai: bool) -> Path:
    POSTS.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    now_ist = now.astimezone(IST)
    post_path = POSTS / f"{now.date().isoformat()}-physics-brief.md"

    try:
        run_time = now_ist.strftime("%-I:%M%p")
    except ValueError:
        run_time = now_ist.strftime("%I:%M%p").lstrip("0")

    ai_note = f"Gemini Summary: {run_time}" if used_ai else f"Headline Digest: {run_time}"
    teaser = one_line_summary(summary, items)
    title = post_title(summary, items)
    source_list = sources_to_html(items)
    digest_html = summary_to_html(summary, items)

    content = f"""---
layout: default
title: {yaml_escape(title)}
date: {now.isoformat()}
summary: {yaml_escape(teaser)}
run_time_ist: {yaml_escape(run_time)}
---

<article class="digest-post">
  <a class="back-link" href="{{{{ '/' | relative_url }}}}">Physics Brief</a>
  <p class="post-meta">{html.escape(ai_note)}</p>

{digest_html}

<section class="source-note">
  <h2>Source</h2>
  <p>Generated from configured physics RSS feeds. Source links below are direct article links where the feed allowed resolution.</p>
</section>

<details class="tp-sources">
<summary>Headlines considered</summary>

{source_list}

</details>
</article>
"""
    post_path.write_text(content, encoding="utf-8")
    return post_path
