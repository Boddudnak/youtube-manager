---
name: ytm-intake
description: >-
  Register a new the channel PS5 recording as a job and lock the original so it can never be
  overwritten. Use when a new gameplay recording arrives ("I recorded a mission", "new recording",
  "process this video", a path to an .mp4/.webm), or to check what is waiting in the inbox.
---

# ytm-intake

Engine: `py ytm.py` (run from the repo root) (below: `YTM`). Part of `/ytm-manager`.

```bash
YTM scan                               # new recordings in inbox
YTM intake "<path to recording>"       # register (fingerprint, probe, mark read-only)
YTM intake "<path>" --copy             # also copy into the library first (when the source is a USB drive)
YTM status <job>                       # stages done + the next command
YTM check-original <job>               # re-fingerprint: proves the original is unchanged
```

## Steps

1. If the user gave no path, run `YTM scan`. PS5 recordings are moved by the user to the inbox or
   anywhere on the PC; any path works.
2. If the file is on a removable drive (D:, E:, ...) use `--copy` so the job survives unplugging.
3. `YTM intake` prints the job id. The PS5 filename (`<Game>_<YYYYMMDDhhmmss>`) gives a *guess* at
   the game (`game_confidence: filename`). It is confirmed later by `/ytm-analyze`, never trusted as is.
4. Report: job id, duration, resolution, HDR yes/no, guessed game.

## Rules

- **Originals are read-only and are never an output.** Every render writes under
  `library/<job>/`; the engine refuses any output path equal to the original.
- Re-registering the same file returns the existing job (fingerprint match) - no duplicates.
- Never delete, move or rename the user's recording.
