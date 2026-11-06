---
name: ytm-brand
description: >-
  Keep everything on the channel on-brand - colours, fonts, crest, title style, hashtag and tag policy,
  upload defaults - and review any output against it. Use for "branding", "brand check", "change the
  thumbnail style", "update the hashtags/footer", or when another ytm- skill needs the brand rules.
---

# ytm-brand

The brand lives in files, so every recording gets the same treatment without rebuilding anything:

| File | Holds |
|---|---|
| `config/brand.json` | colours, fonts, crest/logo, watermark, title patterns, hashtag + tag policy, description footer, upload defaults, Shorts/thumbnail specs |
| `~/.claude/youtube/voice.md` | the voice: audience, phrasing, banned words, what is never claimed (also read by the yt-* skills) |
| `config/games.json` | per-game names, abbreviations, hashtags, tags, confirmed missions |
| `config/avatar.jpg` | the logo crest used for the watermark and thumbnail badge |

## The channel identity

- Colours, tagline and style come from `config/brand.json` - read it, do not assume.
- Titles: `Hook! 🔥 | GAME` - hook first, game after a pipe, max 2 emoji, #Shorts only on Shorts.
- Thumbnails: 1-3 word Impact headline, white with black stroke and glow in the primary colour, crest top corner.
- Shorts: hook card for 3 s, logo watermark top-left, -14 LUFS audio.
- Hashtags: max 8, the first three are the ones YouTube shows above the title (game, mission, #YourChannel).
- Tags: game + mission specific first, brand last, under 480 characters - not the same 18 on every video.

## Brand review (run on any output)

1. Title follows the pattern; game + mission are accurate.
2. Thumbnail: 1-3 words, readable at 168 px, crest visible, colours on palette.
3. Short: hook in the safe area, watermark present, no emoji boxes.
4. Description: first two lines name the game, footer + hashtags present, nothing claimed that the
   footage does not show.

## Changing the brand

Edit `brand.json` (or `voice.md`) - every later job picks it up. Re-render existing Shorts or
thumbnails only if the user asks. Never edit published videos to match a new brand without the
user's go-ahead (`/ytm-publish` handles that, with backups).
