"""Optional colour grade for SDR recordings: shadow lift (curves), brightness, contrast, saturation, gamma (eq), vibrance + light sharpening (unsharp).

The channel default look is brand.json -> grade; job.json -> grade holds per-job tweaks and the approval.
Nothing is graded until the user has seen the BEFORE/AFTER preview and approved it (`grade approve`).
HDR sources are never graded here. Graded output stays SDR bt709 and is never labelled HDR.
"""
import os
from . import core, media

KEYS = ("brightness", "contrast", "saturation", "gamma", "sharpen", "shadows", "vibrance", "auto", "night", "dim", "denoise")
DEFAULT = {"brightness": 0.02, "contrast": 1.06, "saturation": 1.15, "gamma": 1.0, "sharpen": 0.35, "shadows": 0.0, "vibrance": 0.0,
           "auto": False, "night": 1.03, "dim": 1.07, "denoise": 0.0}


def settings(job):
    g = {**DEFAULT, **{k: v for k, v in core.config("brand").get("grade", {}).items() if k in KEYS}}
    g.update({k: v for k, v in job.get("grade", {}).items() if k in KEYS})
    return g


def filters(g, cmdfile=None):
    f = []
    if cmdfile: f.append(f"sendcmd=f='{cmdfile.replace(os.sep, '/').replace(':', chr(92) + ':')}'")
    s = g.get("shadows") or 0
    if s:  # lift the low mids only; the toe (0-3%) stays put so sensor/compression noise in the blacks is not raised into grain
        f.append(f"curves=all='0/0 0.03/0.03 0.12/{0.12 + s * 0.5:.3f} 0.3/{0.3 + s * 0.6:.3f} 0.55/{0.55 + s * 0.2:.3f} 1/1'")
    if g.get("denoise"): f.append(f"hqdn3d={g['denoise']}:0:{g['denoise'] * 2}:0")
    f.append(f"eq@grade=brightness={g['brightness']}:contrast={g['contrast']}:saturation={g['saturation']}:gamma={g['gamma']}")
    if g.get("vibrance"): f.append(f"vibrance=intensity={g['vibrance']}")  # boosts muted colours more than strong ones
    if g.get("sharpen"):  # cas sharpens edges adaptively - far less grain in flat dark areas than unsharp
        f.append(f"cas={g['sharpen']}" if g.get("auto") else f"unsharp=5:5:{g['sharpen']}:5:5:0")
    return ",".join(f)


def exposure(job, g):
    """Scene-aware gamma from grade/luma.json (keyframe brightness): deep night gets a small lift so it stays night,
    dim interiors get the most, daylight none. Smoothed so it eases like a camera's auto-exposure. [(t, gamma)]"""
    import numpy as np
    rows = core.load_json(core.job_dir(job["id"], "grade", "luma.json"), [])
    if not rows: return []
    t = np.array([r["t"] for r in rows]); m = np.array([r["mean"] for r in rows])
    m = np.array([np.median(m[max(0, i - 3): i + 4]) for i in range(len(m))])
    gam = np.interp(m, [20, 35, 60, 90], [g["night"], g["dim"], g["dim"], 1.0]) * g["gamma"]
    gam = np.convolve(np.pad(gam, 3, mode="edge"), np.ones(7) / 7, mode="valid")
    return list(zip(t.tolist(), gam.tolist()))


def chain(job, start=0.0, dur=None):
    """The approved grade as a filter string ('' when the job is HDR, ungraded or not approved yet).
    With auto on, start/dur (source seconds) select the scene-aware gamma for that span, written as sendcmd commands."""
    if job["probe"].get("hdr") or not job.get("grade", {}).get("approved"): return ""
    return _filters_for(job, settings(job), start, dur)


