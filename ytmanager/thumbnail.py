"""Thumbnail candidates (sharp, high-action frames) and final branded thumbnails."""
import os
from . import core, media, graphics, grade


def candidates(job, count=12):
    from PIL import Image, ImageDraw, ImageFont
    info, src = job["probe"], job["source"]["path"]
    mom = core.load_json(core.job_dir(job["id"], "analysis", "moments.json"), {})
    times = [c["peak"] for c in mom.get("candidates", [])][:8]
    for s in job.get("shorts", []): times.append((s["start"] + s["end"]) / 2)
    dur = info["duration"]
    times += [dur * (i + 0.5) / 6 for i in range(6)]
    keep = job.get("long_form", {}).get("keep")
    if keep: times = [t for t in times if any(s <= t <= e for s, e in keep)]
    picked = []
    for t in sorted(times):
        if all(abs(t - p) > 8 for p in picked): picked.append(t)
    out = core.job_dir(job["id"], "thumbs", "candidates"); os.makedirs(out, exist_ok=True)
    rows = []
    for i, t in enumerate(picked[:count]):
        p = os.path.join(out, f"t{i:02d}.jpg")
        media.grab_frame(src, t, p, info, width=1920, grade=grade.chain(job, t, 1.0))
        rows.append({"index": i, "time": round(t, 2), "frame": p, "sharpness": graphics.sharpness(p)})
    rows.sort(key=lambda r: -r["sharpness"])
    tw, th = 480, 270; cols = 4
    sheet = Image.new("RGB", (cols * tw, ((len(rows) + cols - 1) // cols) * (th + 30)), "#0A0A0F")
    d = ImageDraw.Draw(sheet); font = ImageFont.truetype(core.config("brand")["fonts"]["label"], 22)
    for k, r in enumerate(rows):
        im = Image.open(r["frame"]); im.thumbnail((tw, th))
        x, y = (k % cols) * tw, (k // cols) * (th + 30)
        sheet.paste(im, (x, y + 30)); d.text((x + 6, y + 3), f"#{r['index']}  {core.mmss(r['time'])}  sharp {r['sharpness']}", fill="#E6E6F0", font=font)
    sheet_path = core.job_dir(job["id"], "thumbs", "candidates_sheet.jpg"); sheet.save(sheet_path, quality=88)
    core.save_json(core.job_dir(job["id"], "thumbs", "candidates.json"), rows)
    return sheet_path, rows


def make(job, text, target="long", index=None, time=None, side="left", zoom=1.0):
    info, src = job["probe"], job["source"]["path"]
    if index is not None:
        rows = core.load_json(core.job_dir(job["id"], "thumbs", "candidates.json"), [])
        hit = [r for r in rows if r["index"] == index]
        if not hit: core.die(f"no candidate #{index} - run `thumb candidates` first")
        frame = hit[0]["frame"]
    elif time is not None:
        t = core.parse_time(time)  # native 4K frame - thumbnail.quality_rule: never an upscaled 1080p grab
        frame = media.grab_frame(src, t, core.job_dir(job["id"], "thumbs", f"frame_{target}.png"), info, width=None, grade=grade.chain(job, t, 1.0))
    else:
        core.die("give --index (a candidate) or --time")
    vertical = target.startswith("short")
    n = job.get("mission_number"); kicker = f"Mission {n}" if n else ""
    if vertical and n and job.get("mission"): kicker += f" • {job['mission']}"
    sh = [x for x in job.get("shorts", []) if f"short{x['n']}" == target]
    out = graphics.cinematic(frame, core.job_dir(job["id"], "thumbs", f"{job['id']}-{target}"), kicker, text,
                             vertical=vertical, crop_x=sh[0].get("crop_x", 0.5) if sh else 0.5)
    prev = graphics.feed_preview(out, core.job_dir(job["id"], "thumbs", f"{target}_feed_preview.jpg"))
    job.setdefault("thumbnails", {})[target] = {"path": out, "text": text, "frame": frame, "feed_preview": prev,
                                                "bytes": os.path.getsize(out)}
    core.mark(job, "thumbnail", targets=sorted(job["thumbnails"]))
    return job["thumbnails"][target]
