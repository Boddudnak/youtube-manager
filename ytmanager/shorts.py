"""Vertical Shorts cut from the recording: plan up to N per recording, render 1080x1920 with brand overlays."""
import os
from . import core, media, graphics

LAYOUTS = ("square", "blur", "crop", "fit")


def plan_add(job, start, end, hook, layout=None, zoom=1.0, crop_x=0.5, note=""):
    cfg = core.config("brand")["shorts"]
    shorts = job.setdefault("shorts", [])
    if len(shorts) >= cfg["max_per_recording"]:
        core.die(f"already {len(shorts)} Shorts planned - the limit is {cfg['max_per_recording']} per recording "
                 "(remove one with `shorts remove`)")
    s, e = core.parse_time(start), core.parse_time(end)
    if not cfg["min_seconds"] <= e - s <= cfg["max_seconds"]:
        core.die(f"a Short must be {cfg['min_seconds']}-{cfg['max_seconds']}s, this is {e - s:.1f}s")
    if e > job["probe"]["duration"] + 0.5: core.die("end is past the end of the recording")
    for o in shorts:
        if s < o["end"] and e > o["start"]: core.die(f"overlaps Short {o['n']} ({core.mmss(o['start'])}-{core.mmss(o['end'])})")
    layout = layout or cfg["default_layout"]
    if layout not in LAYOUTS: core.die(f"layout must be one of {LAYOUTS}")
    n = max([o["n"] for o in shorts], default=0) + 1
    shorts.append({"n": n, "start": s, "end": e, "hook": hook, "layout": layout, "zoom": zoom, "crop_x": crop_x, "note": note})
    core.mark(job, "shorts", status="planned", count=len(shorts))
    return shorts[-1]


def plan_remove(job, n):
    job["shorts"] = [o for o in job.get("shorts", []) if o["n"] != n]
    core.mark(job, "shorts", status="planned", count=len(job["shorts"]))


def _vf(info, sh, W, H, grade=""):
    sdr = media.sdr_chain(info, 1920, grade)
    fps = 60 if info.get("fps", 30) >= 50 else 30
    if sh["layout"] == "crop":
        x = f"(iw-{W})*{sh['crop_x']}"
        base = f"[0:v]{sdr},scale=-2:{H},crop={W}:{H}:{x}:0,fps={fps}[base]"
    elif sh["layout"] == "square":
        # 1:1 gameplay window (full frame width) centred over a blurred fill - action reads big on a phone
        x = f"(iw-{W})*{sh['crop_x']}"
        base = (f"[0:v]{sdr},split[a][b];"
                f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=40,eq=brightness=-0.12[bg];"
                f"[b]scale=-2:{W},crop={W}:{W}:{x}:0[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={fps}[base]")
    elif sh["layout"] == "fit":
        base = f"[0:v]{sdr},scale={W}:-2,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x0A0A0F,fps={fps}[base]"
    else:
        zw = int(W * sh.get("zoom", 1.0)) // 2 * 2
        base = (f"[0:v]{sdr},split[a][b];"
                f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=40,eq=brightness=-0.12[bg];"
                f"[b]scale={zw}:-2,crop={W}:ih[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={fps}[base]")
    return base


def render(job, only=None):
    b = core.config("brand"); cfg = b["shorts"]; W, H = cfg["width"], cfg["height"]
    from . import grade as gr
    info, src = job["probe"], job["source"]["path"]
    out_dir = core.job_dir(job["id"], "shorts"); os.makedirs(out_dir, exist_ok=True)
    wm = graphics.watermark(os.path.join(out_dir, "watermark.png")) if b["watermark"]["shorts"] else None
    done = []
    for sh in job.get("shorts", []):
        if only and sh["n"] != only: continue
        dur = sh["end"] - sh["start"]
        hook = graphics.hook_card(sh["hook"], os.path.join(out_dir, f"short{sh['n']}_hook.png"), W, H)
        out = os.path.join(out_dir, f"{job['id']}-short{sh['n']}.mp4")
        core.assert_not_original(job, out)
        g = _vf(info, sh, W, H, gr.chain(job, sh["start"], dur))
        g += f";[base][1:v]overlay=0:0:enable='lt(t,{cfg['hook_seconds']})'[h]"
        last = "h"
        if wm:
            g += f";[h][2:v]overlay=40:190[w]"; last = "w"
        g += f";[{last}]fade=t=out:st={dur - 0.35:.2f}:d=0.35[v]"
        inputs = ["-ss", f"{sh['start']:.3f}", "-t", f"{dur:.3f}", "-i", src, "-i", hook] + (["-i", wm] if wm else [])
        audio = []
        if info.get("acodec"):
            g += (f";[0:a]loudnorm=I={cfg['loudness_lufs']}:TP=-1.5:LRA=11,aresample=48000,"
                  f"afade=t=in:d=0.15,afade=t=out:st={dur - 0.5:.2f}:d=0.5[a]")
            audio = ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
        cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-nostats", "-progress", "pipe:1", "-y", *inputs,
               "-filter_complex", g, "-map", "[v]", *audio, "-c:v", *media.h264_encoder(), "-pix_fmt", "yuv420p",
               "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
               "-movflags", "+faststart", "-t", f"{dur:.3f}", out]
        media.run_progress(cmd, dur, f"Short {sh['n']}")
        p = media.probe(out)
        if (p["width"], p["height"]) != (W, H): core.die(f"Short {sh['n']} rendered at {p['width']}x{p['height']}")
        sh.update(path=out, duration=round(p["duration"], 2))
        preview = os.path.join(out_dir, f"short{sh['n']}_preview.jpg")
        media.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-ss", "1.0", "-i", out, "-frames:v", "1", "-vf", "scale=540:-2", preview])
        sh["preview"] = preview
        done.append(sh)
    core.mark(job, "shorts", status="done" if all(s.get("path") for s in job.get("shorts", [])) else "partial",
              count=len(job.get("shorts", [])))
    return done
