"""Analyze a recording before anything is cut.

One decode pass produces per-second signals (loudness, motion, scene cuts, brightness). Then a
timestamped contact sheet for visual identification of the game/mission, and an optional transcript
of in-game dialogue (faster-whisper) that also feeds /yt-chapters and on-screen identification.
"""
import json, os, re, statistics
from . import core, media


def _parse_meta(path, keys):
    """ffmpeg metadata=print output -> list of (pts_time, {key: float})."""
    rows, cur = [], None
    if not os.path.exists(path): return rows
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("frame:"):
                m = re.search(r"pts_time:([\d.]+)", line)
                cur = (float(m.group(1)) if m else 0.0, {}); rows.append(cur)
            elif cur and "=" in line:
                k, v = line.strip().split("=", 1)
                if k in keys:
                    try: cur[1][k] = float(v)
                    except ValueError: cur[1][k] = -120.0
    return rows


def signals(job, force=False):
    out = core.job_dir(job["id"], "analysis")
    os.makedirs(out, exist_ok=True)
    sig_path = os.path.join(out, "signals.json")
    if os.path.exists(sig_path) and not force:
        return core.load_json(sig_path)
    info, src = job["probe"], job["source"]["path"]
    vchain = "[0:v]fps=4,scale=320:-2,format=yuv420p,scdet=threshold=100:sc_pass=0,signalstats,metadata=mode=print:file=video_meta.txt[v]"
    cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-nostats", "-progress", "pipe:1", "-y",
           "-hwaccel", "auto", "-i", src]
    graph, maps = vchain, ["-map", "[v]"]
    if info.get("acodec"):
        graph += (";[0:a]aresample=48000,asetnsamples=n=24000:p=0,ebur128=metadata=1,"
                  "ametadata=mode=print:file=audio_meta.txt[a]")
        maps += ["-map", "[a]"]
    cmd += ["-filter_complex", graph, *maps, "-f", "null", "-"]
    print(f"Scanning {core.mmss(info['duration'])} of footage (one pass)...")
    media.run_progress(cmd, info["duration"], "signals", cwd=out)

    dur = info["duration"]; n = max(1, int(dur) + 1)
    motion = [[] for _ in range(n)]; scene = [0.0] * n; luma = [[] for _ in range(n)]
    for t, m in _parse_meta(os.path.join(out, "video_meta.txt"), {"lavfi.scd.mafd", "lavfi.scd.score", "lavfi.signalstats.YAVG"}):
        i = min(n - 1, int(t))
        if "lavfi.scd.mafd" in m: motion[i].append(m["lavfi.scd.mafd"])
        scene[i] = max(scene[i], m.get("lavfi.scd.score", 0.0))
        if "lavfi.signalstats.YAVG" in m: luma[i].append(m["lavfi.signalstats.YAVG"])
    loud = [-70.0] * n
    for t, m in _parse_meta(os.path.join(out, "audio_meta.txt"), {"lavfi.r128.M"}):
        i = min(n - 1, int(t))
        loud[i] = max(loud[i] if loud[i] > -70 else -70.0, max(-70.0, m.get("lavfi.r128.M", -70.0)))
    sig = {
        "step": 1.0, "duration": dur,
        "loudness_lufs": [round(x, 1) for x in loud],
        "motion": [round(statistics.fmean(x), 2) if x else 0.0 for x in motion],
        "scene": [round(x, 1) for x in scene],
        "luma": [round(statistics.fmean(x), 1) if x else 0.0 for x in luma],
    }
    core.save_json(sig_path, sig)
    for f in ("video_meta.txt", "audio_meta.txt"):
        try: os.remove(os.path.join(out, f))
        except OSError: pass
    return sig


