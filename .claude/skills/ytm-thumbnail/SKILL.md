---
name: ytm-thumbnail
description: >-
  Make the branded the channel thumbnail for a video - pick the strongest frame, 1-3 word glowing
  headline, logo crest badge - and check it at feed size. Use for "thumbnail", "make the thumbnail",
  "my CTR is low", or before uploading a long-form video.
---

# ytm-thumbnail

Engine: `py ytm.py` (run from the repo root) (below: `YTM`).

```bash
YTM thumb candidates <job>                                   # ~12 sharp, high-action frames -> candidates_sheet.jpg
YTM thumb make <job> --index 3 --text "BRIDGE GOES LOUD"      # from a candidate
YTM thumb make <job> --time 14:02 --text "ESSEX FALLS" --side right --zoom 1.15
YTM thumb make <job> --target short1 --index 5 --text "..."  # optional, for a Short
```

Output: `library/<job>/thumbs/<job>-long.jpg` (1280x720, under 2 MB) + `long_feed_preview.jpg`.

## Picking the frame

**Read** `thumbs/candidates_sheet.jpg` (sorted by sharpness). Choose: one clear subject (a face,
a weapon, an explosion, the boss), high contrast, nothing important on the side the text goes.
Motion-blurred frames read as mush at feed size - prefer the sharp ones.

## The words

- **1-3 words** (enforced), ALL CAPS automatically, no emoji.
- **Must not repeat the title** - the thumbnail says what the title does not
  (`/ytm-titles` checks the pairing with `yt-package/title.py`).
- Put the text on the emptier side (`--side left|right`); the crest badge goes to the other corner.

## Check before it is used

**Read** the thumbnail and `long_feed_preview.jpg` (360 / 246 / 168 px wide). If the words do not
read at 168 px, use fewer or bigger words. Report the path and the pairing with the title.
Custom thumbnails upload only if the channel is phone-verified - `/ytm-upload` reports if not.
