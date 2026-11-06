"""Cloned-voice narration (Chatterbox, MIT licence, runs locally on the CPU in tools/voice/venv).

  py ytm.py voice prep <recording>            clean the user's recording -> data/voice/clean/, 6 reference candidates
  py ytm.py voice use <n>                     make candidate n data/voice/ref.wav (the clip the model copies)
  py ytm.py voice say "<text>" --out f.wav    narrate text in the cloned voice (--job marks that job as AI-narrated)
"""
import json, os, re, subprocess, tempfile

from ytmanager import core

VENV_PY = os.path.join(core.ROOT, "tools", "voice", "venv", "Scripts", "python.exe")
WORKER = os.path.join(core.ROOT, "tools", "voice", "worker.py")
VOICE = os.path.join(core.DATA, "voice")
REF = os.path.join(VOICE, "ref.wav")


def _worker(*args):
    if not os.path.exists(VENV_PY): core.die(f"voice venv missing: {VENV_PY}")
    env = dict(os.environ, PYTHONUTF8="1", CUDA_VISIBLE_DEVICES="")  # CPU only - the GPU is for renders
    r = subprocess.run([VENV_PY, "-I", WORKER, *args], env=env, stdout=subprocess.PIPE, text=True, encoding="utf-8")
    if r.returncode: core.die(f"voice worker failed ({r.returncode})")
    return json.loads(r.stdout.strip().splitlines()[-1])


def prep(src, lo=10, hi=25):
    """Mono 24 kHz, low rumble cut, denoise, edges trimmed, long pauses shortened, loudness -16 LUFS."""
    src = core.root_path(src)
    name = os.path.splitext(os.path.basename(src))[0]
    full = os.path.join(VOICE, "clean", f"{name}_full.wav")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    af = ("highpass=f=70,afftdn=nr=15:nf=-40:tn=1,loudnorm=I=-16:TP=-1.5:LRA=11,"  # phone hiss sits ~12 dB under speech
          "silenceremove=start_periods=1:start_threshold=-32dB:stop_periods=-1:stop_duration=0.8:stop_threshold=-32dB")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-vn", "-ac", "1", "-af", af,
                    "-ar", "24000", "-c:a", "pcm_s16le", full], check=True)
    cands = _worker("pick", full, os.path.join(VOICE, "clean", "ref.wav"), str(lo), str(hi), "6")
    core.save_json(os.path.join(VOICE, "ref.json"), {"source": src, "full": full, "candidates": cands, "made": core.now()})
    use(1)
    return cands


def use(n):
    """Make candidate n (from prep; listen first - the auto pick can't hear stumbles) the reference clip."""
    import shutil
    r = core.load_json(os.path.join(VOICE, "ref.json")) or core.die("run `voice prep` first")
    c = r["candidates"][n - 1]
    shutil.copyfile(core.root_path(c["file"]), REF)
    r["using"] = n; core.save_json(os.path.join(VOICE, "ref.json"), r)
    return dict(c, ref=REF)


# mood tags in the script: "[hook] This man has one job. [react] Wait... what?"  -> (exaggeration, cfg_weight, pause after)
MOODS = {"calm": (0.45, 0.5, 0.35), "hook": (0.7, 0.35, 0.3), "react": (0.95, 0.3, 0.15), "hype": (1.1, 0.25, 0.15),
         "scream": (1.4, 0.2, 0.05)}
# after-effects per mood: a yelling voice goes up in pitch and loudness (the model alone tops out at "excited")
MOOD_FX = {"scream": "rubberband=pitch=1.12:tempo=1.12,volume=4dB,alimiter=limit=0.95", "hype": "rubberband=pitch=1.05,volume=2dB"}
NUM = dict(enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                     "sixteen seventeen eighteen nineteen twenty".split()))


def lines(text, limit=280, tagged=110):
    """Split into sentences and merge them up to `limit` chars (`tagged` under a mood tag - shorter keeps the
    delivery lively and the hear-back check precise). -> [(text, mood)]"""
    out = []
    for mood, chunk in re.findall(r"(?:\[(\w+)\])?\s*([^\[]+)", text.strip()):
        cur = ""
        for s in re.split(r"(?<=[.!?])\s+", chunk.strip()):
            if cur and len(cur) + len(s) > (tagged if mood else limit): out.append((cur, mood or None)); cur = s
            else: cur = f"{cur} {s}".strip()
        if cur: out.append((cur, mood or None))
    return out


def _words(t):
    return [NUM.get(int(w), w) if w.isdigit() and int(w) <= 20 else w
            for w in re.findall(r"[a-z0-9']+", t.lower().replace("-", " "))]