def contact_sheet(job, count=None, cols=6):
    from PIL import Image, ImageDraw, ImageFont
    info, src = job["probe"], job["source"]["path"]
    dur = info["duration"]
    count = count or (24 if dur < 1800 else 36)
    out = core.job_dir(job["id"], "analysis", "frames")
    os.makedirs(out, exist_ok=True)
    times = [(i + 0.5) * dur / count for i in range(count)]
    frames = []
    print(f"Grabbing {count} frames for the contact sheet...")
    for i, t in enumerate(times):
        p = os.path.join(out, f"f{i:02d}_{int(t):05d}s.jpg")
        if not os.path.exists(p): media.grab_frame(src, t, p, info, width=960)
        frames.append((t, p))
    tw = 480; th = int(tw * 9 / 16)
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + 26)), "#0A0A0F")
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(core.config("brand")["fonts"]["label"], 20)
    for k, (t, p) in enumerate(frames):
        im = Image.open(p).convert("RGB"); im.thumbnail((tw, th))
        x, y = (k % cols) * tw, (k // cols) * (th + 26)
        sheet.paste(im, (x, y + 26))
        d.text((x + 6, y + 2), f"#{k:02d}  {core.mmss(t)}", fill="#E6E6F0", font=font)
    path = core.job_dir(job["id"], "analysis", "contact_sheet.jpg")
    sheet.save(path, quality=88)
    return path, [{"index": k, "time": round(t, 2), "frame": p} for k, (t, p) in enumerate(frames)]


def transcribe(job, model=None, force=False):
    out = core.job_dir(job["id"], "analysis")
    jpath = os.path.join(out, "transcript.json")
    if os.path.exists(jpath) and not force: return jpath
    if not job["probe"].get("acodec"): return None
    from faster_whisper import WhisperModel
    wav = os.path.join(out, "audio16k.wav")
    media.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", job["source"]["path"], "-vn", "-ac", "1", "-ar", "16000", wav])
    model = model or core.config("brand").get("whisper_model", "small")
    print(f"Transcribing in-game dialogue (faster-whisper {model}, CPU)...")
    wm = WhisperModel(model, device="cpu", compute_type="int8")
    # hand faster-whisper raw samples: its own PyAV-based loader breaks on newer PyAV releases
    import wave, numpy as np
    with wave.open(wav, "rb") as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0
    segs, meta = wm.transcribe(audio, vad_filter=True, beam_size=1)
    rows = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segs if s.text.strip()]
    core.save_json(jpath, {"language": meta.language, "segments": rows})
    with open(os.path.join(out, "transcript.srt"), "w", encoding="utf-8") as f:
        def ts(x): return f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{int(x % 60):02d},{int(x * 1000 % 1000):03d}"
        for i, r in enumerate(rows, 1): f.write(f"{i}\n{ts(r['start'])} --> {ts(r['end'])}\n{r['text']}\n\n")
    os.remove(wav)
    return jpath


def run(job, transcript=True, force=False):
    sig = signals(job, force)
    sheet, frames = contact_sheet(job)
    tpath = None
    if transcript:
        try: tpath = transcribe(job, force=force)
        except Exception as e: print(f"  transcript skipped: {e}")
    n_speech = len(core.load_json(tpath, {}).get("segments", [])) if tpath else 0
    loud = [x for x in sig["loudness_lufs"] if x > -70]
    summary = {
        "contact_sheet": sheet, "frames": frames, "transcript": tpath, "speech_segments": n_speech,
        "median_loudness": round(statistics.median(loud), 1) if loud else None,
        "dark_seconds": sum(1 for y in sig["luma"] if y < 18),
        "static_seconds": sum(1 for m in sig["motion"] if m < 0.4),
    }
    core.save_json(core.job_dir(job["id"], "analysis", "summary.json"), summary)
    core.mark(job, "analyze", **{k: v for k, v in summary.items() if k != "frames"})
    return summary


def identify(job, game, mission=None, number=None, confidence="high", evidence=""):
    """Record what Claude (or the user) identified from the footage. New games/missions are learned."""
    games = core.config("games")
    prof = core.game_profile(game)
    if not prof:
        prof = {"name": game, "short": game, "aliases": [game.lower()], "hashtags": ["#" + re.sub(r"\W", "", game.title())],
                "tags": [game.lower(), f"{game.lower()} gameplay"], "missions": [], "characters": []}
        games["games"].append(prof); print(f"Learned new game profile: {game}")
    if mission and not any(m["name"].lower() == mission.lower() for m in prof["missions"]):
        for g in games["games"]:
            if g["name"] == prof["name"]:
                g["missions"].append({"number": number, "name": mission, "source": f"job {job['id']}"})
        print(f"Learned mission: {prof['short']} - {mission}")
    core.save_json(os.path.join(core.CONFIG, "games.json"), games)
    job.update(game=prof["name"], mission=mission, mission_number=number, game_confidence=confidence,
               identify_evidence=evidence)
    core.mark(job, "identify", game=prof["name"], mission=mission, confidence=confidence)
    return job
