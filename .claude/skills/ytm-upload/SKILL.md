---
name: ytm-upload
description: >-
  Upload a long-form video or Short to YouTube through the existing OAuth integration -
  always private (or unlisted) for review first - set the thumbnail and verify. Use for "upload",
  "send it to YouTube", "put it on the channel", once metadata has passed lint.
---

# ytm-upload

Engine: `py ytm.py` (run from the repo root) (below: `YTM`). Auth: `~/.youtube-api/yt.py` + `token.json` (reused, not duplicated).

```bash
YTM yt whoami                          # confirms the token is your channel (not another channel on the same Google account)
YTM yt upload <job> long               # private by default
YTM yt upload <job> short1 --privacy unlisted
YTM yt thumbnail <job> long            # retry a thumbnail that failed
YTM yt quota                           # estimated units used today (10,000/day; an upload ~1,600)
```

## Before uploading, check

1. `YTM status <job>` - edit/shorts rendered, metadata lint OK (the engine refuses otherwise).
2. **Ask the user before the first upload of a session** which targets to upload and whether
   private or unlisted. Uploading is outward-facing; do not batch-upload unasked.
3. Quota: ~6 uploads per day max. If `yt quota` is high, say so and stop.

## What the engine guarantees

- Only `private` or `unlisted` (brand.json -> `allowed_privacy_before_review`). Public is a separate,
  confirmed step (`/ytm-publish`).
- Channel guard: aborts if the token is for any channel other than your channel.
- No duplicates: a target already uploaded is refused (`--force` only if the user asks).
- `notifySubscribers=false`, made-for-kids false, altered-content false.
- Video id saved to the job the moment the upload finishes; thumbnail set; then `/ytm-verify` runs.

Long uploads (4K, many GB) take a while - run in the background and report the link when done.

## Report

Per target: `https://youtu.be/<id>`, privacy, verification result. Remind the user to review in
YouTube Studio; nothing goes public until they say so.
If the channel guard fails: tell the user to re-run sign-in and pick **your channel** in Google's chooser.
