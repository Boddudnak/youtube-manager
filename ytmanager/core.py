"""Paths, config, job manifests and small shared helpers.

A *job* is one recording. Everything derived from it lives in library/<job_id>/ and its state is
library/<job_id>/job.json. The original recording is only ever read.
"""
import datetime, hashlib, json, os, re, stat, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config")
LIBRARY = os.path.join(ROOT, "library")
INBOX = os.path.join(ROOT, "inbox")
DATA = os.path.join(ROOT, "data")
BACKUPS = os.path.join(ROOT, "backups")
SKILLS = os.path.expanduser("~/.claude/skills")

VIDEO_EXT = {".mp4", ".webm", ".mkv", ".mov", ".m4v", ".ts"}

STAGES = ["intake", "analyze", "identify", "moments", "edit", "shorts", "thumbnail", "metadata", "upload", "verify", "publish"]


def utf8_stdout():
    for s in (sys.stdout, sys.stderr):
        try: s.reconfigure(encoding="utf-8")
        except Exception: pass


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def config(name):
    return load_json(os.path.join(CONFIG, f"{name}.json"), {})


def root_path(p):
    """Config paths may be relative to the youtube-manager folder."""
    p = os.path.expanduser(p)
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def slug(s, n=40):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:n].strip("-") or "recording"


def mmss(t):
    t = int(round(t)); h, m, s = t // 3600, (t % 3600) // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_time(s):
    """'90', '1:30', '1:02:03', '90.5' -> seconds."""
    s = str(s).strip()
    parts = [float(p) for p in s.split(":")]
    sec = 0.0
    for p in parts: sec = sec * 60 + p
    return sec


# ---------------------------------------------------------------- originals

def fingerprint(path, full=False):
    """sha256 of size + first/last 32 MB (fast), or of the whole file with full=True."""
    h = hashlib.sha256()
    size = os.path.getsize(path)
    h.update(str(size).encode())
    with open(path, "rb") as f:
        if full or size <= 64 * 2**20:
            for chunk in iter(lambda: f.read(8 * 2**20), b""): h.update(chunk)
        else:
            h.update(f.read(32 * 2**20)); f.seek(-32 * 2**20, 2); h.update(f.read())
    return ("full:" if full or size <= 64 * 2**20 else "quick:") + h.hexdigest()


def protect(path):
    """Mark the original read-only so no tool (or slip of the hand) can overwrite it."""
    mode = os.stat(path).st_mode
    os.chmod(path, mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def assert_not_original(job, out_path):
    srcs = [job["source"]] + job["source"].get("parts", [])
    if os.path.normcase(os.path.abspath(out_path)) in {os.path.normcase(os.path.abspath(s["path"])) for s in srcs}:
        die("refusing to write over the original recording")


# ---------------------------------------------------------------- jobs

def job_dir(job_id, *sub):
    return os.path.join(LIBRARY, job_id, *sub)


def all_jobs():
    if not os.path.isdir(LIBRARY): return []
    out = []
    for d in sorted(os.listdir(LIBRARY)):
        j = load_json(os.path.join(LIBRARY, d, "job.json"))
        if j: out.append(j)
    return out


def load_job(ref):
    """Accepts a full id, a unique prefix/substring, or 'latest'."""
    jobs = all_jobs()
    if not jobs: die("no jobs yet - run `ytm.py intake <recording>` first")
    if ref in (None, "", "latest"):
        return max(jobs, key=lambda j: j["created"])
    exact = [j for j in jobs if j["id"] == ref]
    hits = exact or [j for j in jobs if ref.lower() in j["id"].lower()]
    if len(hits) != 1:
        die(f"job '{ref}' matches {len(hits)} jobs: {', '.join(j['id'] for j in hits) or '-'}")
    return hits[0]


def save_job(job):
    job["updated"] = now()
    save_json(job_dir(job["id"], "job.json"), job)


def mark(job, stage, status="done", **info):
    job.setdefault("stages", {})[stage] = {"status": status, "at": now(), **info}
    save_job(job)


def next_stage(job):
    if job.get("children"): return None  # a session split into one job per mission - work continues on those
    st = job.get("stages", {})
    for s in STAGES:
        if st.get(s, {}).get("status") != "done":
            return s
    return None


# ---------------------------------------------------------------- games

def find_game(text):
    """Best game profile whose name or alias appears in text (longest alias wins)."""
    if not text: return None
    t = text.lower()
    best = None
    for g in config("games").get("games", []):
        for a in [g["name"].lower()] + g.get("aliases", []):
            if a and a in t and (best is None or len(a) > best[0]):
                best = (len(a), g)
    return best[1] if best else None


def game_profile(name):
    for g in config("games").get("games", []):
        if g["name"].lower() == (name or "").lower():
            return g
    return find_game(name)
