"""Register a recording as a job. The original is fingerprinted, marked read-only and never written.

A recording split into several files (a break mid-session) is one job: every part is fingerprinted and
locked, and they are joined losslessly (concat demuxer, stream copy) into library/<job>/original/.
"""
import os, re, shutil
from . import core, media


def ps5_game_hint(filename):
    """PS5 names captures '<Game Title>_<YYYYMMDDhhmmss>.<ext>'."""
    stem = os.path.splitext(os.path.basename(filename))[0]
    m = re.match(r"^(.*?)[_ -]?(\d{14})$", stem)
    name = (m.group(1) if m else stem).replace("_", " ").replace("®", "").replace("™", "").strip()
    if re.fullmatch(r"[\d _.-]*", name): return None  # capture-tool timestamp names carry no game
    return name or None


def _sources(j):
    """Every original file a job was made from (the parts of a multi-part job, else its source)."""
    return j["source"].get("parts") or [j["source"]]


SAME_STREAMS = ("vcodec", "width", "height", "fps", "pix_fmt", "color_transfer", "acodec", "audio_channels", "sample_rate")


def scan():
    """Video files in the inbox (and config inbox_extra dirs) that are not registered yet."""
    srcs = [s for j in core.all_jobs() for s in _sources(j)]
    known = {s["fingerprint"] for s in srcs}
    known_paths = {os.path.normcase(s["path"]) for s in srcs}
    dirs = [core.INBOX] + [core.root_path(d) for d in core.config("brand").get("inbox_extra", [])]
    new = []
    for d in dirs:
        if not os.path.isdir(d): continue
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if os.path.splitext(name)[1].lower() in core.VIDEO_EXT and os.path.isfile(p):
                if os.path.normcase(p) in known_paths or core.fingerprint(p) in known: continue
                new.append(p)
    return new


def _registered(path, fp):
    for j in core.all_jobs():
        for s in _sources(j):
            if s["fingerprint"].split(":")[1] == fp.split(":")[1] or os.path.normcase(s["path"]) == os.path.normcase(path):
                return j
    return None


def intake(path, copy=False, full_hash=False, protect=True):
    if isinstance(path, (list, tuple)):
        if len(path) > 1: return intake_parts(path, full_hash, protect)
        path = path[0]
    path = os.path.abspath(path)
    if not os.path.isfile(path): core.die(f"not a file: {path}")
    fp = core.fingerprint(path, full=full_hash)
    j = _registered(path, fp)
    if j:
        print(f"Already registered as job {j['id']}")
        return j
    info = media.probe(path)
    hint = ps5_game_hint(path)
    game = core.find_game(hint)
    st = os.stat(path)
    date = __import__("datetime").datetime.fromtimestamp(st.st_mtime).strftime("%Y%m%d")
    job_id = f"{date}-{core.slug(hint or 'recording', 28)}-{fp.split(':')[1][:4]}"
    os.makedirs(core.job_dir(job_id), exist_ok=True)

    src_path = path
    if copy:
        dst = core.job_dir(job_id, "original", os.path.basename(path))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        print(f"Copying original into the library ({info['size_bytes'] / 2**30:.1f} GB)...")
        shutil.copy2(path, dst)
        if core.fingerprint(dst, full=full_hash) != fp: core.die("copy verification failed - fingerprints differ")
        src_path = dst
    if protect:
        core.protect(src_path)
        if copy: core.protect(path)

    job = {
        "id": job_id, "created": core.now(),
        "source": {"path": src_path, "original_path": path, "fingerprint": fp, "size_bytes": st.st_size,
                   "mtime": st.st_mtime, "read_only": protect, "copied": copy},
        "probe": info,
        "game_hint": hint,
        "game": game["name"] if game else None,
        "game_confidence": "filename" if game else None,
        "mission": None,
        "kind": "long",
        "stages": {},
    }
    core.save_job(job)
    core.mark(job, "intake")
    return job


