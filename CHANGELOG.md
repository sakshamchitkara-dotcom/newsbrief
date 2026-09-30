# Changelog

## 0.4.0 - 2026-09-25

### Added
- Dark mode: the email declares `color-scheme: light dark` and recolours itself under
  `prefers-color-scheme: dark` (Apple Mail, iOS Mail, Outlook for Mac, Thunderbird). Clients that
  strip `<style>` still get the light email. Archive pages follow the viewer's theme.

### Fixed
- Weekly digest: a story one brief carried as two stories is one thread once a later brief
  continues both (stored 2026-09-25 brief, Trump/Xi split in two the day before: 13 -> 12 threads).
- A real `run`/`digest` with no email transport fetched every feed and paid for summaries before
  failing; the transport is now checked first. `NEWSBRIEF_TRANSPORT` is case-insensitive and a
  typo lists the valid values.
- A Hacker News story list that wasn't JSON (an HTML error page) or was `null` crashed the whole
  run instead of skipping that source.

### Changed
- Tests for SMTP implicit TLS and failures, SendGrid and API errors, `fetch_hn`, article
  enrichment, `post_json`, and the `serve`/`digest`/`audio` commands (141 -> 157 tests).

## 0.3.1 - 2026-09-25

### Fixed
- Weekly digest: a reworded developing story no longer splits into two threads. Threads are linked
  day by day using the daily tracker's own link, shared article URLs, or the clustering test over
  the stored articles; stories from the same day are never merged.
- HTML `<title>` uses the brief's title ("The Weekly Brief") instead of always "Your news brief".

### Changed
- README screenshots regenerated from a live dry run.

## 0.3.0 - 2026-09-25

### Added
- Developing stories: each brief is matched against the subscriber's briefs from the past 7 days;
  a continuing story gets a "Day N" badge and "Following since ... Previously: ...", linked to
  the earlier day on archive pages.
- `newsbrief digest`: weekly roundup rebuilt from stored briefs, for subscribers with `weekly: true`.
- `newsbrief audio`: podcast-style audio of a stored brief via macOS `say` (`--voice`, `--rate`,
  `--script-only`).
- `newsbrief archive --site-url`: Atom `feed.xml`; `brief.yml` deploys the archive to GitHub Pages
  when `NEWSBRIEF_PAGES=true`.
- `newsbrief eval --snapshot FILE`: capture today's feeds as a pre-labeled set for hand-labeling.
- `check --feeds --probe N`: probes 3 article pages per feed by default instead of 1.

### Fixed
- Clustering recall on big stories: names are recognised at sentence starts, in Title Case and as
  two-letter names ("Xi"), and two rare names shared by both headlines merge a story. A first and
  last name ("Elon Musk") count as one name.
- A developing story vanished from the next day's brief once any of its articles had been sent;
  now only the sent articles are dropped.
- Video clips no longer lead a story, and a story's links, Claude prompt and extra text fetch
  cover other outlets before repeating the lead's.
- Feed blurbs with a standfirst paragraph ran into the next sentence; inline links added a space
  before punctuation in blurbs and article text.
- Config: unknown top-level and source keys, or a source that isn't a mapping, are config errors
  instead of tracebacks; `mute: celebrity` is a one-item list instead of its letters.
- Blank `mute`/`boost` terms muted or boosted every story; terms like "C++" never matched.
- robots.txt is re-read every 6 hours instead of cached for the life of `newsbrief schedule`.

### Changed
- Eval on the 2026-09-25 set: precision 0.955 -> 0.955, recall 0.226 -> 0.677 (f1 0.365 -> 0.792).

## 0.2.0 - 2026-09-25

### Added
- `newsbrief eval`: pairwise precision/recall/F1 of story clustering against a labeled set of
  180 real feed items from 2026-09-25 (shipped as package data), listing false merges and misses.
- Named-entity overlap signal in clustering: shared names (words capitalised mid-sentence,
  acronyms) merge rewritten headlines of one event.
- Per-source `fetch_text: false` to keep feed blurbs for sites that block article fetches
  (set for NPR in the example config).
- HTTP retries with backoff for 429/5xx (honouring `Retry-After`) and a per-domain circuit
  breaker: 401/402/403/451 skip the domain for an hour, three failures in a row for five minutes.
- Per-subscriber `topic_weights`, `boost` and `mute`.
- Reading time per story when its article text was fetched.
- "Why it matters" line on the top story: Claude writes it, with an extractive fallback. Every
  outlet's article is fetched for the top story to give it more to draw on.
- `newsbrief archive`: static HTML site of past briefs (index + one page per day, `.nojekyll`),
  with no subscriber data. Briefs are stored in the state db on every run.
- `newsbrief subscribers list|add|remove`, validating timezone, send time, topics and sources.
- `newsbrief check --feeds`: per-feed status (OK/STALE/EMPTY/FAIL), item count, newest item age
  and article-fetch access; exits 3 when a feed is unhealthy.
- CI prints `newsbrief eval` results.

### Fixed
- Clustering merged unrelated posts that shared a single keyword ("What About Rails?" and
  "Rails World 2026 Opening Keynote"). Keyword merges now need two shared keywords, and the
  thin-title rule only applies across outlets.
- Clustering missed the Guardian's live blog and news piece on the OpenAI Medicare hack.
- Config: duplicate subscribers, unknown topics (in `topics` or `topic_weights`) and unknown
  subscriber keys are now errors instead of silently empty briefs or a bare `TypeError`.
- The extractive "why it matters" line no longer picks tangents or sentences starting "But ...".

### Changed
- Claude is asked for "why it matters" on the top story only.
- Eval on the 2026-09-25 set: precision 0.933 -> 0.955, recall 0.151 -> 0.226.

## 0.1.0 - 2026-09-25

First release: RSS/Atom/RDF, Hacker News and page sources; shingle + keyword clustering;
recency/weight/coverage ranking with a per-topic cap; Claude or extractive summaries; responsive
HTML + text email via SMTP, Resend or SendGrid; per-subscriber local send times; HMAC
unsubscribe links with an RFC 8058 one-click endpoint; `NEWSBRIEF_SECRET` required for real
sends and `serve`.
