"""Find repeated attempts (die -> checkpoint reload -> play the same section again) so the edit keeps
only the final, successful run.

One cheap decode pass at 1 fps gives a 64-bit difference hash per second. When a stretch of later
seconds matches an earlier stretch frame-for-frame (same offset, 10s+), the earlier stretch is a
failed attempt that was replayed: everything from where it started up to where the replay starts
(the attempt, the death, the reload) is a retry cut.
"""
import os, subprocess
import numpy as np
from . import core, media

MIN_RUN = 10        # seconds of matching footage before we call it a replay
MIN_GAP = 20        # an attempt + death + reload takes at least this long
MAX_HAM = 10        # of 64 bits: same place, same camera, small differences (enemies, HUD)
AUTO_MAX = 600      # retry spans longer than 10 min may be backtracking - listed for review, not cut
DARK = 12           # mean luma (0-255) below which a second is too dark to fingerprint
MIN_NCC = 0.8       # replay confirmation (see _confirm) needed before a retry is cut automatically


def _hashes(job):
    """dHash per second: 9x8 grey frame, compare neighbours -> 64 bits."""
    src, info = job["source"]["path"], job["probe"]
    cmd = ["ffmpeg", "-hide_banner", "-v", "error", "-hwaccel", "auto", "-i", src,
           "-vf", "fps=1,scale=9:8:flags=area,format=gray", "-f", "rawvideo", "-"]
    print(f"Fingerprinting {core.mmss(info['duration'])} at 1 frame/s for repeated attempts...")
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    px = np.frombuffer(raw, np.uint8)[: len(raw) // 72 * 72].reshape(-1, 8, 9).astype(np.int16)
    bits = (px[:, :, 1:] > px[:, :, :-1]).reshape(len(px), 64)
    flat = (px.max(axis=(1, 2)) - px.min(axis=(1, 2))) < 12   # near-uniform frames (black, fades) hash unreliably
    return np.packbits(bits, axis=1).view(">u8").ravel().astype(np.uint64), flat


def _confirm(src, a, b, n=12):
    """Second opinion: a checkpoint reload puts the camera back in the same spot, so contrast-normalised 96x54
    frames of the attempt and the replay correlate almost perfectly. Look-alike corridors score ~0.5."""
    def grab(t):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", src, "-t", str(n), "-vf",
                              "fps=1,scale=96:54:flags=area,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
        return np.frombuffer(raw, np.uint8)[: len(raw) // 5184 * 5184].reshape(-1, 54, 96).astype(np.float32)
    x, y = grab(a), grab(b)
    sc = []
    for i in range(min(len(x), len(y))):
        p, q = x[i] - x[i].mean(), y[i] - y[i].mean()
        den = float(np.sqrt((p * p).sum() * (q * q).sum()))
        sc.append(float((p * q).sum()) / den if den > 1e-3 else 0.0)
    return round(float(np.median(sc)), 3) if sc else 0.0


def _popcount(x):
    x = x - ((x >> np.uint64(1)) & np.uint64(0x5555555555555555))
    x = (x & np.uint64(0x3333333333333333)) + ((x >> np.uint64(2)) & np.uint64(0x3333333333333333))
    x = (x + (x >> np.uint64(4))) & np.uint64(0x0F0F0F0F0F0F0F0F)
    return (x * np.uint64(0x0101010101010101)) >> np.uint64(56)


def find(job, force=False):
    path = core.job_dir(job["id"], "analysis", "retries.json")
    if os.path.exists(path) and not force: return core.load_json(path)
    h, flat = _hashes(job)
    sig = core.load_json(core.job_dir(job["id"], "analysis", "signals.json"), {})
    luma, motion = sig.get("luma", []), sig.get("motion", [])
    n = len(h)
    # dark night levels are still usable footage; only near-uniform frames (black, fades, loading) are not
    # ...but near-black seconds (YAVG < DARK) hash alike everywhere - dark stealth missions matched
    # unrelated black corridors as "replays", so they never count towards a match
    usable = np.array([not flat[i] and (i >= len(motion) or motion[i] >= 0.4) and (i >= len(luma) or luma[i] >= DARK)
                       for i in range(n)])
    # match[d][i]: second i matches second i+d (d = how much later the replay is)
    runs = []
    for d in range(MIN_GAP, n - MIN_RUN):
        a, b = h[: n - d], h[d:]
        ok = (_popcount(a ^ b) <= MAX_HAM) & usable[: n - d] & usable[d:]
        if ok.sum() < MIN_RUN: continue
        # runs of matches, tolerating 2-second gaps (HUD pop-ups, an enemy in a different spot)
        i, cnt = 0, len(ok)
        while i < cnt:
            if not ok[i]: i += 1; continue
            j, miss, hits = i, 0, 0
            while j < cnt and miss <= 2:
                if ok[j]: hits += 1; miss = 0
                else: miss += 1
                j += 1
            end = j - miss
            if end - i >= MIN_RUN and hits / (end - i) >= 0.7:
                runs.append({"orig": i, "replay": i + d, "len": end - i, "offset": d})
            i = j
    # keep the earliest original for each replay; drop runs contained in a longer one
    runs.sort(key=lambda r: (r["replay"], -r["len"]))
    retries, last_end = [], -1
    for r in runs:
        if r["replay"] < last_end: continue
        a, b = r["orig"], r["replay"]   # cut the failed attempt, death and reload; keep the replay
        span = b - a
        ncc = _confirm(job["source"]["path"], a, b)
        retries.append({"start": float(a), "end": float(b), "seconds": span, "replayed_at": float(b),
                        "matched_seconds": r["len"], "ncc": ncc, "auto": span <= AUTO_MAX and ncc >= MIN_NCC,
                        "why": f"{core.mmss(a)} is played again from {core.mmss(b)} ({r['len']}s match, ncc {ncc:.2f})"})
        last_end = b + r["len"]
    out = {"retries": retries, "params": {"min_run": MIN_RUN, "min_gap": MIN_GAP, "max_hamming": MAX_HAM}}
    core.save_json(path, out)
    for x in retries:
        print(f"  {'cut ' if x['auto'] else 'REVIEW'} {core.mmss(x['start'])}-{core.mmss(x['end'])} "
              f"({x['seconds']:.0f}s): {x['why']}")
    if not retries: print("  no repeated attempts found")
    return out
