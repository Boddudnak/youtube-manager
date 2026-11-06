# YouTube Manager: instructions for Claude

This repo is a YouTube channel pipeline for gameplay creators. You (Claude) drive it through the
project skills in `.claude/skills/`, and the engine does the work: `py ytm.py <command>` (Windows) or
`python3 ytm.py <command>` (macOS/Linux), always run from the repo root.

## First thing in every session

Check whether setup is finished:

- `config/channel.json` exists and its `channel_id` is not `UCxxxxxxxxxxxxxxxxxxxxxx`
- `~/.youtube-api/yt.py` and `~/.youtube-api/client_secret.json` exist
- `py ytm.py yt whoami` prints `OK - token is for ...`

If any check fails, tell the user setup is not finished and run the `/ytm-setup` skill. It walks
them through setup one step at a time. Do not start processing recordings before setup passes.

## After setup

- New recording → `/ytm-manager` (it runs every step and stops for review before uploading).
- Single steps have their own skills: `/ytm-intake`, `/ytm-analyze`, `/ytm-moments`, `/ytm-edit`,
  `/ytm-shorts`, `/ytm-thumbnail`, `/ytm-titles`, `/ytm-seo`, `/ytm-upload`, `/ytm-verify`,
  `/ytm-publish`, `/ytm-competitors`, `/ytm-analytics`, `/ytm-brand`.
- `py ytm.py status latest` prints the next command for the newest job.

## Rules that always apply

- Never modify, move or delete the user's original recordings.
- Uploads go up **private** (or unlisted). Make a video public only after the user has watched it
  and said "publish" for that video.
- Never change an already-published video without a dry run, the user's yes and a backup.
- Never put the user's keys or tokens (`client_secret.json`, `token.json`) inside this repo, and
  never commit `config/channel.json`, `inbox/`, `library/`, `data/` or `backups/`.
- Titles and descriptions must describe only what is actually in the footage.
