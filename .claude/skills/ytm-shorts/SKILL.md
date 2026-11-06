---
name: ytm-shorts
description: >-
  Create up to fifteen branded vertical YouTube Shorts from a recording - pick self-contained
  moments, write the on-screen hook, render 1080x1920 with the logo watermark. Use for "make Shorts",
  "clip this", "cut this into shorts", or after a long-form edit.
---

# ytm-shorts

Engine: `py ytm.py` (run from the repo root) (below: `YTM`). Needs `/ytm-moments`. Brand: `/ytm-brand`.

```bash
YTM shorts add <job> --start 12:31 --end 13:09 --hook "He never saw it coming" [--layout square|blur|crop|fit] [--zoom 1.2] [--crop-x 0.5]
YTM shorts list <job>
YTM shorts remove <job> <n>
YTM shorts render <job> [<n>]          # -> library/<job>/shorts/<job>-shortN.mp4 + preview jpg
```

## Choosing (quality over count)

- **At most 15 per recording** (enforced). Mine a long recording hard - aim for 8-15 - but every one must stand alone; drop weak ones rather
  than pad, and **zero is still a valid answer**.
- Default is **3 Shorts per day** (brand.json `posts_per_day`). One recording's Shorts become several days of posts:
  after upload + verify + the user's review, `YTM yt schedule <job>` spreads them 3/day at
  brand.json `post_times_utc` (dry run first; `--confirm` only after the user says yes).
- Uploads cost ~1,650 API units each (10,000/day), so ~6 uploads fit in one day.
- 15-58 s each (enforced), no overlap (enforced). 25-45 s is the sweet spot.
- Start ON the action (first frame already moving), end on a beat.
- Only clean play: hits, kills, precise aim, takedowns, set pieces. Never a moment from a failed
  attempt (`analysis/retries.json` spans), a death, or a stretch of missed shots - look at the
  frames before choosing.

## Hook text (first 3 seconds, on screen)

- 3-6 words, says what is about to happen, not what the title says.
- Run options through `py ~/.claude/skills/yt-script/hookscore.py --hook "..."` and keep the best.
- Emoji are stripped from on-screen text (the font cannot draw them) - put them in the title.

## Layout

- `square` (default): a 1:1 gameplay window the full width of
  the phone, centred over a blurred fill. `--crop-x` 0-1 picks which part of the 16:9 frame is kept
  (0.5 = centre); check the action and the subtitles stay inside the square.
- `blur`: full 16:9 frame centred over a blurred fill (whole HUD visible, but small on a phone). Safe for HUD-heavy footage.
  `--zoom 1.2-1.4` fills more of the screen when the action is central.
- `crop`: full-height 9:16 crop; `--crop-x` 0-1 picks the horizontal position. Best for
  third-person / centred action; check nothing important is cut off.
- `fit`: letterboxed on brand black.

HDR recordings are tone-mapped to SDR automatically (otherwise they look grey on phones).

## After rendering - verify by eye

**Read** each `shorts/shortN_preview.jpg` and check: hook text readable and inside the safe area,
watermark visible, action visible after the crop. Then hand titles to `/ytm-titles`.
