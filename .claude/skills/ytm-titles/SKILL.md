---
name: ytm-titles
description: >-
  Write accurate, on-brand the channel titles for a long-form video and its Shorts, paired with the
  thumbnail text and linted. Use for "title", "name this video", "titles for the Shorts", or when
  metadata.json still has <<WRITE>> titles.
---

# ytm-titles

Engine: `py ytm.py` (run from the repo root) (below: `YTM`). Reuses `~/.claude/skills/yt-package/title.py`.

## Inputs to read first

- `YTM status <job>` - game, mission, mission number (from `/ytm-analyze`, with evidence).
- `~/.claude/youtube/voice.md` and `brand.json` -> `titles`.
- What actually happens: the moments sheet / Short previews / chapter frames.
- `YTM meta draft <job>` creates `library/<job>/metadata.json` if it does not exist yet.

## Write

- **Long-form:** mission + what happens + game. Pattern `{hook} {emoji} | {game_short} – {mission} | 4K PS5`
  e.g. "The Bridge Goes Loud 🔥 | GAME – Mission Name | 4K PS5". Must name the game AND the mission.
- **Shorts:** the moment, not the mission. `{hook} {emoji} | {game_short} #Shorts`
  e.g. "He Never Saw It Coming 💀 | GAME #Shorts".
- Under 60 characters before the pipe matters most (mobile shows ~40).
- Generate 5-10 per target, check each:
  `py ~/.claude/skills/yt-package/title.py --title "..." --thumb "<thumbnail words>"`
- Keep the best; the thumbnail must not repeat the title's words.
- Accuracy over excitement: no event, character or place that is not in the footage.

## Save and lint

Put the chosen titles into `metadata.json` -> `long.title`, `short1.title`, ... (Edit tool), then
`YTM meta build <job>`. Fix every **error** it reports; show the user the warnings.

Show the user: chosen title per target, the runner-up, title.py score, thumbnail pairing.
