---
name: ytm-competitors
description: >-
  Research and track 10+ gaming competitor channels in the channel's niche (PS5 4K campaign walkthroughs,
  no commentary) and find what is outperforming. Use for "competitors", "what's working", "who else
  does this", "find viral videos in my niche", "research the niche".
---

# ytm-competitors

Engine: `py ytm.py` (run from the repo root) (below: `YTM`). Ranking: `~/.claude/skills/yt-viral/swipe.py`.
Official YouTube Data API only (public data; never scraping, never another account).

```bash
YTM competitors discover "<query>" "<query>" ...   # channels ranked by search hits (100 quota units/query)
YTM competitors add <channel_id|@handle> --why "<reason>"
YTM competitors remove <channel_id>
YTM competitors list                               # tracked: config/competitors.json
YTM competitors scan --recent 15                   # last N uploads of each + outliers + tags
```

## Keep at least 10 tracked, and the right ones

- Same format first: no-commentary / cinematic campaign walkthroughs, PS5 / 4K HDR.
- A mix of sizes: 2-3 benchmarks (1M+), most mid-size, and 2-3 peers near the channel's size -
  peers are the most useful, their outliers are reachable.
- Exclude publishers (PlayStation, IGN, GameSpot), news/review channels, and commentary
  personalities unless kept as a labelled benchmark.
- When the user moves to a new game, run `discover` with that game's queries and add peers.

## Reading a scan

Saved to `data/competitors/report-<date>.json`. Report:
1. Top outliers by **multiple of the channel's own median** (not raw views) with the formula.
2. The ONE pattern the outliers share (format, length, title shape, timing vs game release).
3. Profile table: subs, uploads/week, median long vs Shorts views, Shorts share.
4. Tags competitors use that the channel's game profiles lack -> suggest additions to games.json.
5. What the channel could make this week from footage it already has.

Say clearly that the formula label is a judgement about the title, not proof of why it worked.