def intake_parts(paths, full_hash=False, protect=True):
    """Several files of one session, in recording order -> one job with a lossless joined source."""
    paths = [os.path.abspath(p) for p in paths]
    for p in paths:
        if not os.path.isfile(p): core.die(f"not a file: {p}")
    parts = []
    for p in paths:
        fp = core.fingerprint(p, full=full_hash)
        j = _registered(p, fp)
        if j: core.die(f"{os.path.basename(p)} is already registered as job {j['id']}")
        parts.append({"path": p, "fingerprint": fp, "probe": media.probe(p)})
    first = parts[0]["probe"]
    for k in SAME_STREAMS:
        bad = [os.path.basename(x["path"]) for x in parts if x["probe"].get(k) != first.get(k)]
        if bad: core.die(f"parts differ in {k} ({', '.join(bad)}) - a lossless join needs identical streams")
    hint = next((h for h in (ps5_game_hint(p) for p in paths) if h), None)
    game = core.find_game(hint)
    st0 = os.stat(paths[0])
    date = __import__("datetime").datetime.fromtimestamp(st0.st_mtime).strftime("%Y%m%d")
    job_id = f"{date}-{core.slug(hint or 'recording', 28)}-{parts[0]['fingerprint'].split(':')[1][:4]}"
    os.makedirs(core.job_dir(job_id, "original"), exist_ok=True)

    t = 0.0
    for x in parts:
        st = os.stat(x["path"])
        if protect: core.protect(x["path"])
        x.update(size_bytes=st.st_size, mtime=st.st_mtime, offset=round(t, 3), duration=x["probe"]["duration"])
        t += x.pop("probe")["duration"]
    joined = core.job_dir(job_id, "original", f"{job_id}-joined.mp4")
    lst = core.job_dir(job_id, "original", "parts.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for x in parts: f.write("file '" + x["path"].replace("\\", "/").replace("'", "'\\''") + "'\n")
    print(f"Joining {len(parts)} parts losslessly ({sum(x['size_bytes'] for x in parts) / 2**30:.1f} GB, stream copy)...", flush=True)
    media.run_progress(["ffmpeg", "-hide_banner", "-y", "-nostats", "-progress", "pipe:1", "-f", "concat", "-safe", "0",
                        "-i", lst, "-map", "0:v:0", "-map", "0:a?", "-c", "copy", "-movflags", "+faststart", joined], t, "join")
    info = media.probe(joined)
    if abs(info["duration"] - t) > 1.0: core.die(f"joined duration {info['duration']:.1f}s != parts total {t:.1f}s")
    if protect: core.protect(joined)
    st = os.stat(joined)
    job = {
        "id": job_id, "created": core.now(),
        "source": {"path": joined, "original_path": paths[0], "fingerprint": core.fingerprint(joined),
                   "size_bytes": st.st_size, "mtime": st.st_mtime, "read_only": protect, "copied": False,
                   "joined": True, "parts": parts},
        "probe": info,
        "game_hint": hint,
        "game": game["name"] if game else None,
        "game_confidence": "filename" if game else None,
        "mission": None,
        "kind": "long",
        "stages": {},
    }
    core.save_job(job)
    core.mark(job, "intake", parts=len(parts))
    return job


def _keyframe_at_or_before(src, t):
    if t <= 0: return 0.0
    p = media.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey", "-read_intervals",
                   f"{max(0.0, t - 10):.3f}%{t + 0.01:.3f}", "-show_entries", "frame=pts_time", "-of", "csv=p=0", src])
    ks = [float(x) for x in p.stdout.split() if x.strip() and float(x) <= t + 1e-3]
    return max(ks) if ks else 0.0


