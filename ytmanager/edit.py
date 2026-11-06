"""Long-form edit: an EDL of cuts (loading screens, menus, dead air), rendered without touching the original.

copy mode (default) cuts on keyframes with no re-encode - lossless, keeps 4K HDR exactly as recorded.
encode mode is frame-accurate: HDR -> libx265 10-bit with HDR10 tags, SDR -> hardware H.264.
An approved SDR grade (grade.py) forces encode mode: graded HEVC at a high bitrate, tagged SDR bt709.
"""
import os
from . import core, media

PAD = 1.0  # seconds of each dead span kept on both sides so cuts do not feel abrupt


def plan(job, min_dead=8, trim_head=True, trim_tail=True, retries=True):
    mom = core.load_json(core.job_dir(job["id"], "analysis", "moments.json"))
    if not mom: core.die("run moments first")
    dur = job["probe"]["duration"]
    cuts = []
    for s in mom["dead_spans"]:
        if s["seconds"] < min_dead: continue
        a = 0.0 if (trim_head and s["start"] <= 2) else s["start"] + PAD
        b = dur if (trim_tail and s["end"] >= dur - 2) else s["end"] - PAD
        if b - a >= 3: cuts.append({"start": round(a, 2), "end": round(b, 2), "reason": f"{s['kind']} {s['seconds']:.0f}s"})
    review = []
    if retries:
        from . import retries as rt
        for r in rt.find(job)["retries"]:
            (cuts if r["auto"] else review).append({"start": r["start"], "end": r["end"], "reason": f"retry: {r['why']}"})
    edl = {"mode": "copy", "cuts": cuts, "keep": keep_from_cuts(cuts, dur), "review": review}
    edl["kept_seconds"] = round(sum(e - s for s, e in edl["keep"]), 2)
    core.save_json(core.job_dir(job["id"], "edit", "edl.json"), edl)
    return edl


def keep_from_cuts(cuts, dur):
    keep, t = [], 0.0
    for c in sorted(cuts, key=lambda c: c["start"]):
        if c["start"] > t: keep.append([round(t, 3), round(c["start"], 3)])
        t = max(t, c["end"])
    if dur - t > 0.5: keep.append([round(t, 3), round(dur, 3)])
    return keep


def to_edited(t, keep):
    """Map a source timestamp to the edited timeline (None if it was cut)."""
    acc = 0.0
    for s, e in keep:
        if s <= t <= e: return acc + (t - s)
        acc += e - s
    return None


def render(job, mode=None):
    edl_path = core.job_dir(job["id"], "edit", "edl.json")
    edl = core.load_json(edl_path)
    if edl is None: core.die("run `edit plan` first")
    edl["keep"] = keep_from_cuts(edl["cuts"], job["probe"]["duration"])
    from . import grade
    look = grade.chain(job)
    mode = "encode" if look else (mode or edl.get("mode", "copy"))
    info, src = job["probe"], job["source"]["path"]
    if not edl["cuts"] and not look:
        job["long_form"] = {"path": src, "mode": "passthrough", "duration": info["duration"], "keep": edl["keep"]}
        core.mark(job, "edit", mode="passthrough", note="no cuts - the original is uploaded as-is (read-only)")
        return job["long_form"]
    ext = os.path.splitext(src)[1].lower() if mode == "copy" else ".mp4"
    if ext not in (".mp4", ".webm", ".mkv", ".mov"): ext = ".mkv"
    work = core.job_dir(job["id"], "edit", "parts"); os.makedirs(work, exist_ok=True)
    out = core.job_dir(job["id"], "edit", f"{job['id']}-long{ext}")
    core.assert_not_original(job, out)
    parts = []
    for i, (s, e) in enumerate(edl["keep"]):
        p = os.path.join(work, f"part{i:03d}{ext}")
        if mode == "copy":
            cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-ss", f"{s:.3f}", "-to", f"{e:.3f}", "-i", src,
                   "-map", "0:v:0", "-map", "0:a?", "-c", "copy", "-avoid_negative_ts", "make_zero", p]
        else:
            if look:
                v = ["-vf", media.sdr_chain(info, grade=grade.chain(job, s, e - s)), "-c:v", *grade.hevc_encoder(), "-tag:v", "hvc1",
                     "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
            elif info.get("hdr"):
                v = ["-c:v", "libx265", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p10le",
                     "-x265-params", "hdr10=1:repeat-headers=1:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc",
                     "-color_primaries", "bt2020", "-color_trc", "smpte2084", "-colorspace", "bt2020nc", "-tag:v", "hvc1"]
            else:
                v = ["-c:v", *media.h264_encoder(), "-pix_fmt", "yuv420p"]
            cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-ss", f"{s:.3f}", "-i", src, "-t", f"{e - s:.3f}",
                   "-map", "0:v:0", "-map", "0:a?", *v, "-c:a", "aac", "-b:a", "256k", p]
        print(f"  part {i + 1}/{len(edl['keep'])}: {core.mmss(s)}-{core.mmss(e)}", flush=True)
        if mode == "copy": media.run(cmd)
        else: media.run_progress(cmd[:4] + ["-nostats", "-progress", "pipe:1"] + cmd[4:], e - s, f"part {i + 1}")
        parts.append(p)
    lst = os.path.join(work, "concat.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in parts: f.write(f"file '{os.path.basename(p)}'\n")
    media.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt",
               "-c", "copy", *(["-movflags", "+faststart"] if ext in (".mp4", ".mov") else []), out], cwd=work)
    for p in parts: os.remove(p)
    dur = media.probe(out)["duration"]
    job["long_form"] = {"path": out, "mode": mode, "duration": dur, "keep": edl["keep"]}
    core.mark(job, "edit", mode=mode, cuts=len(edl["cuts"]), duration=round(dur, 1),
              removed_seconds=round(info["duration"] - dur, 1), graded=bool(look))
    return job["long_form"]


