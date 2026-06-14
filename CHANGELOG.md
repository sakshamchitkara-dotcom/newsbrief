# Changelog

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
