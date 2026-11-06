---
name: ytm-verify
description: >-
  Verify every the channel upload and metadata change against what was intended - title, description,
  tags, category, privacy, processing, duration, thumbnail - and that the original recording is
  untouched. Use after any upload or update, for "did it upload", "check the video", "is it processed".
---

# ytm-verify

Engine: `py ytm.py` (run from the repo root) (below: `YTM`).

```bash
YTM yt verify <job>               # every uploaded target of the job
YTM yt verify <job> long          # one target
YTM check-original <job>          # the recording is byte-identical to intake (fingerprint)
```

## What is checked (from the live API, not from our own records)

| Check | Pass when |
|---|---|
| video exists, on your channel | `videos.list` returns it, channelId = your channel |
| title / description / tags / category | exactly what `metadata.json` -> `final` says |
| privacy | what was requested (private/unlisted) or later published |
| not locked private | an `unlisted` request did not come back `private` (unverified-API lock) |
| upload / processing status | uploaded/processed; processing succeeded (or still processing) |
| duration | matches the rendered file within 2 s (once processed) |
| custom thumbnail | thumbnails.set succeeded |

Results are saved in the job (`uploads.<target>.verify`).

## Rules

- "Still processing" is not a pass: say so and verify again later (4K takes longest).
- Any mismatch: report it exactly (field, expected, actual). Fix metadata with `/ytm-publish`
  (update with backup), never by re-uploading.
- For metadata updates (`YTM yt update ... --apply`) the engine verifies from the API response and
  logs to `data/changes.json`; re-fetch with `YTM yt index` when the user wants proof.
- Never call something verified that was not checked.
