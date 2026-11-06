---
name: ytm-setup
description: >-
  First-time setup for YouTube Manager - checks Python, ffmpeg and packages, connects the user's own
  YouTube channel through Google Cloud OAuth, and fills in the channel and brand config. Use for
  "/ytm-setup", "set this up", "get started", "install", or whenever CLAUDE.md's setup checks fail.
---

# ytm-setup

Walk the user through setup **one step at a time**. Run each check yourself, and fix what you
can. When a step needs the user (a website, a sign-in, a choice), give short numbered instructions,
then wait until they say it's done. Re-run the check before moving on. Never ask for, paste or
store their passwords, client secret contents or tokens in chat. The files stay on their computer.

Below, `PY` is `py -3.12` on Windows and `python3` on macOS/Linux.

## 1. Tools

| Check | Fix |
|---|---|
| `PY --version` is 3.10+ (3.12 recommended) | Windows: `winget install Python.Python.3.12`; macOS: `brew install python@3.12` |
| `ffmpeg -version` works | Windows: `winget install Gyan.FFmpeg`; macOS: `brew install ffmpeg`; Linux: `sudo apt install ffmpeg`. Open a new terminal afterwards |
| `PY -c "import PIL, numpy, googleapiclient, google_auth_oauthlib, faster_whisper"` | `PY -m pip install -r requirements.txt` |

Ask before installing anything.

## 2. Helper skills

The engine calls helper scripts from four YouTube skills: `~/.claude/skills/yt-package/title.py`,
`yt-chapters/chapters.py`, `yt-viral/swipe.py` and `yt-retention/retention.py`. Check that they
exist. If they don't, tell the user to add the YouTube skills (yt-package, yt-chapters, yt-viral,
yt-retention) from the Claude skills catalog, or skip the steps that need them: title scoring,
chapter validation, competitor outliers and retention reports.

## 3. Connect YouTube (the user does this in Google Cloud)

Give the user these steps:

1. Go to https://console.cloud.google.com/ → create a project (any name).
2. **APIs & Services → Library**: enable **YouTube Data API v3** and **YouTube Analytics API**.
3. **OAuth consent screen**: External, add your own Google account as a **test user**.
4. **Credentials → Create credentials → OAuth client ID → Desktop app**. Download the JSON.
5. Save it as `~/.youtube-api/client_secret.json` (create the folder).

Then you copy `auth/yt.py` to `~/.youtube-api/yt.py`. Never read client_secret.json aloud or copy
it into the repo.

## 4. Channel config

1. Ask for their channel's **handle** (e.g. `@name`) and **channel ID**. The ID is in YouTube Studio
   → Settings → Channel → Advanced settings, or at https://www.youtube.com/account_advanced.
2. Copy `config/channel.example.json` → `config/channel.json` and fill in `channel_id`, `title`
   and `handle`.
3. Run `PY ytm.py yt whoami`. A browser opens to sign in. If their Google account has several
   channels, they must pick **this** channel. Success prints `OK - token is for <title>`.
   - Wrong channel → move `~/.youtube-api/token.json` aside and run it again.
   - Testing-mode tokens expire every 7 days. Signing in again fixes that.

## 5. Brand (ask, don't guess)

Ask the user for each item and write the answers into `config/brand.json`:

- Display name, handle, tagline
- Two brand colours (hex values, or ask them to describe the colours and suggest values)
- Title pattern (keep the default unless they want another)
- Description footer, and 1-3 brand tags
- Shorts per day and posting times (suggest Studio → Analytics → Audience → "When your viewers are
  on YouTube")
- Fonts: the defaults are Windows fonts. On macOS/Linux, point them at installed `.ttf` files

Also ask:

- Optionally, a square logo saved as `config/avatar.jpg` (used for the watermark and thumbnail
  badge).
- Which game(s) they play. Replace the example in `config/games.json` with each game's name, short
  name, aliases, hashtags and tags.

## 6. Done check

- `PY ytm.py -h` runs.
- `PY ytm.py yt whoami` prints OK.
- `PY ytm.py jobs` runs (an empty list is fine).

Tell the user setup is done. Next: put a recording in `inbox/` and say **"process my new
recording"**. Remind them that nothing is ever made public without their explicit "publish".
