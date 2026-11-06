---
name: ytm-publish
description: >-
  Take reviewed the channel uploads public (now or scheduled), and safely change metadata on existing
  published videos with a backup first. Use for "publish it", "make it public", "schedule it",
  "fix the title of my old video", "update the description/tags on <video>".
---

# ytm-publish

Engine: `py ytm.py` (run from the repo root) (below: `YTM`).

```bash
YTM yt publish <job> long --privacy public --confirm
YTM yt publish <job> short1 --privacy public --at 2030-01-05T17:00:00Z --confirm    # scheduled
YTM yt update <video_id> --title "..."                     # DRY RUN: shows old vs new
YTM yt update <video_id> --description-file new.txt --tags "a,b,c" --apply
YTM yt index                                               # full metadata backup of every video
```

## Publishing a job upload

1. **Only after the user has watched the private upload and explicitly says publish** (in this
   conversation, for this video). Ask which targets and whether now or scheduled.
2. `--confirm` is passed only on that yes. The engine also requires a passing verify.
3. After: `YTM yt verify <job> <target>` and report the privacy YouTube actually shows.
4. If YouTube keeps it private: the API project is unverified, and YouTube locks API uploads to
   private until the project passes Google's audit. Tell the user to publish from YouTube Studio
   (or apply for the audit) - do not retry.

## Changing existing published videos (preserve them)

- Only title, description, tags, category can be changed - never privacy, never delete
  (the engine has no delete).
- Always dry-run first and show the user OLD vs NEW. `--apply` only after they approve that exact change.
- The engine backs up the full snippet + status to `backups/videos/<id>-<time>-before-update.json`
  before writing, sends every existing field back (YouTube replaces the whole snippet), and checks
  the response. To restore: run update with the backup's values.
- Batch fixes (e.g. retitling several old videos): run `YTM yt index` first (whole-channel backup),
  then one dry-run per video, one approval for the list, apply one at a time, report each.

## Shorts: 3 a day

By default 3 Shorts go out per day (brand.json `posts_per_day`). Schedule a whole recording's reviewed Shorts at once:

```bash
YTM yt schedule <job>                      # dry run: shows which Short goes out when
YTM yt schedule <job> --confirm            # after the user says yes
YTM yt schedule <job> --start 2030-01-10 --times 12:00,17:00,20:00 --per-day 3
```

Default slots come from brand.json `post_times_utc` (set them from your own Studio audience heatmap). Re-check them monthly with `/ytm-analytics`.
Slots already used by other recordings (data/schedule.json) are skipped, so days never get more than 3.

## Related video on every Short (standing rule)

Every Short links to its full long-form video (Studio → video → Details → **Related video**) so
Shorts viewers flow into long-form watch hours - the hours that count for the Partner Program.
The Data API cannot set this field: do it in YouTube Studio in the browser, after the
long video is public. Link to the same mission's long video; if the game has no long video, leave
it empty (never link a different game). A Short linked to another Short gets switched to the long
video.
