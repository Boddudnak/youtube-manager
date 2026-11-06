---
name: ytm-seo
description: >-
  Write unique the channel descriptions, relevant hashtags and tags, and the chapter list for a video and
  its Shorts, then lint them for accuracy, uniqueness and YouTube limits. Use for "description",
  "tags", "hashtags", "SEO", "metadata", or when metadata.json has <<WRITE>> placeholders.
---

# ytm-seo

Engine: `py ytm.py` (run from the repo root) (below: `YTM`). Rules from `/yt-seo`; chapter rules from `/yt-chapters`.

```bash
YTM meta draft <job>        # metadata.json per target, tags + hashtags pre-filled from brand + game + mission
YTM meta build <job>        # assemble final descriptions and lint
YTM meta show <job>
YTM yt index                # refresh the channel index (uniqueness check + a metadata backup)
```

## What you write in `library/<job>/metadata.json`

Per target (`long`, `short1`..): `hook_lines` (2 lines), `body`, and for long-form `chapters`.

- **hook_lines** = the only lines anyone reads (above "...more", and the search snippet). Name the
  game and mission in the words people search: "<Game> Mission 4 '<Mission>' full walkthrough in
  4K HDR - no commentary."
- **body** = 2-5 sentences of what actually happens in THIS video, in order. Specific places,
  characters, set pieces seen in the footage. Never paste a previous description - the linter
  rejects anything 50%+ similar to any channel video.
- **chapters** (long-form): times from `YTM edit chapters`, titles you wrote by looking at the frames.
- The engine adds: game/mission line, brand footer, hashtags. Do not add them twice.

## Tags and hashtags

Pre-filled: mission tags first, then game, then format, then brand (under 480 chars). Add only
what a real person would type (spellings, the abbreviation, the mission name); remove anything
not in the video. Hashtags: max 8; the first three show above the title - keep
game, mission, #YourChannel first. Shorts get #Shorts.

## The query test (before building)

Write the 3 searches this video should win (e.g. "<game> <mission>", "<game> mission 4",
"<game> <place> mission"). The title + first two lines must contain those words.

## Lint

`YTM meta build <job>` blocks: unwritten placeholders, missing game, wrong #Shorts use, over-limit
tags/hashtags/length, `<` `>`, broken chapters, duplicated descriptions. Upload is impossible until
it passes. Show the user the final title + description + tags per target.
