from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timedelta, timezone

try:
    from .common import IST, NewsItem, clean_text, config_bool
except ImportError:
    from common import IST, NewsItem, clean_text, config_bool


def configured_keywords(settings: dict, key: str, default: str) -> list[str]:
    raw = settings.get(key, default)
    return [clean_text(keyword).lower() for keyword in str(raw).split(",") if clean_text(keyword)]


def section_keywords(section: str, settings: dict) -> list[str]:
    default_india = "india,indian,isro,iit,iisc,tifr,rri,prl,iiser,dst,barc,dae"
    default_world = (
        "physics,quantum,particle,cosmology,astrophysics,astronomy,nuclear,"
        "condensed matter,materials,plasma,semiconductor,superconduct,photonics,"
        "neutrino,lhc,cern,nasa,esa,telescope"
    )
    return configured_keywords(settings, f"{section}_keywords", default_india if section == "india" else default_world)


def physics_topic_keywords(settings: dict) -> list[str]:
    return configured_keywords(
        settings,
        "physics_topic_keywords",
        (
            "physics,quantum,qubit,particle,astronomy,astrophysics,cosmology,"
            "condensed matter,materials,space,mission,satellite,telescope,aerospace,"
            "gravitational,detector,accelerator,superconduct,semiconductor,plasma,"
            "nuclear,neutrino,dark matter,chandrayaan,aditya-l1,astrosat,gaganyaan"
        ),
    )


def filter_relevant_items(section: str, items: list[NewsItem], settings: dict) -> list[NewsItem]:
    keywords = section_keywords(section, settings)
    topic_keywords = physics_topic_keywords(settings)
    if not keywords:
        return items
    relevant: list[NewsItem] = []
    for item in items:
        haystack = f"{item.title} {item.source}".lower()
        section_match = any(keyword in haystack for keyword in keywords)
        topic_match = any(keyword in haystack for keyword in topic_keywords)
        if section == "india":
            if section_match and topic_match:
                relevant.append(item)
        elif section_match or topic_match:
            relevant.append(item)
    return relevant


def filter_excluded_items(items: list[NewsItem], settings: dict) -> list[NewsItem]:
    excluded = configured_keywords(
        settings,
        "exclude_keywords",
        (
            "horoscope,astrology,photo gallery,photos,web story,viral video,recipe,"
            "lottery,result live,cricket score,match preview"
        ),
    )
    if not excluded:
        return items
    useful: list[NewsItem] = []
    for item in items:
        haystack = f"{item.title} {item.source}".lower()
        if not any(keyword in haystack for keyword in excluded):
            useful.append(item)
    return useful


def item_sort_key(item: NewsItem) -> tuple[int, float]:
    if not item.published_at:
        return (0, 0.0)
    return (1, item.published_at.timestamp())


def filter_fresh_items(items: list[NewsItem], settings: dict) -> list[NewsItem]:
    require_today = config_bool(settings.get("require_ist_today"), True)
    allow_unknown_dates = config_bool(settings.get("allow_unknown_dates"), False)
    max_age_hours = int(settings.get("max_age_hours", 30))
    now_ist = datetime.now(IST)
    fresh: list[NewsItem] = []
    for item in items:
        if not item.published_at:
            if allow_unknown_dates:
                fresh.append(item)
            continue
        published_ist = item.published_at.astimezone(IST)
        if require_today:
            if published_ist.date() == now_ist.date():
                fresh.append(item)
            continue
        if now_ist - published_ist <= timedelta(hours=max_age_hours):
            fresh.append(item)
    return sorted(fresh, key=item_sort_key, reverse=True)


def assign_ids(section: str, items: list[NewsItem]) -> list[NewsItem]:
    prefix = "I" if section == "india" else "W"
    for index, item in enumerate(items, 1):
        item.item_id = f"{prefix}{index}"
    return items