def _filters_for(job, g, start, dur):
    ex = exposure(job, g) if g.get("auto") else []
    if not ex: return filters(g)
    import numpy as np
    dur = dur if dur is not None else job["probe"]["duration"] - start
    ts = np.arange(0.0, dur + 0.5, 0.5)
    vals = np.interp(ts + start, [a for a, _ in ex], [b for _, b in ex])
    g = {**g, "gamma": round(float(vals[0]), 3)}
    p = core.job_dir(job["id"], "grade", f"exposure_{start:.2f}.cmd")
    with open(p, "w", encoding="utf-8") as f:
        f.writelines(f"{x:.2f} eq@grade gamma {v:.3f};\n" for x, v in zip(ts, vals))
    return filters(g, p)


def hevc_encoder():
    """brand.json -> grade.encoder (picked by benchmark on this PC), else libx265."""
    e = core.config("brand").get("grade", {}).get("encoder")
    return e if e else ["libx265", "-preset", "medium", "-b:v", "45M", "-maxrate", "60M", "-bufsize", "90M"]


def preview(job, at=None, seconds=20, **tweak):
    """~20 s BEFORE|AFTER split-screen clip plus full-frame before/after stills, for the user to judge the look."""
    if job["probe"].get("hdr"): core.die("HDR source - the SDR grade does not apply")
    gj = job.setdefault("grade", {})
    changed = {k: v for k, v in tweak.items() if k in KEYS and v is not None}
    if changed: gj.update(changed); gj["approved"] = False
    g = settings(job)
    src, info = job["source"]["path"], job["probe"]
    if at is None:
        mom = core.load_json(core.job_dir(job["id"], "analysis", "moments.json"), {})
        top = (mom.get("candidates") or [{}])[0]
        at = top.get("start", info["duration"] / 2)
    at = core.parse_time(at); f = _filters_for(job, g, at, seconds)
    out = core.job_dir(job["id"], "grade"); os.makedirs(out, exist_ok=True)
    clip = os.path.join(out, "before_after.mp4")
    font = core.config("brand")["fonts"]["label"].replace(":", "\\:")
    lab = lambda t, x: (f"drawtext=fontfile='{font}':text='{t}':x={x}:y=24:fontsize=44:fontcolor=white:"
                        "box=1:boxcolor=black@0.55:boxborderw=12")
    graph = (f"[0:v]split[a][b];[b]{f}[g];"
             f"[a]scale=1920:-2,crop=iw/2:ih:0:0,{lab('BEFORE', 24)}[l];"
             f"[g]scale=1920:-2,crop=iw/2:ih:iw/2:0,{lab('AFTER', 'w-tw-24')}[r];"
             "[l][r]hstack,drawbox=x=iw/2-1:y=0:w=2:h=ih:color=white@0.8:t=fill,format=yuv420p[v]")
    media.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-ss", f"{at:.3f}", "-t", f"{seconds:.3f}", "-i", src,
               "-filter_complex", graph, "-map", "[v]", "-map", "0:a?", "-c:v", *media.h264_encoder(),
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", clip])
    stills = []
    for k, t in enumerate((at + 2, at + seconds / 2, at + seconds - 2)):
        p = os.path.join(out, f"still{k + 1}.jpg")
        pre = max(0.0, t - 2.0)
        media.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-ss", f"{pre:.3f}", "-i", src, "-ss", f"{t - pre:.3f}",
                   "-frames:v", "1", "-filter_complex",
                   f"[0:v]split[a][b];[b]{_filters_for(job, g, pre, 4.0)},scale=1280:-2,{lab('AFTER', 24)}[g];[a]scale=1280:-2,{lab('BEFORE', 24)}[o];[o][g]vstack",
                   "-q:v", "2", p])
        stills.append(p)
    gj.update({"preview": clip, "stills": stills, "preview_at": round(at, 2), "filters": f})
    core.save_job(job)
    return {"settings": g, "filters": f, "clip": clip, "stills": stills, "approved": gj.get("approved", False)}


def approve(job, on=True):
    if on and not job.get("grade", {}).get("preview"): core.die("render `grade preview` and show it to the user first")
    gj = job.setdefault("grade", {})
    gj.update({**settings(job), "approved": on, "approved_at": core.now() if on else None})
    core.save_job(job)
    return gj