def chapter_points(job, target=None):
    """Chapter boundaries on the EDITED timeline: transcript (via yt-chapters) or visual section breaks."""
    import json, subprocess, sys
    keep = job.get("long_form", {}).get("keep") or [[0, job["probe"]["duration"]]]
    total = sum(e - s for s, e in keep)
    target = target or max(3, min(10, int(total // 300) + 1))
    tpath = core.job_dir(job["id"], "analysis", "transcript.json")
    segs = core.load_json(tpath, {}).get("segments", [])
    if len(segs) >= 12:
        mapped = [{"start": to_edited(r["start"], keep), "end": to_edited(r["end"], keep), "text": r["text"]} for r in segs]
        mapped = [r for r in mapped if r["start"] is not None and r["end"] is not None]
        mp = core.job_dir(job["id"], "edit", "transcript_edited.json")
        core.save_json(mp, {"segments": mapped})
        p = subprocess.run([sys.executable, os.path.join(core.SKILLS, "yt-chapters", "chapters.py"), mp, "--target", str(target), "--json"],
                           capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
        if p.returncode == 0:
            pts = [c["start"] for c in json.loads(p.stdout)["chapters"]]
            return _with_frames(job, pts, total, keep, "transcript")
    sig = core.load_json(core.job_dir(job["id"], "analysis", "signals.json"))
    cands = []
    for i in range(1, len(sig["scene"])):
        after_dark = min(sig["luma"][max(0, i - 3):i] or [99]) < 18 and sig["luma"][i] >= 18
        w = sig["scene"][i] + (40 if after_dark else 0)
        t = to_edited(float(i), keep)
        if t is not None and w >= 10: cands.append((w, t))
    cands.sort(reverse=True)
    pts = [0.0]
    min_gap = max(30.0, total / (target * 2))
    for _, t in cands:
        if len(pts) >= target: break
        if all(abs(t - p) >= min_gap for p in pts) and total - t >= 30: pts.append(t)
    return _with_frames(job, sorted(pts), total, keep, "visual")


def _from_edited(t, keep):
    acc = 0.0
    for s, e in keep:
        if t <= acc + (e - s): return s + (t - acc)
        acc += e - s
    return keep[-1][1]


def _with_frames(job, pts, total, keep, source):
    out = core.job_dir(job["id"], "edit", "chapters"); os.makedirs(out, exist_ok=True)
    rows = []
    for k, t in enumerate(pts):
        end = pts[k + 1] if k + 1 < len(pts) else total
        p = os.path.join(out, f"c{k:02d}.jpg")
        media.grab_frame(job["source"]["path"], _from_edited(t + 2, keep), p, job["probe"], width=640)
        rows.append({"start": round(t, 1), "label": core.mmss(t), "seconds": round(end - t, 1), "title": "", "frame": p})
    res = {"source": source, "valid": len(rows) >= 3 and rows[0]["start"] == 0 and all(r["seconds"] >= 10 for r in rows),
           "chapters": rows}
    core.save_json(core.job_dir(job["id"], "edit", "chapters.json"), res)
    return res