def normalized_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def normalize_match_text(text: str) -> str:
    text = clean_text(text).lower()
    replacements = {
        r"\blhc\b": "large hadron collider",
        r"\bgrb\b": "gamma ray burst",
        r"\bqw\b": "quantum",
        r"\bai\b": "artificial intelligence",
        r"\bisro\b": "indian space research organisation",
        r"\biisc\b": "indian institute of science",
        r"\btifr\b": "tata institute of fundamental research",
        r"\biit\b": "indian institute of technology",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    return text


def keyword_set(text: str) -> set[str]:
    normalized = normalize_match_text(text)
    words = re.findall(r"[\w-]{4,}", normalized, flags=re.UNICODE)
    stopwords = {
        "about", "after", "from", "have", "into", "that", "their", "this", "with",
        "news", "latest", "today", "google", "india", "indian", "world", "science",
        "physics", "research", "study", "studies", "scientists", "researchers", "says",
        "said", "finds", "found", "could", "first", "new", "update", "updates", "story",
        "stories", "live",
    }
    return {word for word in words if word not in stopwords}


def title_fingerprint(title: str) -> str:
    return " ".join(sorted(keyword_set(title)))


def dedupe_items(items: list[NewsItem]) -> list[NewsItem]:
    result: list[NewsItem] = []
    seen_urls: set[str] = set()
    seen_keys: set[str] = set()
    for item in items:
        url_key = normalized_url(item.url)
        title_key = title_fingerprint(item.title)
        if url_key in seen_urls or title_key in seen_keys:
            continue
        seen_urls.add(url_key)
        seen_keys.add(title_key)
        result.append(item)
    return result


def related_titles(a: str, b: str) -> bool:
    left = keyword_set(a)
    right = keyword_set(b)
    if not left or not right:
        return False
    overlap = len(left & right)
    return overlap >= 3 and overlap / min(len(left), len(right)) >= 0.55


def group_related_items(items: list[NewsItem]) -> list[list[NewsItem]]:
    groups: list[list[NewsItem]] = []
    for item in items:
        matched_group = None
        for group in groups:
            if any(related_titles(item.title, existing.title) for existing in group):
                matched_group = group
                break
        if matched_group is None:
            groups.append([item])
        else:
            matched_group.append(item)
    return groups


def keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword and keyword in text)


def unique_sources(group: list[NewsItem]) -> set[str]:
    return {clean_text(item.source).lower() for item in group if clean_text(item.source)}


def recency_score(group: list[NewsItem]) -> int:
    newest = max((item.published_at for item in group if item.published_at), default=None)
    if not newest:
        return 0
    age = datetime.now(timezone.utc) - newest.astimezone(timezone.utc)
    if age <= timedelta(hours=6):
        return 2
    if age <= timedelta(hours=12):
        return 1
    return 0


def score_story_group(group: list[NewsItem], settings: dict) -> tuple[int, list[str]]:
    if not group:
        return 0, []
    section = group[0].section
    text = " ".join(f"{item.title} {item.source}" for item in group).lower()
    score = 0
    reasons: list[str] = []
    source_boost = min(4, max((max(0, item.source_weight) for item in group), default=1))
    score += source_boost
    reasons.append(f"source weight +{source_boost}")

    if section == "india":
        india_hits = keyword_hits(text, section_keywords("india", settings))
        if india_hits:
            boost = min(6, india_hits * 2)
            score += boost
            reasons.append(f"India physics +{boost}")
        else:
            score -= 2
            reasons.append("weak India match -2")
    else:
        world_hits = keyword_hits(text, section_keywords("world", settings))
        if world_hits:
            boost = min(5, world_hits)
            score += boost
            reasons.append(f"world physics +{boost}")

    public_hits = keyword_hits(
        text,
        configured_keywords(
            settings,
            "research_keywords",
            (
                "discovery,experiment,measurement,observed,detected,breakthrough,research,"
                "quantum,particle,condensed matter,materials,astronomy,astrophysics,cosmology,"
                "nuclear,plasma,photonics,superconduct,semiconductor,neutrino,gravitational wave"
            ),
        ),
    )
    if public_hits:
        boost = min(6, public_hits * 2)
        score += boost
        reasons.append(f"research value +{boost}")

    classroom_hits = keyword_hits(
        text,
        configured_keywords(
            settings,
            "classroom_keywords",
            "explain,student,education,lecture,nobel,olympiad,demonstration,concept,experiment,measurement",
        ),
    )
    if classroom_hits:
        boost = min(3, classroom_hits)
        score += boost
        reasons.append(f"classroom value +{boost}")

    if len(group) > 1:
        boost = min(3, len(group) - 1)
        score += boost
        reasons.append(f"related headlines +{boost}")
    if len(unique_sources(group)) > 1:
        score += 2
        reasons.append("multiple sources +2")

    freshness = recency_score(group)
    if freshness:
        score += freshness
        reasons.append(f"freshness +{freshness}")

    low_value_hits = keyword_hits(
        text,
        configured_keywords(settings, "low_value_keywords", "campus diary,opinion,editorial,celebrity,entertainment,promotion,launch offer,poster,trailer"),
    )
    if low_value_hits:
        penalty = min(6, low_value_hits * 3)
        score -= penalty
        reasons.append(f"low value -{penalty}")
    if len(keyword_set(text)) <= 2:
        score -= 2
        reasons.append("vague headline -2")
    return score, reasons


