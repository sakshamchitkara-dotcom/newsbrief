# newsbrief

Collects the day's news from RSS/Atom feeds, Hacker News and (optionally) scraped
section pages, merges near-duplicate stories across outlets, ranks them, summarizes
them with Claude (or an extractive fallback), and emails each subscriber a
responsive HTML brief at their own local send time.

<p align="center">
  <img src="docs/brief-mobile.png" width="300" alt="A real brief rendered at phone width">
</p>

Full-page desktop render of a real run: [docs/brief-desktop.png](docs/brief-desktop.png).

## How it works

```
sources ──► collect ──► cluster ──► rank ──► filter ──► summarize ──► render ──► deliver
 rss/atom    parallel,   shingles +   recency,  already-   Claude Opus   HTML +     SMTP / Resend /
 hackernews  robots.txt  idf-weighted source    sent,      5.5, or       plain      SendGrid, or
 page        respected   Jaccard      weight,   lookback,  extractive    text       --dry-run outbox
                                      coverage  per-topic
                                                cap
```

| Step | Module | Notes |
|---|---|---|
| Sources | `feeds.py`, `hn.py`, `scrape.py` | RSS 2.0, RSS 1.0 (RDF) and Atom via `xml.etree`; the official HN API; `page` sources scrape headline links from a section page. Tracking params (`utm_*`, `at_medium`, ...) are stripped. |
| Article text | `extract.py` | Fetches each chosen story's page, respecting `robots.txt`, and keeps the parent element holding the most paragraph text. |
| Dedupe | `dedupe.py` | Exact URL dedupe, then leader clustering: cross-outlet 3-word shingle Jaccard (syndicated copy), or idf-weighted keyword Jaccard over title + lede (rewrites of the same event). Phrases an outlet repeats across items ("Get our breaking news email...") are stripped first, and live blogs never lead a story. |
| Ranking | `rank.py` | `recency (12h half-life) × source weight × (1 + log2 outlets) × HN popularity`, then a per-topic cap so one busy beat can't fill the brief. |
| State | `state.py` | SQLite: URLs already sent to each subscriber (so tomorrow's brief doesn't repeat them), deliveries per local day, unsubscribes. |
| Summaries | `summarize.py` | `claude-opus-5-5` via `messages.parse` with a Pydantic schema (headline, summary, why it matters, intro), `effort: medium`. Falls back to extractive summaries with no API key, a refusal, truncation or any API error. |
| Email | `render.py`, `deliver.py`, `unsubscribe.py` | Table layout with inline CSS and a text/plain alternative. HMAC unsubscribe link, `List-Unsubscribe` and one-click `List-Unsubscribe-Post` headers. |

## Quick start

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e '.[claude]'          # drop [claude] for extractive-only
cp newsbrief.example.yaml newsbrief.yaml   # add yourself under subscribers
cp .env.example .env                        # fill in what you need
set -a; . ./.env; set +a

