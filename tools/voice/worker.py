"""Runs inside tools/voice/venv (Chatterbox, CPU). Called by ytmanager/voice.py - not meant to be run by hand.

  worker.py pick <clean.wav> <ref_out.wav> [min_s max_s n]
  worker.py render <spec.json>    # {"ref": wav, "lines": [{"text", "out", "ex", "cfg", "temp", "seed"}]}
"""
import json, sys, time

import numpy as np
import soundfile as sf


def pick(src, dst, lo=10.0, hi=25.0, n=3):
    """Reference candidates: the n non-overlapping stretches with the most steady speech and no long pauses.
    Writes <dst>_cand1..n.wav (best first) and copies the best to dst."""
    y, sr = sf.read(src, dtype="float32")
    if y.ndim > 1: y = y.mean(1)
    hop = int(sr * 0.05)
    rms = np.sqrt(np.convolve(y ** 2, np.ones(hop) / hop, "same")[::hop] + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    voiced = db > (np.percentile(db, 95) - 18)
    win = int(hi / 0.05)
    if len(voiced) <= win:
        sf.write(dst, y, sr); return [{"file": dst, "start": 0.0, "seconds": len(y) / sr}]
    scores = []
    for i in range(0, len(voiced) - win, 10):
        w = voiced[i:i + win]
        gaps = np.diff(np.flatnonzero(np.diff(np.r_[1, w.astype(int), 1]) != 0))[1::2] if (~w).any() else np.array([0])
        scores.append((w.mean() - 0.5 * (gaps.max() * 0.05 > 1.2), i))  # penalise pauses longer than 1.2 s
    out = []
    for score, i in sorted(scores, reverse=True):
        if len(out) == n: break
        if any(abs(i - c["_i"]) < win for c in out): continue
        s, e = i, i + win  # start and end on a pause so no word is cut
        while s > 0 and voiced[s] and i - s < 20: s -= 1
        while e > s + int(lo / 0.05) and e < len(voiced) and voiced[e - 1]: e -= 1
        f = dst.replace(".wav", f"_cand{len(out) + 1}.wav")
        sf.write(f, y[s * hop:e * hop], sr)
        out.append({"_i": i, "file": f, "start": round(s * hop / sr, 2), "seconds": round((e - s) * hop / sr, 2),
                    "voiced": round(float(score), 3)})
    sf.write(dst, sf.read(out[0]["file"], dtype="float32")[0], sr)
    for c in out: c.pop("_i")
    return out


def render(spec):
    """spec = {"ref": wav, "lines": [{"text", "out", "ex", "cfg", "temp", "seed"}]} - one model load, one wav per line."""
    import torch
    from chatterbox.tts import ChatterboxTTS
    torch.set_num_threads(8)  # half the CPU - leaves room for ffmpeg renders running alongside
    t0 = time.time()
    model = ChatterboxTTS.from_pretrained(device="cpu")
    load, res = time.time() - t0, []
    for ln in spec["lines"]:
        t = time.time(); torch.manual_seed(ln["seed"])
        w = model.generate(ln["text"], audio_prompt_path=spec["ref"], exaggeration=ln["ex"], cfg_weight=ln["cfg"],
                           temperature=ln["temp"])
        sf.write(ln["out"], w.squeeze(0).cpu().numpy(), model.sr, subtype="PCM_16")
        res.append({"out": ln["out"], "audio_s": round(w.shape[-1] / model.sr, 2), "gen_s": round(time.time() - t, 1)})
        print(json.dumps(res[-1]), file=sys.stderr, flush=True)
    return {"load_s": round(load, 1), "lines": res}


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "pick":
        a = sys.argv[2:]
        print(json.dumps(pick(a[0], a[1], *(float(x) for x in a[2:4]), *(int(x) for x in a[4:5]))))
    elif cmd == "render":
        print(json.dumps(render(json.load(open(sys.argv[2], encoding="utf-8")))))