def accuracy(want, got):
    """1.0 = every word said as written; added, dropped or swapped words all count against it."""
    import difflib
    a, b = _words(want), _words(got)
    m = sum(x.size for x in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
    return round(2 * m / max(len(a) + len(b), 1), 3)


class _Ears:
    """faster-whisper (already used by analyze) - hears each rendered line back."""
    def __init__(self):
        from faster_whisper import WhisperModel
        self.m = WhisperModel(core.config("brand").get("whisper_model", "small"), device="cpu", compute_type="int8", cpu_threads=8)

    def hear(self, wav_path):
        import numpy as np, wave
        with wave.open(wav_path, "rb") as w:  # raw samples: faster-whisper's PyAV loader breaks on newer PyAV
            a, sr = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0, w.getframerate()
        if sr != 16000: a = np.interp(np.arange(0, len(a), sr / 16000), np.arange(len(a)), a).astype(np.float32)
        return " ".join(s.text.strip() for s in self.m.transcribe(a, language="en", beam_size=1)[0])


def say(texts, outs, ref=None, exaggeration=0.5, cfg=0.5, job=None, speed=None, energy=None, tries=None, check=True):
    """Narrate each text into its out file. Texts may carry mood tags - [calm] [hook] [react] [hype].
    Every line is transcribed back and re-rendered (new seed, a little calmer each time) until it says the script -
    up to `tries` renders; the best take is kept and any line still off-script is reported.
    speed: tempo multiplier applied afterwards (pitch kept); energy: scales the mood tags. Defaults from brand.voice."""
    import random, shutil, time, wave
    bv = core.config("brand").get("voice", {})
    speed, energy = speed or bv.get("speed", 1.0), energy or bv.get("energy", 1.0)
    tries, need = (tries or bv.get("tries", 4)) if check else 1, bv.get("min_accuracy", 0.93)
    ref = core.root_path(ref) if ref else REF
    if not os.path.exists(ref): core.die("no reference clip - run `py ytm.py voice prep <recording>` first")
    L = []
    for fi, t in enumerate(texts):
        for s, mood in lines(t):
            ex, cf, pause = MOODS.get(mood, (exaggeration, cfg, 0.25))
            if mood in MOODS:  # energy > 1 pushes every tagged line harder: more expressive, tighter pauses
                ex, cf, pause = min(ex * energy, 2.0), max(cf / energy, 0.1), pause / energy
            L.append({"file": fi, "text": s, "mood": mood, "ex": ex, "cfg": cf, "pause": pause,
                      "best": None, "acc": -1.0, "tries": 0, "heard": ""})
    ears, t0, tmp = (_Ears() if check else None), time.time(), tempfile.mkdtemp(prefix="nkvoice_")
    try:
        for attempt in range(tries):
            todo = [i for i, l in enumerate(L) if l["acc"] < need]
            if not todo: break
            calm = 0.85 ** attempt  # each retry eases off - high exaggeration is what makes the model invent words
            spec = {"ref": ref, "lines": [{"text": L[i]["text"], "out": os.path.join(tmp, f"{i}_{attempt}.wav"),
                                           "ex": max(L[i]["ex"] * calm, 0.4), "cfg": min(L[i]["cfg"] / calm, 0.5),
                                           "temp": 0.8, "seed": random.randrange(2**31)} for i in todo]}
            sp = os.path.join(tmp, "spec.json"); core.save_json(sp, spec)
            _worker("render", sp)
            for i, ln in zip(todo, spec["lines"]):
                l = L[i]; l["tries"] += 1
                heard = ears.hear(ln["out"]) if check else l["text"]
                acc = accuracy(l["text"], heard)
                if acc > l["acc"]: l.update(best=ln["out"], acc=acc, heard=heard)
            print(f"  pass {attempt + 1}: {sum(l['acc'] >= need for l in L)}/{len(L)} lines on script", flush=True)
        res = []
        for fi, out in enumerate(outs):
            out = os.path.abspath(core.root_path(out)); os.makedirs(os.path.dirname(out), exist_ok=True)
            mine, raw = [l for l in L if l["file"] == fi], os.path.join(tmp, f"file{fi}.wav")
            for l in mine:
                if l["mood"] in MOOD_FX:
                    fx = l["best"][:-4] + "_fx.wav"
                    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", l["best"], "-af", MOOD_FX[l["mood"]],
                                    "-c:a", "pcm_s16le", fx], check=True)
                    l["best"] = fx
            with wave.open(raw, "wb") as w:
                for k, l in enumerate(mine):
                    with wave.open(l["best"], "rb") as r:
                        if not k: w.setparams(r.getparams())
                        w.writeframes(r.readframes(r.getnframes()))
                    if k < len(mine) - 1: w.writeframes(b"\0\0" * int(w.getframerate() * l["pause"]))
            if speed != 1.0:
                subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", raw, "-af", f"atempo={speed}", out], check=True)
            else: shutil.copyfile(raw, out)
            with wave.open(out, "rb") as w: secs = w.getnframes() / w.getframerate()
            res.append({"out": out, "audio_s": round(secs, 1), "off_script": sum(l["acc"] < need for l in mine),
                        "lines": [{"text": l["text"], "mood": l["mood"], "accuracy": l["acc"], "tries": l["tries"],
                                   **({"heard": l["heard"]} if l["acc"] < need else {})} for l in mine]})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if job:  # every upload of this job must carry YouTube's altered/synthetic content disclosure
        j = core.load_job(job)
        n = j.setdefault("narration", {"cloned_voice": True, "files": []})
        n["files"] = sorted(set(n["files"]) | {r["out"] for r in res})
        core.save_job(j)
    took = time.time() - t0
    return {"files": res, "gen_s": round(took, 1), "min_per_audio_min": round(took / max(sum(r["audio_s"] for r in res), 0.1), 1)}


def needs_disclosure(job):
    """brand.upload.synthetic_voice_disclosure: a cloned-voice narration means containsSyntheticMedia=true."""
    b = core.config("brand")["upload"]
    return bool(b["contains_synthetic_media"] or
                (b.get("synthetic_voice_disclosure", True) and (job.get("narration") or {}).get("cloned_voice")))
