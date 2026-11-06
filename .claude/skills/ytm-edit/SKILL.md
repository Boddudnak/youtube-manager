---
name: ytm-edit
description: >-
  Edit a long-form gameplay video - cut loading screens, pause menus, dead air and repeated
  attempts (die -> reload -> replay), keep the
  4K HDR quality, and propose chapters. Use for "edit the long video", "cut the loading screens",
  "make the full mission video", "add chapters".
---

# ytm-edit

Engine: `py ytm.py` (run from the repo root) (below: `YTM`). Needs `/ytm-moments` first.

```bash
YTM edit plan <job>                    # EDL: dark/static spans >= 8 s + failed attempts that were replayed
YTM edit plan <job> --min-dead 15 --keep-head
YTM edit show <job>                    # the current EDL
YTM edit render <job>                  # copy mode: lossless, keyframe cuts, HDR kept exactly
YTM edit render <job> --mode encode    # frame-accurate re-encode (HDR -> x265 10-bit HDR10, slow)
YTM edit chapters <job>                # chapter points on the EDITED timeline + a frame for each
```

## What gets cut

Only the attractive, clean gameplay stays: no wasted time, **no repeated clips**. When the user dies
and the checkpoint reloads, the failed attempt, the death and the reload are cut and only the final,
successful run is kept (`analysis/retries.json`, found by matching footage frame-for-frame).
Retry spans over 10 minutes are NOT cut automatically - they are listed in `edl.json` -> `review`
because they may be backtracking; look at the frames and move real retries into `cuts`.
Misses inside a firefight stay - cutting mid-fight breaks continuity; clean kills and good aim go to
Shorts instead (`/ytm-shorts`).

## Review the cuts before rendering

For each cut in `library/<job>/edit/edl.json`, look at the contact-sheet frames nearest its start
and end (`analysis/frames/`, named by second). Keep a "static" span when it is actually
a cutscene or a tense slow moment - delete that cut from `edl.json` ("cuts" list) by editing the
file, then render. Long-form the channel videos are cinematic: cut waiting, never story.

No cuts = passthrough: the original is uploaded as-is (still read-only, nothing re-encoded).

## Chapters

`YTM edit chapters` proposes points (from dialogue via `/yt-chapters` when there is a transcript,
otherwise from visual section breaks) with a frame per point in `edit/chapters/`. **Look at each
frame** and name the chapter as what happens there, 2-5 words ("Ambush at the Docks"). The names
go into `metadata.json` -> `long.chapters` via `/ytm-seo`. YouTube needs 3+ chapters, the first at
0:00, each 10 s+ - otherwise leave chapters out.

## Rules

- Copy mode is the default. Use encode only when a cut must be frame-exact.
- Never trim gameplay the user would consider part of the mission.
- Report the before/after runtime and every cut with its reason.
