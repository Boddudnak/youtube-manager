---
name: ytm-manager
description: >-
  YouTube Manager master workflow - YouTube-only channel management for your channel. Takes a PS5
  gameplay recording from intake to verified private uploads (long-form + up to 15 Shorts, posted 3 a day), and runs
  competitor research and growth analytics. Use for "/ytm-manager", "process my new recording",
  "run the pipeline", "what's next for the channel", "channel status", or any channel request that
  spans more than one step.
---

# ytm-manager

**YouTube only.** No Instagram, TikTok, Facebook or any other platform - decline and stay on YouTube.

Engine: `py ytm.py` (run from the repo root) (below: `YTM`). All state is in files, so any session can
pick up any job where it stopped: `YTM jobs`, `YTM status <job>` (prints the next command).

## The pipeline for one recording

| # | Step | Skill | Gate before moving on |
|---|---|---|---|
| 1 | Register + lock original | `/ytm-intake` | job id exists, original read-only |
| 2 | Analyze (signals, contact sheet, transcript) | `/ytm-analyze` | always - nothing is edited unanalyzed |
| 3 | Identify game + mission from evidence | `/ytm-analyze` | confidence high/medium, else ask the user |
| 4 | Rank moments + dead spans | `/ytm-moments` | looked at the moments sheet |
| 5 | Long-form edit + chapters | `/ytm-edit` | cuts reviewed; HDR kept (copy mode) |
| 6 | Up to 15 Shorts | `/ytm-shorts` | each self-contained; previews checked; 0 is allowed |
| 7 | Thumbnail(s) | `/ytm-thumbnail` | readable at 168 px; not repeating the title |
| 8 | Titles | `/ytm-titles` | game + mission accurate; title.py checked |
| 9 | Descriptions, tags, hashtags | `/ytm-seo` | `YTM meta build` lint OK (unique, accurate, in limits) |
| 10 | **Review stop** | - | show the user everything below and get a go-ahead to upload |
| 11 | Upload private/unlisted | `/ytm-upload` | user said upload; quota OK |
| 12 | Verify | `/ytm-verify` | every check passes (re-run while processing) |
| 13 | **Review stop** | - | user watches the private videos in YouTube Studio |
| 14 | Publish / schedule | `/ytm-publish` | user explicitly says publish, per video |

Steps 1-9 need no approval: they only create files inside `library/`.
Run long steps (analyze on a long recording, edit render in encode mode, uploads) in the background.

### Review stop (step 10) - show, in one message

- Game + mission + the evidence; runtime before/after edit and what was cut.
- Each Short: timecode, hook, preview image path; why it was picked.
- Thumbnail path + feed preview.
- Per target: title, first two description lines, tags count, hashtags.
- Then ask: upload these as private?

## Channel-level work (no recording needed)

- `/ytm-analytics` - weekly growth report (organic vs paid, Shorts vs long, top videos).
- `/ytm-competitors` - keep 10+ tracked, scan for outliers, feed ideas back to titles and Shorts.
- `/ytm-brand` - brand rules; `/ytm-publish` - safe fixes to existing videos (backup + dry-run first).
- The generic `yt-*` skills (audit, plan, retention, script, comment...) work alongside; their
  helper scripts are what the engine calls for titles, chapters, outliers and retention.

## Non-negotiables

1. **Originals are never modified** (read-only + fingerprint; `YTM check-original <job>`).
2. **Existing published videos are never deleted and never changed without a dry-run + the user's
   yes** for that exact change; a backup is written first.
3. **Uploads start private (or unlisted)**; public only via `/ytm-publish --confirm` after review.
4. **Every upload and update is verified** against the live API before it is called done.
5. **Channel guard**: the token must be your channel - it protects you if one Google account owns several channels. If the guard fails, re-run sign-in and choose your channel.
6. **Accuracy**: never title or describe something not visible in the footage.

## Where things are

- `README.md` - layout, commands, maintenance.
- `config/` brand.json, games.json, channel.json, competitors.json, avatar.jpg
- `library/<job>/` job.json, analysis/, edit/, shorts/, thumbs/, metadata.json
- `data/` channel_index, analytics snapshots + reports, competitor scans, quota ledger, changes log
- `backups/` channel-wide and per-video metadata backups
- OAuth: `~/.youtube-api/` (yt.py + token.json - shared with the existing helper scripts)

## Troubleshooting

- `token is for another channel` -> sign-in picked the wrong channel; move `~/.youtube-api/token.json`
  aside, run `YTM yt whoami` (opens Google sign-in) and pick your channel in the channel chooser.
- Refresh token expired after 7 days -> the OAuth app is in Testing mode; sign in again
  (or publish the OAuth consent screen to Production in Google Cloud to stop the weekly expiry).
- `quotaExceeded` -> wait for midnight Pacific; `YTM yt quota` shows the local estimate.
- Video stays private after publish -> unverified API project lock; publish from Studio.
