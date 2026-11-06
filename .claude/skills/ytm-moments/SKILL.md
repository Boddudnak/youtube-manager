---
name: ytm-moments
description: >-
  Find the important gameplay moments in a recording - firefights, explosions, boss hits,
  set pieces - and the dead spans (loading screens, menus). Use for "best moments", "highlights",
  "what should I clip", or before Shorts and thumbnails.
---

# ytm-moments

Engine: `py ytm.py` (run from the repo root) (below: `YTM`). Needs `/ytm-analyze` first.

```bash
YTM moments <job>                      # 10 ranked candidates (~40 s) + dead spans + a frame sheet
YTM moments <job> --length 30 --count 12
```

## How moments are scored

Per second: loudness rank (35%), sudden loudness jumps over the last 10 s - gunfire, explosions
(30%), motion (25%), scene-cut density (10%). Dark or static seconds score zero. Windows are
non-overlapping, snapped to scene cuts, and rejected if more than 15% dead.

## Judge them by eye - the score only finds candidates

**Read** `library/<job>/analysis/moments_sheet.jpg` (start / peak / end frame per candidate).
A moment is worth keeping when:

1. It reads **without the rest of the mission** - a viewer from the Shorts feed knows what is
   happening within 2 seconds.
2. Something **changes**: an ambush, a breach, a boss phase, a takedown, a vehicle exploding.
3. It **ends on a beat**, not mid-walk.

Reject: menus, cutscene dialogue with no action (unless it is a famous scene), walking sections,
anything with a spoiler the user would not want in a Short.

## Report

A table: rank, timecode, what happens (from the frames), keep / reject and why. Recommend up to
three for `/ytm-shorts` and one frame for `/ytm-thumbnail`. Dead spans go to `/ytm-edit`.
