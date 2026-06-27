from __future__ import annotations

import html
import re
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PhysicsBrief/1.0; +https://github.com/rajeshphy/physics-news)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "igshid",
}


WRAPPER_PARAMS = (
    "url",
    "u",
    "target",
    "link",
    "q",
    "redirect",
    "redirect_url",
    "destination",
    "dest",
    "to",
)


def clean_url(url: str) -> str:
    url = html.unescape((url or "").strip())

    if not url:
        return ""

    parsed = urllib.parse.urlparse(url)

    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if k.lower() not in TRACKING_PARAMS]

    return urllib.parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urllib.parse.urlencode(query),
            "",
        )
    )


def is_feed_like_url(url: str) -> bool:
    lowered = url.lower()

    feed_markers = (
        "/rss",
        "rss.",
        "rss?",
        "/feed",
        "feed.",
        "feeds.",
        "feedburner",
        "atom.xml",
        "rss.xml",
        "news.google.com/rss",
    )

    return any(marker in lowered for marker in feed_markers)


def is_http_url(url: str) -> bool:
    return url.startswith(("http://", "https://"))


def extract_wrapped_url(url: str) -> str:
    """
    Return real target from common RSS/search/news wrapper parameters.
    Example:
    https://example.com/redirect?url=https%3A%2F%2Freal-site.com%2Farticle
    """
    url = clean_url(url)

    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)

    for key in WRAPPER_PARAMS:
        values = params.get(key)

        if not values:
            continue

        candidate = html.unescape(values[0]).strip()
        candidate = urllib.parse.unquote(candidate)

        if is_http_url(candidate):
            return clean_url(candidate)

    return url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_url(url: str, *, method: str = "GET", timeout: int = 20):
    request = urllib.request.Request(url, headers=HEADERS, method=method)
    return urllib.request.urlopen(request, timeout=timeout)


def follow_redirects_head(url: str, max_hops: int = 6) -> str:
    """
    Manual redirect following using HEAD.
    Fast, but some websites block HEAD.
    """
    current = extract_wrapped_url(url)
    opener = urllib.request.build_opener(NoRedirect)

    for _ in range(max_hops):
        try:
            request = urllib.request.Request(current, headers=HEADERS, method="HEAD")
            response = opener.open(request, timeout=15)
            response.close()
            break

        except urllib.error.HTTPError as exc:
            if exc.code not in {301, 302, 303, 307, 308}:
                break

            location = exc.headers.get("Location")

            if not location:
                break

            next_url = urllib.parse.urljoin(current, location)
            next_url = extract_wrapped_url(next_url)

            if next_url == current:
                break

            current = next_url

        except Exception:
            break

    return clean_url(current)


def follow_redirects_get(url: str) -> str:
    """
    Follow redirect using normal GET.
    Slower, but works for many sites that block HEAD.
    """
    url = extract_wrapped_url(url)

    try:
        with request_url(url, method="GET", timeout=20) as response:
            resolved = response.geturl() or url
            return clean_url(extract_wrapped_url(resolved))

    except Exception:
        return clean_url(url)


def extract_canonical_or_og_url(page_url: str, html_text: str) -> str:
    patterns = [
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']canonical["\']',
        r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:url["\']',
    ]

    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.I)

        if not match:
            continue

        candidate = html.unescape(match.group(1)).strip()
        candidate = urllib.parse.urljoin(page_url, candidate)
        candidate = clean_url(candidate)

        if is_http_url(candidate):
            return candidate

    return ""


def extract_article_link_from_html(page_url: str, html_text: str) -> str:
    """
    Fallback for pages like Google News / feed wrappers.
    Tries to find the first non-feed external article URL inside HTML.
    """
    parsed_page = urllib.parse.urlparse(page_url)
    page_domain = parsed_page.netloc.lower()

    candidates = re.findall(r'https?://[^"\'>\s]+', html_text)

    for candidate in candidates:
        candidate = html.unescape(candidate)
        candidate = urllib.parse.unquote(candidate)
        candidate = clean_url(candidate)

        if not is_http_url(candidate):
            continue

        parsed_candidate = urllib.parse.urlparse(candidate)
        candidate_domain = parsed_candidate.netloc.lower()

        if not candidate_domain:
            continue

        if candidate_domain == page_domain:
            continue

        if is_feed_like_url(candidate):
            continue

        if "google.com" in candidate_domain and "news.google.com" in page_domain:
            continue

        return candidate

    return ""


def canonical_from_html(url: str) -> str:
    """
    Fetch final page and prefer canonical/og:url where present.
    """
    head_url = follow_redirects_head(url)
    get_url = follow_redirects_get(head_url)

    final_url = get_url or head_url or url

    try:
        with request_url(final_url, method="GET", timeout=20) as response:
            resolved = response.geturl() or final_url
            ctype = response.headers.get("content-type", "")

            raw = response.read(400_000)

            if "html" not in ctype.lower():
                return clean_url(extract_wrapped_url(resolved))

            charset = "utf-8"
            match = re.search(r"charset=([\w.-]+)", ctype, flags=re.I)

            if match:
                charset = match.group(1)

            text = raw.decode(charset, errors="replace")

    except Exception:
        return clean_url(final_url)

    resolved = clean_url(extract_wrapped_url(resolved))

    canonical = extract_canonical_or_og_url(resolved, text)

    if canonical and not is_feed_like_url(canonical):
        return canonical

    article_link = extract_article_link_from_html(resolved, text)

    if article_link and not is_feed_like_url(article_link):
        return article_link

    return clean_url(resolved)


@lru_cache(maxsize=512)
def resolve_direct_link(url: str) -> str:
    """
    Return direct article URL instead of RSS/search/feed redirect URL whenever possible.
    """
    if not url:
        return ""

    original = clean_url(url)
    unwrapped = extract_wrapped_url(original)

    resolved = canonical_from_html(unwrapped)

    if resolved and not is_feed_like_url(resolved):
        return resolved

    if unwrapped and not is_feed_like_url(unwrapped):
        return unwrapped

    return original
