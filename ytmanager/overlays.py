"""Live-stream graphics for OBS: full-screen break cards and reaction pop-ups, in the channel brand.

Everything is drawn at the OBS canvas size (4K) into assets/stream/. The OBS side (scenes, hotkeys) is
wired up separately - see `ytm.py overlays`.
"""
import glob, os
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageFont
from . import core, graphics as g

W, H = 3840, 2160
OUT = os.path.join(core.ROOT, "assets", "stream")
SCREENS = {  # file: (headline, subtitle)
    "starting": ("STARTING SOON", ""),   # headline only on Starting Soon and BRB
    "brb": ("BE RIGHT BACK", ""),
    "ending": ("THANKS FOR WATCHING", "See you in the next mission"),
}
REACTIONS = {  # file: (text, glow colour key, emoji)
    "letsgo": ("LET'S GO!", "primary", "🔥"),
    "gg": ("GG", "secondary", "🏆"),
    "clutch": ("CLUTCH!", "primary", "🎯"),
    "noway": ("NO WAY!", "secondary", "😱"),
    "rip": ("RIP", "primary", "💀"),
    "subscribe": ("CHAT DECIDES", "secondary", "🗳️"),  # Numpad 6; was SUBSCRIBE! - no begging (brand.json engagement)
}


def _backdrop():
    """A blurred, darkened gameplay frame from the newest job's thumbnail candidates; plain brand colour if none."""
    frames = sorted(glob.glob(os.path.join(core.ROOT, "library", "*", "thumbs", "candidates", "*.jpg")), key=os.path.getmtime)
    b = g.brand()["colors"]
    if not frames: return Image.new("RGBA", (W, H), b["background"])
    im = Image.open(frames[-1]).convert("RGB").resize((W, H), Image.LANCZOS)
    im = ImageEnhance.Brightness(im.filter(ImageFilter.GaussianBlur(28))).enhance(0.35)
    shade = Image.new("RGBA", (W, H), b["background"] + "99")
    return Image.alpha_composite(im.convert("RGBA"), shade)