def split(parent, bounds, names, protect=True, reuse=False):
    """One job per mission from a session that holds several. Each child's source is a lossless stream-copy slice
    of the (read-only) parent source starting on a keyframe; the parent's signals and transcript are sliced over
    so the children need no second decode pass."""
    src, dur = parent["source"]["path"], parent["probe"]["duration"]
    edges = [0.0] + [core.parse_time(b) for b in bounds] + [dur]
    if len(names) != len(edges) - 1: core.die(f"{len(edges) - 1} pieces need {len(edges) - 1} names")
    sig = core.load_json(core.job_dir(parent["id"], "analysis", "signals.json"))
    tr = core.load_json(core.job_dir(parent["id"], "analysis", "transcript.json"))
    kids = []
    for k, name in enumerate(names):
        a = _keyframe_at_or_before(src, edges[k]); b = edges[k + 1]
        kid_id = f"{parent['id'].rsplit('-', 1)[0]}-{core.slug(name, 20)}-{parent['id'].rsplit('-', 1)[1]}"
        out = core.job_dir(kid_id, "original", f"{kid_id}.mp4")
        if reuse and os.path.exists(core.job_dir(kid_id, "job.json")):  # unchanged piece of a re-split
            kids.append(core.load_job(kid_id)); continue
        if os.path.exists(out): core.die(f"{kid_id} already exists")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        print(f"  {name}: {core.mmss(a)}-{core.mmss(b)} (stream copy)", flush=True)
        media.run(["ffmpeg", "-hide_banner", "-v", "error", "-ss", f"{a:.3f}", "-i", src, "-t", f"{b - a:.3f}",
                   "-map", "0:v:0", "-map", "0:a?", "-c", "copy", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", out])
        if protect: core.protect(out)
        st, info = os.stat(out), media.probe(out)
        kid = {"id": kid_id, "created": core.now(),
               "source": {"path": out, "original_path": parent["source"]["original_path"], "fingerprint": core.fingerprint(out),
                          "size_bytes": st.st_size, "mtime": st.st_mtime, "read_only": protect, "copied": False,
                          "parent": parent["id"], "parent_start": round(a, 3), "parent_end": round(b, 3)},
               "probe": info, "game_hint": parent.get("game_hint"), "game": parent.get("game"),
               "game_confidence": parent.get("game_confidence"), "mission": None, "kind": "long", "stages": {},
               **({"grade": parent["grade"]} if parent.get("grade") else {})}
        an = core.job_dir(kid_id, "analysis")
        if sig:
            i, j = int(a), int(a) + int(info["duration"]) + 1
            core.save_json(os.path.join(an, "signals.json"),
                           {**{key: v[i:j] if isinstance(v, list) else v for key, v in sig.items()}, "duration": info["duration"]})
        if tr:
            segs = [{**s, "start": round(s["start"] - a, 2), "end": round(s["end"] - a, 2)}
                    for s in tr.get("segments", []) if a <= s["start"] < a + info["duration"]]
            core.save_json(os.path.join(an, "transcript.json"), {**tr, "segments": segs})
        core.save_job(kid)
        core.mark(kid, "intake", parent=parent["id"])
        kids.append(kid)
    parent["children"] = [j["id"] for j in kids]
    core.mark(parent, "split", children=parent["children"])
    return kids


def verify_original(job):
    """Every original file (each part, plus the joined copy of a multi-part job) still matches its fingerprint."""
    srcs = _sources(job) + ([job["source"]] if job["source"].get("parts") else [])
    msgs, ok_all = [], True
    for s in srcs:
        p = s["path"]
        if not os.path.exists(p):
            ok_all = False; msgs.append(f"{os.path.basename(p)}: missing"); continue
        ok = core.fingerprint(p, full=s["fingerprint"].startswith("full:")) == s["fingerprint"]
        ok_all &= ok
        msgs.append(f"{os.path.basename(p)}: {'unchanged' if ok else 'FINGERPRINT CHANGED'}")
    if len(srcs) == 1: return ok_all, msgs[0].split(": ", 1)[1].replace("missing", "original is missing")
    return ok_all, "\n".join(msgs)
