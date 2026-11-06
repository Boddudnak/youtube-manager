"""Brand graphics with Pillow: logo badge, Shorts hook card, thumbnail composition."""
import os, re
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from . import core

EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF️‍]+")


def plain(text):
    """Strip emoji - the headline fonts cannot draw them and they render as boxes."""
    return re.sub(r"\s{2,}", " ", EMOJI.sub("", text)).strip()


def brand():
    return core.config("brand")


def logo_badge(size, ring=True, opacity=1.0):
    b = brand()
    path = core.root_path(b["logo"])
    if os.path.exists(path):
        im = ImageOps.fit(Image.open(path).convert("RGB"), (size, size), Image.LANCZOS)
    else:  # no logo yet: the channel's initials on the background colour
        im = Image.new("RGB", (size, size), b["colors"]["background"])
        initials = "".join(w[0] for w in b["display_name"].split()[:2]).upper() or "YT"
        font = ImageFont.truetype(b["fonts"]["headline"], size // 3) if os.path.exists(b["fonts"]["headline"]) else ImageFont.load_default()
        ImageDraw.Draw(im).text((size // 2, size // 2), initials, fill=b["colors"]["text"], font=font, anchor="mm")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=int(255 * opacity))
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    if ring:
        w = max(3, size // 28)
        ImageDraw.Draw(out).ellipse((w // 2, w // 2, size - 1 - w // 2, size - 1 - w // 2), outline=b["colors"]["primary"], width=w)
    return out


def _fit_font(text_lines, path, max_w, max_size, min_size=40):
    for size in range(max_size, min_size - 1, -4):
        f = ImageFont.truetype(path, size)
        if all(f.getbbox(l)[2] - f.getbbox(l)[0] <= max_w for l in text_lines): return f
    return ImageFont.truetype(path, min_size)


def _wrap(text, max_lines=2):
    words = text.split()
    if len(words) <= 2 or max_lines == 1: return [text]
    best = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(" ".join(words[k:]))))
    return [" ".join(words[:best]), " ".join(words[best:])]


def _glow_text(canvas, xy_lines, font, fill, glow, stroke, stroke_w, spacing):
    """Text with a coloured glow behind a black stroke - the brand crest look."""
    W, H = canvas.size
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for (x, y), line in xy_lines:
        d.text((x, y), line, font=font, fill=glow, stroke_width=stroke_w + 10, stroke_fill=glow)
    layer = layer.filter(ImageFilter.GaussianBlur(14))
    canvas.alpha_composite(layer)
    d = ImageDraw.Draw(canvas)
    for (x, y), line in xy_lines:
        d.text((x, y), line, font=font, fill=fill, stroke_width=stroke_w, stroke_fill=stroke)


def hook_card(text, out, W=1080, H=1920):
    """Transparent 1080x1920 overlay: the first-seconds hook line inside the Shorts safe area."""
    b = brand(); c = b["colors"]
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    lines = _wrap(plain(text).upper())
    font = _fit_font(lines, b["fonts"]["headline"], W - 140, 120)
    lh = font.getbbox("HG")[3] + 18
    y0 = 380  # below the Shorts top bar and the watermark (y 190-300)
    band = Image.new("RGBA", (W, lh * len(lines) + 60), (7, 6, 12, 150))
    canvas.alpha_composite(band, (0, y0 - 30))
    xy = []
    for i, l in enumerate(lines):
        w = font.getbbox(l)[2] - font.getbbox(l)[0]
        xy.append((((W - w) // 2, y0 + i * lh), l))
    _glow_text(canvas, xy, font, c["text"], c["primary"], c["stroke"], 7, 18)
    canvas.save(out)
    return out


def watermark(out):
    wm = brand()["watermark"]
    logo_badge(wm["size_px"], opacity=wm["opacity"]).save(out)
    return out


def thumbnail(frame_path, text, out, side="left", zoom=1.0, accent=None, hdr=False):
    """1280x720 YouTube thumbnail: graded frame, darkened text side, glowing 1-3 word headline, crest badge,
    and brand corner tags (thumbnail.corners: PS5 top-left, '4K HDR' top-right - '4K' only when the source is SDR)."""
    b = brand(); c = b["colors"]; tcfg = b["thumbnail"]
    W, H = tcfg["width"], tcfg["height"]
    im = Image.open(frame_path).convert("RGB")
    if zoom > 1.0:
        w, h = im.size; cw, ch = int(w / zoom), int(h / zoom)
        im = im.crop(((w - cw) // 2, (h - ch) // 2, (w + cw) // 2, (h + ch) // 2))
    im = ImageOps.fit(im, (W, H), Image.LANCZOS)
    im = ImageEnhance.Contrast(im).enhance(1.18)
    im = ImageEnhance.Color(im).enhance(1.25)
    im = ImageEnhance.Sharpness(im).enhance(1.4)
    canvas = im.convert("RGBA")
    grad = Image.new("L", (W, 1))
    for x in range(W):
        f = x / W if side == "right" else 1 - x / W
        grad.putpixel((x, 0), int(215 * max(0.0, (f - 0.35) / 0.65) ** 1.2))
    shade = Image.new("RGBA", (W, H), (7, 6, 12, 255)); shade.putalpha(grad.resize((W, H)))
    canvas.alpha_composite(shade)
    words = plain(text).upper().split()
    if len(words) > tcfg["max_words"]:
        core.die(f"thumbnail text has {len(words)} words - the brand limit is {tcfg['max_words']}")
    lines = _wrap(" ".join(words))
    font = _fit_font(lines, b["fonts"]["headline"], int(W * 0.52), 190, 80)
    lh = font.getbbox("HG")[3] + 10
    y0 = (H - lh * len(lines)) // 2 - 10
    xy = []
    for i, l in enumerate(lines):
        w = font.getbbox(l)[2] - font.getbbox(l)[0]
        x = 56 if side == "left" else W - 56 - w
        xy.append(((x, y0 + i * lh), l))
    _glow_text(canvas, xy, font, c["text"], accent or c["primary"], c["stroke"], 9, 10)
    corners = tcfg.get("corners", {})
    if corners:
        cf = ImageFont.truetype(b["fonts"].get("headline_alt", b["fonts"]["headline"]), corners.get("size", 64))
        logo = core.root_path(corners.get("top_left_logo", ""))
        if corners.get("top_left_logo") and os.path.exists(logo):
            lg = Image.open(logo).convert("RGBA"); lg.thumbnail((260, corners.get("size", 64) + 12))
            canvas.alpha_composite(lg, (30, 28))
        elif corners.get("top_left"):
            _glow_text(canvas, [((30, 22), corners["top_left"])], cf, c["text"], (0, 0, 0), c["stroke"], 4, 6)
        tr = corners.get("top_right" if hdr else "top_right_sdr", "")
        if tr:
            w = cf.getbbox(tr)[2] - cf.getbbox(tr)[0]
            _glow_text(canvas, [((W - 30 - w, 22), tr)], cf, c["text"], (0, 0, 0), c["stroke"], 4, 6)
    badge = logo_badge(118)
    if corners: canvas.alpha_composite(badge, (W - 118 - 28, H - 118 - 26) if side == "left" else (28, H - 118 - 26))
    else: canvas.alpha_composite(badge, (W - 118 - 28, 26) if side == "left" else (28, 26))
    rgb = canvas.convert("RGB")
    q = 92
    while True:
        rgb.save(out, quality=q, optimize=True)
        if os.path.getsize(out) <= tcfg["max_bytes"] or q <= 60: break
        q -= 6
    return out


def cinematic(frame_path, out, kicker, title, vertical=False, crop_x=0.5, game_logo="assets/game_logo.png"):
    """Full-4K cinematic thumbnail (thumbnail.quality_rule): long 3840x2160 or Shorts 2160x3840. Letterbox bars and the
    subtitle/HUD strip are cropped off, then graded + vignette; game logo top-left, crest top-right, a yellow kicker
    ('MISSION 7') over the big title in the centre. Writes <out>_master_4k.png and <out>.jpg (4K, under max_bytes)."""
    import numpy as np
    b = brand(); c = b["colors"]; t = b["thumbnail"]
    W, H = t["master_short"] if vertical else t["master_long"]; S = W / 1920 if not vertical else W / 1080
    im = Image.open(frame_path).convert("RGB")
    rows = np.asarray(im.convert("L"), float).mean(1); act = np.where(rows > 10)[0]
    if not len(act): act = np.arange(len(rows))
    top = int(act[0]); bot = top + int((int(act[-1]) + 1 - top) * (0.78 if vertical else 0.86))
    cw = min(im.width, int((bot - top) * W / H)); x = int((im.width - cw) * crop_x)
    im = im.crop((x, top, x + cw, bot)).resize((W, H), Image.LANCZOS)
    im = ImageEnhance.Contrast(im).enhance(1.12); im = ImageEnhance.Color(im).enhance(1.18); im = ImageEnhance.Sharpness(im).enhance(1.35)
    yy, xx = np.mgrid[0:H, 0:W]; r = np.hypot((xx - W / 2) / (W / 2), (yy - H / 2) / (H / 2))
    vig = np.clip(1 - 0.45 * np.clip(r - (0.6 if vertical else 0.55), 0, None) ** 1.4, 0.45, 1)[..., None]
    cv = Image.fromarray((np.asarray(im, float) * vig).clip(0, 255).astype(np.uint8)).convert("RGBA")
    lines = _wrap(plain(title).upper(), 3 if vertical else 1)
    big = _fit_font(lines, b["fonts"]["headline"], W - int(130 * S), int((165 if vertical else 230) * S), 60)
    small = _fit_font([kicker.upper()], b["fonts"]["headline"], W - int(100 * S), int((65 if vertical else 78) * S), 40)
    lh = big.getbbox("HG")[3] + int(15 * S); hb = lh * len(lines); gap = int((85 if vertical else 88) * S)
    y1 = H // 2 - (hb + gap) // 2; y2 = y1 + gap
    shade = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shade).ellipse((W * 0.1 - 100 * S, y1 - 130 * S, W * 0.9 + 100 * S, y2 + hb + 130 * S), fill=125)
    cv.alpha_composite(Image.merge("RGBA", [Image.new("L", (W, H), 0)] * 3 + [shade.filter(ImageFilter.GaussianBlur(85 * S))]))
    k = kicker.upper(); _glow_text(cv, [(((W - small.getbbox(k)[2]) // 2, y1), k)], small, "#FFD21F", c["primary"], c["stroke"], int(5 * S), 0)
    xy = [(((W - (big.getbbox(l)[2] - big.getbbox(l)[0])) // 2, y2 + i * lh), l) for i, l in enumerate(lines)]
    _glow_text(cv, xy, big, c["text"], c["primary"], c["stroke"], int(9 * S), 0)
    if game_logo and os.path.exists(core.root_path(game_logo)):
        g = Image.open(core.root_path(game_logo)).convert("RGBA"); f = (1.3 if vertical else 1.5) * S
        cv.alpha_composite(g.resize((int(g.width * f), int(g.height * f)), Image.LANCZOS), (int(45 * S), int((75 if vertical else 40) * S)))
    crest = logo_badge(int((280 if vertical else 330) * S)); cv.alpha_composite(crest, (W - crest.width - int(35 * S), int((55 if vertical else 25) * S)))
    rgb = cv.convert("RGB"); rgb.save(out + "_master_4k.png")
    q = 95
    while True:
        rgb.save(out + ".jpg", quality=q, optimize=True)
        if os.path.getsize(out + ".jpg") < t["max_bytes"] * 0.95 or q < 55: break
        q -= 4
    return out + ".jpg"


def feed_preview(thumb_path, out):
    """The thumbnail at home-feed and sidebar sizes - if the words do not survive here, they do not work."""
    im = Image.open(thumb_path).convert("RGB")
    sizes = [(360, 202), (246, 138), (168, 94)]
    sheet = Image.new("RGB", (sum(w for w, _ in sizes) + 40, 222), "#0f0f0f")
    x = 10
    for w, h in sizes:
        sheet.paste(im.resize((w, h), Image.LANCZOS), (x, 10)); x += w + 10
    sheet.save(out, quality=90)
    return out


def sharpness(path):
    from PIL import ImageStat
    im = Image.open(path).convert("L").resize((480, 270))
    edges = ImageStat.Stat(im.filter(ImageFilter.FIND_EDGES))
    st = ImageStat.Stat(im)
    return round(edges.mean[0] * 0.7 + st.stddev[0] * 0.3, 2)