def _centered(canvas, text, font, y, fill, glow):
    w = font.getbbox(text)[2] - font.getbbox(text)[0]
    g._glow_text(canvas, [(((W - w) // 2, y), text)], font, fill, glow, g.brand()["colors"]["stroke"], 14, 0)


def _screen_fg(headline, subtitle):
    """Crest, headline and subtitle on a transparent 4K layer."""
    b = g.brand(); c = b["colors"]
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.alpha_composite(g.logo_badge(620), ((W - 620) // 2, 330))
    font = g._fit_font([headline], b["fonts"]["headline"], W - 600, 300)
    _centered(canvas, headline, font, 1060 if subtitle else 1120, c["text"], c["primary"])
    if not subtitle: return canvas
    sub = ImageFont.truetype(b["fonts"]["label"], 96)
    w = sub.getbbox(subtitle)[2] - sub.getbbox(subtitle)[0]
    d = ImageDraw.Draw(canvas)
    d.text(((W - w) // 2, 1480), subtitle, font=sub, fill=c["silver"])
    d.rectangle(((W - 900) // 2, 1420, (W + 900) // 2, 1428), fill=c["primary"])
    return canvas


def screen(name, headline, subtitle):
    canvas = _backdrop(); canvas.alpha_composite(_screen_fg(headline, subtitle))
    out = os.path.join(OUT, f"{name}.png"); canvas.convert("RGB").save(out); return out


def reaction(name, text, glow_key, emoji=""):
    """Transparent full-canvas PNG with a glowing word in the lower-middle, on a soft dark band."""
    b = g.brand(); c = b["colors"]
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(band).rounded_rectangle((W // 2 - 1100, 1380, W // 2 + 1100, 1800), 60, fill=(7, 6, 12, 150))
    canvas.alpha_composite(band.filter(ImageFilter.GaussianBlur(6)))
    font = g._fit_font([text], b["fonts"]["headline"], 1450, 330)
    _centered(canvas, text, font, 1420, c["text"], c[glow_key])
    canvas.alpha_composite(g.logo_badge(260), (W // 2 - 1100 + 40, 1460))
    if emoji:  # colour emoji from Segoe UI Emoji, mirrored to the crest on the right
        ef = ImageFont.truetype("C:/Windows/Fonts/seguiemj.ttf", 200)
        ImageDraw.Draw(canvas).text((W // 2 + 1100 - 300, 1495), emoji, font=ef, embedded_color=True)
    out = os.path.join(OUT, f"react_{name}.png"); canvas.save(out); return out


# ------------------------------------------------------------------ motion (CPU only - libx264 / libvpx, so a GPU render can keep running)

AW, AH, FPS = 1920, 1080, 30  # animated layers are drawn at 1080p; OBS scales them onto the 4K canvas


def _ffmpeg(frames_dir, out, alpha):
    import subprocess
    enc = (["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "30", "-auto-alt-ref", "0"] if alpha
           else ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "slow"])
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-i", os.path.join(frames_dir, "%04d.png"), *enc, out], check=True)


def screen_loop(name, headline, subtitle, seconds=12):
    """Seamless loop: backdrop drifts in and back out, the crest glow breathes, embers rise and wrap around."""
    import math, random, shutil, tempfile
    fg = _screen_fg(headline, subtitle).resize((AW, AH), Image.LANCZOS)
    base = _backdrop().convert("RGB")
    b = g.brand(); c = b["colors"]
    violet = tuple(int(c["primary"][i:i + 2], 16) for i in (1, 3, 5))
    rnd = random.Random(name)
    embers = [(rnd.random(), rnd.random(), rnd.uniform(3, 7), rnd.uniform(0.5, 1)) for _ in range(90)]
    n = seconds * FPS; tmp = tempfile.mkdtemp()
    for i in range(n):
        t = i / n; ph = math.sin(2 * math.pi * t)                      # -1..1, returns to start: seamless
        z = 1.06 + 0.04 * ph; cw, ch = int(W / z), int(H / z)
        x0, y0 = (W - cw) // 2 + int(60 * ph), (H - ch) // 2
        frame = base.crop((x0, y0, x0 + cw, y0 + ch)).resize((AW, AH), Image.LANCZOS).convert("RGBA")
        glow = Image.new("RGBA", (AW, AH), (0, 0, 0, 0)); d = ImageDraw.Draw(glow)
        r = 190 + 25 * (0.5 + 0.5 * math.sin(4 * math.pi * t))         # crest halo breathes twice per loop
        d.ellipse((AW / 2 - r, 165 + 155 - r, AW / 2 + r, 165 + 155 + r), fill=violet + (int(110 + 60 * math.sin(4 * math.pi * t)),))
        for ex, ey, s, a in embers:
            y = (ey - t) % 1.0
            d.ellipse((ex * AW - s, y * AH - s, ex * AW + s, y * AH + s), fill=violet + (int(255 * a * min(1, y * 3)),))
        frame.alpha_composite(glow.filter(ImageFilter.GaussianBlur(6)))
        frame.alpha_composite(fg)
        frame.convert("RGB").save(os.path.join(tmp, f"{i:04d}.png"))
    out = os.path.join(OUT, f"{name}_loop.mp4"); _ffmpeg(tmp, out, alpha=False); shutil.rmtree(tmp); return out


def reaction_clip(name, text, glow_key, emoji="", seconds=2.6):
    """Transparent WebM: pops in with an overshoot, glow pulses, slight shake on the loud ones, fades out to nothing."""
    import math, shutil, tempfile
    still = Image.open(os.path.join(OUT, f"react_{name}.png")).resize((AW, AH), Image.LANCZOS)
    box = still.getbbox(); card = still.crop(box); cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    n = int(seconds * FPS); tmp = tempfile.mkdtemp(); loud = name in ("noway", "letsgo", "clutch")
    for i in range(n):
        t = i / FPS
        if t < 0.35: s = 0.4 + 0.75 * math.sin(t / 0.35 * math.pi / 2) + 0.12 * math.sin(t / 0.35 * math.pi)  # overshoot
        else: s = 1.0 + 0.025 * math.sin((t - 0.35) * 2 * math.pi * 2)                                        # breathe
        a = min(1, t / 0.15) * (1 if t < seconds - 0.45 else max(0, (seconds - t) / 0.45))
        dx = int(7 * math.sin(t * 60)) if loud and 0.35 < t < 0.9 else 0
        c = card.resize((max(1, int(card.width * s)), max(1, int(card.height * s))), Image.LANCZOS)
        if a < 1: c.putalpha(Image.eval(c.getchannel("A"), lambda v: int(v * a)))
        frame = Image.new("RGBA", (AW, AH), (0, 0, 0, 0))
        frame.alpha_composite(c, (int(cx - c.width / 2) + dx, int(cy - c.height / 2)))
        frame.save(os.path.join(tmp, f"{i:04d}.png"))
    out = os.path.join(OUT, f"react_{name}.webm"); _ffmpeg(tmp, out, alpha=True); shutil.rmtree(tmp); return out


def build(motion=True):
    os.makedirs(OUT, exist_ok=True)
    outs = [screen(k, *v) for k, v in SCREENS.items()] + [reaction(k, *v) for k, v in REACTIONS.items()]
    if motion:
        outs += [screen_loop(k, *v) for k, v in SCREENS.items()] + [reaction_clip(k, *v) for k, v in REACTIONS.items()]
    for o in outs: print(o)
    return outs
