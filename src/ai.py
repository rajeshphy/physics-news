from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

try:
    from .common import DATA, DEFAULT_GEMINI_MODEL, GEMINI_API_ROOT, IST, QUOTA_FILE, NewsItem
    from .filter import fallback_home_summary, group_related_items, readable_title, score_story_group
except ImportError:
    from common import DATA, DEFAULT_GEMINI_MODEL, GEMINI_API_ROOT, IST, QUOTA_FILE, NewsItem
    from filter import fallback_home_summary, group_related_items, readable_title, score_story_group


def prompt_story_groups(items: list[NewsItem], settings: dict) -> str:
    lines: list[str] = []
    for section, heading in (("india", "India Physics"), ("world", "World Physics")):
        lines.append(f"{heading} candidate story groups:")
        section_items = [item for item in items if item.section == section]
        if not section_items:
            lines.append("- No fresh items found for this section.")
            continue
        for group_index, group in enumerate(group_related_items(section_items), 1):
            ids = ", ".join(f"[{item.item_id}]" for item in group)
            dates = ", ".join(sorted({item.published for item in group if item.published}))
            score, reasons = score_story_group(group, settings)
            signals = "; ".join(reasons[:4])
            lines.append(f"- Group {group_index} {ids}; score: {score}; signals: {signals}; dates: {dates}")
            for item in group:
                lines.append(f"  {item.item_id}: {item.title} | {item.source}")
    return "\n".join(lines)


def load_quota() -> dict:
    if not QUOTA_FILE.exists():
        return {"day": "", "count": 0, "last_call": 0.0}
    try:
        return json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"day": "", "count": 0, "last_call": 0.0}


def reserve_gemini_call(max_daily_calls: int, min_interval_seconds: int) -> None:
    DATA.mkdir(exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()
    quota = load_quota()
    if quota.get("day") != today:
        quota = {"day": today, "count": 0, "last_call": 0.0}
    if int(quota.get("count", 0)) >= max_daily_calls:
        raise RuntimeError(f"Daily Gemini call limit reached: {max_daily_calls}")
    elapsed = time.time() - float(quota.get("last_call", 0.0))
    if elapsed < min_interval_seconds:
        time.sleep(min_interval_seconds - elapsed)
    quota["count"] = int(quota.get("count", 0)) + 1
    quota["last_call"] = time.time()
    QUOTA_FILE.write_text(json.dumps(quota, indent=2), encoding="utf-8")


def gemini_summary(items: list[NewsItem], api_key: str, points_total: int, settings: dict) -> str:
    reserve_gemini_call(max_daily_calls=20, min_interval_seconds=12)
    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    current_date = datetime.now(IST).date().isoformat()
    max_points = min(5, points_total)
    prompt_items = prompt_story_groups(items, settings)
    prompt = f"""
Create an English daily physics news brief for a physics teacher to share with students.
Current IST date: {current_date}

Rules:
- First line must be: TITLE: concise title for the full brief.
- Second line must be: SUMMARY: one concise homepage line covering the main themes across both sections.
- Keep SUMMARY under 160 characters.
- Then produce exactly two sections: SECTION: India Physics and SECTION: World Physics.
- Across both sections combined, output 0 to {max_points} significant bullet points total.
- It is better to output fewer than {max_points} points than to include weak, duplicate, stale, or filler news.
- Use only the supplied items.
- Treat each candidate group as one possible story.
- End each bullet with source ids using this exact format: Sources: [I1], [I3] or Sources: [W2]
- Do not include inline URLs.
- Format bullets as: - **Short topic:** one concise synthesized sentence explaining what happened and why it matters. Sources: [I1]

Candidate story groups:
{prompt_items}
""".strip()
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1100},
    }
    body = json.dumps(payload).encode("utf-8")
    url = f"{GEMINI_API_ROOT}/{urllib.parse.quote(model)}:generateContent?key={urllib.parse.quote(api_key)}"
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response: {data}") from exc


def fallback_summary(items: list[NewsItem], points_total: int, settings: dict) -> str:
    lines = [
        "TITLE: Physics News Brief",
        f"SUMMARY: {fallback_home_summary(items, points_total, settings)}",
    ]
    max_points = min(5, points_total)
    selected_by_section: dict[str, list[list[NewsItem]]] = {"india": [], "world": []}
    scored_groups = []
    for section in ("india", "world"):
        section_items = [item for item in items if item.section == section]
        for group in group_related_items(section_items):
            score, _ = score_story_group(group, settings)
            newest = max((item.published_at.timestamp() for item in group if item.published_at), default=0.0)
            scored_groups.append((score, newest, section, group))
    scored_groups.sort(key=lambda row: (row[0], row[1]), reverse=True)
    min_score = int(settings.get("min_group_score", 2))
    selected_keys: set[tuple[str, ...]] = set()

    for section in ("india", "world"):
        section_candidates = [row for row in scored_groups if row[2] == section and row[0] >= min_score]
        if section_candidates and sum(len(groups) for groups in selected_by_section.values()) < max_points:
            _, _, _, group = section_candidates[0]
            selected_by_section[section].append(group)
            selected_keys.add(tuple(item.item_id for item in group))

    remaining = max_points - sum(len(groups) for groups in selected_by_section.values())
    for _, _, section, group in scored_groups:
        if remaining <= 0:
            break
        key = tuple(item.item_id for item in group)
        if key in selected_keys:
            continue
        selected_by_section[section].append(group)
        selected_keys.add(key)
        remaining -= 1

    for section, heading in (("india", "India Physics"), ("world", "World Physics")):
        lines.append(f"SECTION: {heading}")
        for group in selected_by_section[section]:
            lead = group[0]
            source_ids = ", ".join(f"[{item.item_id}]" for item in group[:4])
            lines.append(f"- **{readable_title(lead.source)}:** {readable_title(lead.title)} Sources: {source_ids}")
    return "\n".join(lines)
