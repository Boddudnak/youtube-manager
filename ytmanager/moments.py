"""Rank highlight moments (Shorts candidates) and find dead spans (loading screens, menus, pauses)."""
import os, statistics
from . import core, media

DARK_LUMA, STATIC_MOTION = 18.0, 0.4


def _rank(xs):
    s = sorted(xs); n = len(s) - 1 or 1
    import bisect
    return [bisect.bisect_left(s, x) / n for x in xs]


def _smooth(xs, w):
    out, acc = [], 0.0
    q = []
    for x in xs:
        q.append(x); acc += x
        if len(q) > w: acc -= q.pop(0)
        out.append(acc / len(q))
    h = w // 2
    return out[h:] + [out[-1]] * h


def per_second(sig):
    loud, motion, scene, luma = sig["loudness_lufs"], sig["motion"], sig["scene"], sig["luma"]
    n = len(loud)
    dead = [luma[i] < DARK_LUMA or (motion[i] < STATIC_MOTION and loud[i] < -45) for i in range(n)]
    lr, mr = _rank(loud), _rank(motion)
    punch = []
    for i in range(n):
        base = statistics.median(loud[max(0, i - 10):i] or [loud[i]])
        punch.append(max(0.0, min(1.0, (loud[i] - base) / 15)))
    cuts = [1.0 if s >= 8 else 0.0 for s in scene]
    cutd = _smooth(cuts, 7)
    raw = [0 if dead[i] else 0.35 * lr[i] + 0.30 * punch[i] + 0.25 * mr[i] + 0.10 * min(1, cutd[i] * 3) for i in range(n)]
    return _smooth(raw, 5), dead, cuts


def dead_spans(dead, min_len):
    spans, start = [], None
    for i, d in enumerate(dead + [False]):
        if d and start is None: start = i
        if not d and start is not None:
            if i - start >= min_len: spans.append((start, i))
            start = None
    return spans


def find(job, length=None, count=10, min_dead=8):
    sig = core.load_json(core.job_dir(job["id"], "analysis", "signals.json"))
    if not sig: core.die("run analyze first")
    cfg = core.config("brand")["shorts"]
    length = int(length or cfg["target_seconds"])
    score, dead, cuts = per_second(sig)
    n = len(score)
    win = [statistics.fmean(score[i:i + length]) for i in range(max(1, n - length))]
    taken, cands = [], []
    for i in sorted(range(len(win)), key=lambda i: -win[i]):
        if len(cands) >= count: break
        if any(i < e + 10 and i + length > s - 10 for s, e in taken): continue
        df = sum(dead[i:i + length]) / length
        if df > 0.15: continue
        s, e = i, min(n, i + length)
        near = [k for k in range(max(0, s - 4), s + 3) if cuts[k]]           # start on a cut if one is close
        if near: s = near[-1]
        near = [k for k in range(e - 3, min(n, e + 4)) if cuts[k]]
        if near: e = near[0]
        e = max(e, s + cfg["min_seconds"]); e = min(e, s + cfg["max_seconds"])
        peak = max(range(s, e), key=lambda k: score[k])
        taken.append((s, e))
        cands.append({"rank": len(cands) + 1, "start": float(s), "end": float(e), "peak": float(peak),
                      "score": round(win[i], 3), "dead_fraction": round(df, 2),
                      "label": f"{core.mmss(s)}-{core.mmss(e)}"})
    spans = dead_spans(dead, min_dead)
    res = {"length": length, "candidates": cands,
           "dead_spans": [{"start": float(s), "end": float(e), "seconds": e - s,
                           "kind": "dark" if statistics.fmean(sig["luma"][s:e]) < DARK_LUMA else "static"} for s, e in spans]}
    res["sheet"] = _sheet(job, cands)
    core.save_json(core.job_dir(job["id"], "analysis", "moments.json"), res)
    core.mark(job, "moments", candidates=len(cands), dead_spans=len(spans))
    return res


def _sheet(job, cands):
    """One row per candidate: start / peak / end frames, so moments can be judged by eye."""
    from PIL import Image, ImageDraw, ImageFont
    if not cands: return None
    info, src = job["probe"], job["source"]["path"]
    out = core.job_dir(job["id"], "analysis", "moments")
    os.makedirs(out, exist_ok=True)
    tw, th = 400, 225
    sheet = Image.new("RGB", (3 * tw + 160, len(cands) * (th + 8)), "#0A0A0F")
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(core.config("brand")["fonts"]["label"], 22)
    for r, c in enumerate(cands):
        y = r * (th + 8)
        d.text((8, y + 8), f"#{c['rank']}", fill="#E53935", font=font)
        d.text((8, y + 40), c["label"], fill="#E6E6F0", font=font)
        d.text((8, y + 72), f"score {c['score']}", fill="#E6E6F0", font=font)
        for k, t in enumerate((c["start"] + 1, c["peak"], c["end"] - 1)):
            p = os.path.join(out, f"m{c['rank']:02d}_{k}.jpg")
            media.grab_frame(src, t, p, info, width=tw)
            im = Image.open(p); im.thumbnail((tw, th)); sheet.paste(im, (160 + k * tw, y))
    path = core.job_dir(job["id"], "analysis", "moments_sheet.jpg")
    sheet.save(path, quality=88)
    return path
