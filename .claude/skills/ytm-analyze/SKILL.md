---
name: ytm-analyze
description: >-
  Analyze a recording before any editing - signals pass, contact sheet, dialogue transcript -
  then identify the game and mission from the footage itself. Use after intake, for "what is in this
  recording", "which mission is this", or whenever a job has not been analyzed.
---

# ytm-analyze

Engine: `py ytm.py` (run from the repo root) (below: `YTM`). Every recording is analyzed before editing.

```bash
YTM analyze <job>                      # signals + 24-36 frame contact sheet + transcript
YTM analyze <job> --no-transcribe      # faster; use when the recording has no dialogue at all
YTM identify <job> --game "<exact game name>" --mission "<mission name>" --number N --evidence "<what showed it>"
```

Long recordings: run `YTM analyze` in the background - one decode pass is roughly 3-10x realtime.

## Identify the game and mission - from evidence, not guesses

1. **Read** `library/<job>/analysis/contact_sheet.jpg` (the Read tool shows images). For text that
   is too small, open the single frames in `analysis/frames/` (960 px).
2. Look for: mission title cards, objective text, HUD, location captions, character faces, the
   pause/loading screen naming the mission.
3. Read `analysis/transcript.srt` if it exists - names and places in dialogue confirm the mission.
4. Compare against `config/games.json` (known missions from past uploads).
5. Run `YTM identify` with `--evidence` naming exactly what you saw ("mission title card at 0:42").
   New games and missions are learned into games.json automatically.
6. Confidence: `high` = title card / HUD text seen; `medium` = characters + location match a known
   mission; `low` = inferred. On `low`, **ask the user** before anything is titled.

## What to report

Game, mission (+ number), evidence, confidence, duration, how much is loading/menus
(`dark_seconds`, `static_seconds` from the summary), and whether there is dialogue.

## Never

Never name a mission you did not see evidence for. A wrong mission name in a title is the one
error this channel cannot afford - search viewers bounce and the video ranks for the wrong query.