def select_top_story_groups(section: str, items: list[NewsItem], settings: dict) -> list[list[NewsItem]]:
    groups = group_related_items(items)
    scored = []
    for group in groups:
        score, _ = score_story_group(group, settings)
        newest = max((item.published_at.timestamp() for item in group if item.published_at), default=0.0)
        scored.append((score, newest, group))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    max_groups = int(settings.get("max_groups_per_section", 8))
    min_score = int(settings.get("min_group_score", 2))
    selected = [group for score, _, group in scored if score >= min_score][:max_groups]
    if not selected:
        selected = [group for _, _, group in scored[:max_groups]]
    return selected


def readable_title(text: str) -> str:
    text = clean_text(text)
    letters = [char for char in text if char.isalpha()]
    if letters and sum(char.isupper() for char in letters) / len(letters) > 0.82:
        small_words = {"a", "an", "and", "as", "at", "for", "from", "in", "of", "on", "or", "the", "to"}
        words = text.lower().split()
        return " ".join(word if index > 0 and word in small_words else word[:1].upper() + word[1:] for index, word in enumerate(words))
    return text


def plain_text(markdown: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", markdown)
    text = re.sub(r"[*_`#>~]+", "", text)
    text = re.sub(r"\[[A-Z]\d+\]", "", text)
    return clean_text(text)


def clean_title(value: str) -> str:
    title = plain_text(value).strip(" .,:;-")
    return title[:80].rstrip(" ,;:") if title else "Physics Brief"


def clean_summary(value: str) -> str:
    summary = plain_text(value).strip(" .,:;-")
    return summary[:157].rstrip() + "..." if len(summary) > 160 else summary


def split_digest_header(summary: str) -> tuple[str, str, str]:
    lines = summary.splitlines()
    remaining: list[str] = []
    title = ""
    teaser = ""
    for line in lines:
        match = re.match(r"^TITLE\s*:\s*(.+)$", line.strip(), flags=re.I)
        if match and not title:
            title = clean_title(match.group(1))
            continue
        summary_match = re.match(r"^SUMMARY\s*:\s*(.+)$", line.strip(), flags=re.I)
        if summary_match and not teaser:
            teaser = clean_summary(summary_match.group(1))
            continue
        remaining.append(line)
    return title or "Physics News Brief", teaser, "\n".join(remaining).strip()


def split_digest_title(summary: str) -> tuple[str, str]:
    title, _, body = split_digest_header(summary)
    return title, body


def generic_title(title: str) -> bool:
    normalized = clean_text(title).lower()
    return normalized in {
        "physics brief", "physics news brief", "daily physics news brief", "india and world physics brief",
    }


def item_map(items: list[NewsItem]) -> dict[str, NewsItem]:
    return {item.item_id: item for item in items}


def extract_source_ids(text: str) -> tuple[str, list[str]]:
    source_ids = [match.upper() for match in re.findall(r"\[([IW]\d+)\]", text, flags=re.I)]
    text = re.sub(r"\s*Sources?:\s*(?:\[[IW]\d+\]\s*,?\s*)+$", "", text, flags=re.I)
    text = re.sub(r"\s*(?:\[[IW]\d+\]\s*)+$", "", text, flags=re.I)
    return clean_text(text), source_ids


def infer_source_ids(text: str, items: list[NewsItem], section: str, limit: int = 2) -> list[str]:
    text_words = keyword_set(plain_text(text))
    if not text_words:
        return []
    scored = []
    for item in items:
        if item.section != section:
            continue
        overlap = len(text_words & keyword_set(item.title))
        if overlap:
            scored.append((overlap, item.item_id))
    scored.sort(reverse=True)
    return [item_id for _, item_id in scored[:limit]]


def source_relevance_score(text: str, item: NewsItem) -> int:
    bullet_words = keyword_set(plain_text(text))
    title_words = keyword_set(item.title)
    return len(bullet_words & title_words)


def validate_source_ids(text: str, source_ids: list[str], lookup: dict[str, NewsItem], section: str) -> list[str]:
    valid: list[str] = []
    for source_id in source_ids:
        item = lookup.get(source_id)
        if not item or item.section != section:
            continue
        if source_relevance_score(text, item) >= 1:
            valid.append(source_id)
    return valid


def headline_without_source(item: NewsItem) -> str:
    title = clean_text(item.title)
    source = clean_text(item.source)
    if source:
        title = re.sub(rf"\s+-\s*{re.escape(source)}$", "", title, flags=re.I)
    return title


def story_topic(group: list[NewsItem]) -> str:
    text = " ".join(headline_without_source(item) for item in group).lower()
    topic_rules = [
        ("quantum research", ("quantum", "qubit", "entanglement", "superposition")),
        ("space science", ("isro", "nasa", "esa", "mission", "satellite", "telescope", "space")),
        ("astronomy", ("astronomy", "astrophysics", "cosmology", "galaxy", "exoplanet", "black hole")),
        ("particle physics", ("particle", "cern", "lhc", "neutrino", "muon", "boson", "detector")),
        ("materials physics", ("material", "condensed matter", "semiconductor", "superconduct", "photonics")),
        ("nuclear and plasma physics", ("nuclear", "fusion", "plasma", "reactor")),
        ("research policy", ("funding", "policy", "facility", "collaboration", "institute")),
        ("physics education", ("student", "education", "lecture", "olympiad", "classroom")),
    ]
    for label, keywords in topic_rules:
        if any(keyword in text for keyword in keywords):
            return label
    return ""


def join_summary_topics(topics: list[str]) -> str:
    clean_topics = [topic for topic in topics if topic]
    if not clean_topics:
        return "Daily physics news for classroom and research awareness"
    if len(clean_topics) == 1:
        return f"{clean_topics[0].capitalize()} for physics students and research awareness"
    if len(clean_topics) == 2:
        return f"{clean_topics[0].capitalize()} and {clean_topics[1]} for physics students"
    return f"{', '.join(clean_topics[:-1]).capitalize()}, and {clean_topics[-1]} for physics students"


def fallback_home_summary(items: list[NewsItem], points_total: int, settings: dict) -> str:
    topics: list[str] = []
    max_points = min(5, points_total)
    for section in ("india", "world"):
        section_items = [item for item in items if item.section == section]
        groups = group_related_items(section_items)
        groups.sort(key=lambda group: score_story_group(group, settings)[0], reverse=True)
        for group in groups[:max_points]:
            topic = story_topic(group)
            if topic and topic.lower() not in {existing.lower() for existing in topics}:
                topics.append(topic)
            if len(topics) >= 4:
                return join_summary_topics(topics)
    return join_summary_topics(topics) if topics else "Daily physics news for classroom and research awareness"
