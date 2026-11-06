# YouTube Manager

A YouTube channel pipeline for gameplay creators, run by [Claude Code](https://claude.com/claude-code).

You drop in a gameplay recording, and Claude:

1. Analyzes the footage and works out the game and mission.
2. Cuts loading screens, menus and failed attempts.
3. Renders the long-form video and up to 15 vertical Shorts.
4. Makes thumbnails and writes titles, descriptions and tags.
5. Uploads everything **private** for you to review.

Nothing goes public until you say "publish". It also tracks competitor channels and your growth
analytics.

## Quick start: let Claude set it up

1. Install [Claude Code](https://claude.com/claude-code). The desktop app or the terminal both work.
2. Clone this repo:
   ```bash
   git clone https://github.com/Boddudnak/youtube-manager.git
   ```
3. Open the `youtube-manager` folder in Claude Code and say:
   > **set this up**

   (or run `/ytm-setup`).

Claude reads [`CLAUDE.md`](CLAUDE.md) and walks you through each step:

- Checking Python, ffmpeg and the packages.
- Connecting your own YouTube channel through Google Cloud. You sign in yourself, and your keys stay
  on your computer in `~/.youtube-api/`.
- Filling in your channel name, colours, games and posting times.

When setup is done, put a recording in `inbox/` and say:

> **process my new recording**

## What you need

- Windows 10/11 is tested. macOS and Linux should work but are untested; you'll need to change the
  font paths in `config/brand.json`.
- Python 3.10+ (3.12 recommended) and [ffmpeg](https://ffmpeg.org/).
- A Google account with a YouTube channel, and a free Google Cloud project (setup explains this).
- Optional: the Claude YouTube skills `yt-package`, `yt-chapters`, `yt-viral` and `yt-retention`.
  They are used for title scoring, chapter checks, competitor outliers and retention reports.

## What it does

| Stage | Skill | What happens |
|---|---|---|
| Setup | `/ytm-setup` | Guided first-time setup |
| Everything | `/ytm-manager` | Runs the full pipeline below and stops for your review before uploading |
| Intake | `/ytm-intake` | Registers the recording, fingerprints it and makes the original read-only |
| Analyze | `/ytm-analyze` | Builds a contact sheet, transcribes the audio (faster-whisper) and identifies the game + mission |
| Moments | `/ytm-moments` | Finds the best moments and the dead spans (loading screens, menus) |
| Edit | `/ytm-edit` | Cuts dead time and die → reload → retry loops, renders losslessly (keeps 4K HDR), adds chapters |
| Shorts | `/ytm-shorts` | Renders up to 15 branded 1080×1920 Shorts with a hook card and watermark |
| Thumbnail | `/ytm-thumbnail` | Picks the best frame, adds a 1–3 word glowing headline, checks it at feed size |
| Titles / SEO | `/ytm-titles`, `/ytm-seo` | Writes titles, descriptions, tags and hashtags, then lints them for accuracy and YouTube limits |
| Upload | `/ytm-upload` | Uploads private or unlisted only and sets the thumbnail |
| Verify | `/ytm-verify` | Checks every field against the live YouTube API |
| Publish | `/ytm-publish` | Makes videos public now or on a schedule (e.g. 3 Shorts a day). Backs up metadata before changing a live video |
| Research | `/ytm-competitors`, `/ytm-analytics` | Finds competitor outliers and reports growth, Shorts vs long-form and retention |
| Brand | `/ytm-brand` | Checks every output against `config/brand.json` |

## Safety (enforced in code)

- **Originals:** your recordings are made read-only, fingerprinted and never overwritten.
- **No deletes:** there is no delete operation anywhere in the engine.
- **Uploads:** private or unlisted only. An upload is refused if metadata lint fails or if it is a duplicate.
- **Publishing:** needs `--confirm` and a passing verify.
- **Changes to live videos:** dry run first, then a backup, then a verify afterwards.
- **Channel guard:** every API write stops unless the signed-in account is the channel in
  `config/channel.json`. This protects you if your Google account owns more than one channel.

## Layout

```
CLAUDE.md              instructions Claude follows in this folder
.claude/skills/        the ytm-* skills (loaded automatically by Claude Code)
ytm.py                 CLI entry (py ytm.py -h)
ytmanager/             engine: media, intake, analyze, moments, edit, shorts, graphics,
                       thumbnail, metadata, youtube, research, analytics, voice, ...
auth/yt.py             Google OAuth helper (setup copies it to ~/.youtube-api/)
config/                brand.json, games.json, competitors.json, channel.example.json
inbox/                 drop recordings here
```

Created as you use it and never committed: `library/` (one folder per recording), `data/`
(analytics, quota ledger, change log), `backups/`, and `config/channel.json`.

## Commands (what Claude runs for you)

```
py ytm.py jobs | status [job] | scan | intake <file> [--copy]
py ytm.py analyze <job> | identify <job> --game .. --mission .. --evidence ..
py ytm.py moments <job> | edit plan|render|chapters <job>
py ytm.py shorts add|list|render <job> ... | thumb candidates|make <job> ...
py ytm.py meta draft|build|lint <job>
py ytm.py yt whoami|quota | yt upload|verify <job> <target> | yt schedule <job> [--confirm]
py ytm.py yt publish <job> <target> --privacy public [--at ISO] --confirm
py ytm.py competitors discover|add|scan ... | analytics report|retention ...
```

## License

MIT. See [LICENSE](LICENSE).