newsbrief check                 # validate config, show who gets which sources
newsbrief run --dry-run         # build briefs into ./outbox/*.eml + *.html, send nothing
open outbox/*.html
newsbrief run                   # really send (needs a transport, see below)
```

Only addresses listed under `subscribers:` ever receive email. `--dry-run` never sends
and never writes sent-story state, so a dry run doesn't hide stories from the next real run.

## Configuration

`newsbrief.yaml` (or `.json`). See [`newsbrief.example.yaml`](newsbrief.example.yaml).

```yaml
from_email: "The Daily Brief <brief@example.com>"
base_url: "https://brief.example.com"   # where `newsbrief serve` is reachable; "" = mailto-only unsubscribe
max_stories: 12
max_per_topic: 5
lookback_hours: 36
sources:
  bbc-world: {type: rss, url: "https://feeds.bbci.co.uk/news/world/rss.xml", weight: 1.3, topics: [world]}
  hn:        {type: hackernews, url: topstories, limit: 30, weight: 0.9, topics: [tech]}
  npr-sci:   {type: page, url: "https://www.npr.org/sections/science/", topics: [science]}
subscribers:
  - email: you@example.com
    name: You
    timezone: Europe/London     # any IANA zone
    send_at: "07:00"            # local time
    topics: [world, tech]       # optional filter
    sources: [bbc-world, hn]    # optional filter
    max_stories: 8              # optional override
```

### Environment

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude summaries (optional) |
| `NEWSBRIEF_SECRET` | Key for unsubscribe tokens. **Set this for real sends.** |
| `NEWSBRIEF_TRANSPORT` | `smtp`, `resend` or `sendgrid`. Otherwise picked from whichever of the variables below is set. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` | SMTP. Port 587 uses STARTTLS, 465 uses implicit TLS. |
| `RESEND_API_KEY` / `SENDGRID_API_KEY` | HTTP email APIs |

## Scheduling

Each subscriber gets one brief per local day, on the first run after their `send_at`.

- **Once**: `newsbrief run --only-due` from any scheduler.
- **Long-running**: `newsbrief schedule --interval 300` (reloads config on every tick).
- **cron**: [`deploy/crontab.example`](deploy/crontab.example).
- **launchd (macOS)**: [`deploy/com.newsbrief.schedule.plist`](deploy/com.newsbrief.schedule.plist).
- **GitHub Actions**: [`.github/workflows/brief.yml`](.github/workflows/brief.yml) runs hourly once you set the repo
  variable `NEWSBRIEF_ENABLED=true`. The config lives in the `NEWSBRIEF_CONFIG` secret, so subscriber
  addresses stay out of the repo. The SQLite state is carried between runs in the Actions cache.
  A manual dispatch defaults to a dry run and uploads the outbox as an artifact.

## Unsubscribing

Every email has an unsubscribe link and `List-Unsubscribe` header, signed with `NEWSBRIEF_SECRET`.

- `newsbrief serve --port 8025` serves `/unsubscribe`. Put it behind TLS and set `base_url`.
  A GET only shows a confirmation button, so mail scanners that follow links can't unsubscribe
  anyone. The POST (also used by RFC 8058 one-click) records the unsubscribe.
- `newsbrief unsubscribe EMAIL TOKEN` does the same from the shell, for example for mailto requests.

## Real output

A dry run against the example config's live feeds (BBC World and Business, NPR, Guardian,
Al Jazeera, The Verge, Ars Technica, HN) on 2026-09-25. No API key was set, so it used
the extractive summaries:

```
$ newsbrief run --dry-run
INFO newsbrief.pipeline: aljazeera       25 items
INFO newsbrief.pipeline: verge           10 items
INFO newsbrief.pipeline: ars             20 items
INFO newsbrief.pipeline: npr             10 items
INFO newsbrief.pipeline: bbc-business    30 items
INFO newsbrief.pipeline: guardian        30 items
INFO newsbrief.pipeline: bbc-world       30 items
INFO newsbrief.pipeline: hn              30 items
you@...: 12 stories via outbox -> outbox/you-...-2026-09-25.html
```

An excerpt of the text/plain part:

```
THE DAILY BRIEF - Friday, September 25, 2026
============================================

Good morning, Saksham. 12 stories today across world, tech, business.

## WORLD

* Trump and Xi exchange warm words at state dinner but little progress on
key issues
  The two superpowers seek greater dialogue despite differences over issues
  such as Iran, Taiwan, AI and trade.
  - bbc-world: https://www.bbc.co.uk/news/articles/cxq63dqp93n1o
  - aljazeera: https://www.aljazeera.com/news/2026/9/25/trump-praises-us-china-friendship-at-state-dinner-with-xi-jinping

* Four civilians killed in Pakistani strikes in Afghanistan, Taliban says
  Pakistan says it struck 10 targets, adding the strikes were "strictly
  limited to identified military objectives".
  - bbc-world: https://www.bbc.co.uk/news/articles/cm86xn0nnw58o
  - aljazeera: https://www.aljazeera.com/news/2026/9/25/pakistani-forces-kill-afghan-taliban-fighters-in-border-escalation

## TECH

* F-Droid gets its biggest update in a decade with new UI and smoother app
installs
  ...
  - ars: https://arstechnica.com/gadgets/2026/09/f-droid-gets-its-biggest-update-in-a-decade-with-new-ui-and-smoother-app-installs/
  - hn: https://f-droid.org/2026/09/24/f-droid-2.0-a-new-chapter-for-android-freedom.html
    discussion (1206 pts): https://news.ycombinator.com/item?id=49831968
```

On that day's 185 items, clustering merged same-event coverage across outlets, including
BBC/Al Jazeera, BBC/Guardian, BBC/NPR, Guardian/Al Jazeera, Ars/BBC and Ars/HN pairs.

### Known limits

- Keyword clustering still makes mistakes. On the day above it merged two different
  Rails posts from HN and missed a Guardian/Guardian pair about the same Medicare hack.
- Some sites block scripted fetches (NPR answered `402`). Those stories fall back to the feed blurb.
- Pairwise clustering is O(n × clusters), which is fine for a few hundred items a day.
  Beyond that, switch to MinHash LSH.

## Development

```sh
pip install -e '.[dev,claude]'
pytest -q        # local fixtures only; a conftest guard fails any test that touches the network
```

MIT licensed.
