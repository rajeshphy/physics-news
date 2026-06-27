# Physics Brief `src` package

This `src` folder splits the earlier single-file generator into small modules while keeping the same project role: fetch configured RSS feeds, filter physics-relevant items, summarize them, and write a Jekyll post under `docs/_posts`.

## Files

- `main.py` — command-line entry point.
- `common.py` — shared constants, paths, dataclass, environment loader, and small YAML parser.
- `fetch.py` — RSS/Atom fetching and `NewsItem` collection.
- `directlink.py` — resolves RSS/search/redirect URLs to direct article URLs using redirects plus canonical/`og:url` extraction.
- `filter.py` — freshness, relevance, deduplication, grouping, scoring, source-id parsing, and title helpers.
- `ai.py` — Gemini prompt, quota handling, AI summary, and fallback summary.
- `markdown.py` — converts summary/source IDs into the final Jekyll Markdown/HTML post.
- `__init__.py` — package marker.

## Direct-link behavior

RSS feeds often provide indirect links. `fetch.py` now calls `resolve_direct_link()` from `directlink.py` for every RSS/Atom item before it is stored. This means the generated post source chips and the “Headlines considered” list use the resolved direct article URL wherever the source allows it.

## Run

From the repository root:

```bash
python src/main.py
```

To skip Gemini and use the fallback digest:

```bash
python src/main.py --no-ai
```
