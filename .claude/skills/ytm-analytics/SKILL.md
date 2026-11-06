---
name: ytm-analytics
description: >-
  Track the channel's performance and organic growth from YouTube Analytics - period-over-period growth,
  organic vs paid, Shorts vs long-form, top videos, retention of a single video. Use for "how is the
  channel doing", "analytics", "growth", "stats", "why did views drop", "retention of <video>".
---

# ytm-analytics

Engine: `py ytm.py` (run from the repo root) (below: `YTM`). Retention reading: `/yt-retention`.

```bash
YTM analytics report [--days 28]        # this period vs the previous one (+ saves a snapshot)
YTM analytics snapshot                  # snapshot only -> data/analytics/<date>.json
YTM analytics retention <video_id>      # API retention curve -> CSV -> retention.py report
```

Analytics data lags ~2 days; periods end 2 days ago. Snapshots accumulate, so growth since the
first snapshot is tracked over time (run a report at least weekly).

## Organic growth - read it honestly

- **Organic share** = views not from `ADVERTISING`. Paid views inflate totals and wreck average
  view percentage (ads bring viewers who leave in seconds). Always report organic separately.
- **Net subscribers** = gained - lost. Views up while subscribers down usually means the views
  came from Shorts or ads, not from viewers who want more.
- **Format split**: Shorts vs long-form views. Shorts feed growth that does not convert to
  long-form watch time is the common trap for gameplay channels.
- Traffic: `SHORTS`, `YT_SEARCH` (titles/descriptions working), `RELATED_VIDEO`/`SUGGESTED`
  (packaging + retention working), `SUBSCRIBER`.

## Report format

1. Headline numbers with % change: views, watch time, net subs, avg % viewed - organic share.
2. The ONE thing driving the change (a video, a traffic source, a format).
3. Top 5 videos: views, avg % viewed, format.
4. One action for next week, tied to the pipeline (e.g. "location-reveal Shorts are the
   winner - next recording, `/ytm-shorts` should look for those").
Never invent a number - every figure comes from the report JSON.
