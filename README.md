# Physics Brief

Daily English physics-news brief for classroom sharing and research-direction awareness.

The project collects configurable RSS feeds, filters for fresh physics items, groups duplicates, scores stories before the AI call, asks Gemini for a concise digest, and writes a Jekyll Markdown post under `docs/_posts/`.

## Output

- `India Physics`: Indian physics, space science, institutions, policy, and research signals
- `World Physics`: global research news from physics-focused sources
- The final post lists at most five points total. If there are not enough worthwhile stories, it shows fewer.
- Each point keeps source chips that link back to the supporting article/feed item.

## Local Run

Create `.env` locally:

```bash
PHYSICS_API_KEY=your_gemini_key_here
# Optional override. The default is gemini-3.1-flash-lite.
GEMINI_MODEL=gemini-3.1-flash-lite
```

Generate:

```bash
./run.sh generate
```

Run without Gemini:

```bash
./run.sh no-ai
```

Preview locally:

```bash
./run.sh serve
```

## Sources

Edit:

```text
config/sources.yml
```

Add a source under `india` or `world`:

```yml
- name: Example Physics Source
  type: rss
  weight: 3
  url: "https://example.com/rss.xml"
```

Useful tuning settings:

```yml
final_points_total: 5
max_groups_per_section: 8
min_group_score: 2
require_ist_today: true
max_age_hours: 36
india_keywords: "india,indian,isro,iit,iisc,tifr"
world_keywords: "physics,quantum,particle,cosmology,astrophysics"
research_keywords: "discovery,experiment,measurement,quantum,neutrino"
classroom_keywords: "student,education,concept,experiment,measurement"
exclude_keywords: "astrology,horoscope,photo gallery,celebrity"
```

Before Gemini runs, the script filters old and irrelevant items, removes excluded topics, groups similar headlines, scores each group, and sends only the top `max_groups_per_section` groups per section. URLs are kept locally for source links but are not sent to Gemini.

## GitHub Deployment

1. Push this folder as the root of a repo named `physics-news`.
2. Add a GitHub Actions repository secret:

```text
PHYSICS_API_KEY
```

3. In GitHub Pages settings, set source to `GitHub Actions`.

The site is configured for:

```text
/physics-news
```

## Schedule

The workflow runs at:

- 06:00 IST
- 14:00 IST
- 20:00 IST

Each successful run commits the generated post into `docs/_posts/` and deploys GitHub Pages.
