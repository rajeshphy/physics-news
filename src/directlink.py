from __future__ import annotations

import html
import re
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache


HEADERS = {
    "User-Agent": "PhysicsBrief/1.0 (+https://github.com/rajeshphy/physics-news)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "fbclid", "gclid", "mc_cid", "mc_eid", "igshid", "ref", "source",
}


def clean_url(url: str) -> str:
    url = html.unescape((url or "").strip())
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if k.lower() not in TRACKING_PARAMS]
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urllib.parse.urlencode(query), ""))


def extract_wrapped_url(url: str) -> str:
    """Return the real target from common RSS/search wrapper parameters when present."""
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    for key in ("url", "u", "target", "link", "q"):
        values = params.get(key)
        if values:
            candidate = urllib.parse.unquote(values[0])
            if candidate.startswith(("http://", "https://")):
                return candidate
    return url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request(url: str, *, method: str = "GET", timeout: int = 20):
    request = urllib.request.Request(url, headers=HEADERS, method=method)
    return urllib.request.urlopen(request, timeout=timeout)


def follow_http_redirects(url: str, max_hops: int = 6) -> str:
    current = extract_wrapped_url(clean_url(url))
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
            if next_url == current:
                break
            current = extract_wrapped_url(clean_url(next_url))
        except Exception:
            break
    return clean_url(current)


def canonical_from_html(url: str) -> str:
    """Fetch final page and prefer canonical/og:url links when they are present."""
    final_url = follow_http_redirects(url)
    try:
        with _request(final_url, timeout=20) as response:
            resolved = response.geturl() or final_url
            ctype = response.headers.get("content-type", "")
            if "html" not in ctype.lower():
                return clean_url(resolved)
            raw = response.read(300_000)
            charset = "utf-8"
            match = re.search(r"charset=([\w.-]+)", ctype, flags=re.I)
            if match:
                charset = match.group(1)
            text = raw.decode(charset, errors="replace")
    except Exception:
        return clean_url(final_url)

    patterns = [
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']canonical["\']',
        r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:url["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            candidate = urllib.parse.urljoin(final_url, html.unescape(match.group(1)))
            return clean_url(candidate)
    return clean_url(resolved)


@lru_cache(maxsize=512)
def resolve_direct_link(url: str) -> str:
    """Return a direct article URL instead of RSS/search/feed redirect URL whenever possible."""
    if not url:
        return ""
    return canonical_from_html(url)
