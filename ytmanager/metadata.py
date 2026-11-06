"""Titles, descriptions, tags and hashtags: drafted from brand + game profiles, written by Claude, then linted.

library/<job>/metadata.json holds the editable text per target ("long", "short1".."short15"); `build`
assembles the final API payloads and `lint` blocks anything inaccurate, duplicated or over a limit.
"""
import json, os, re, subprocess, sys
from . import core, graphics

PLACEHOLDER = "<<WRITE>>"


def targets(job):
    t = ["long"] if job.get("kind", "long") == "long" else []
    return t + [f"short{s['n']}" for s in job.get("shorts", [])]


def _tag_chars(tags):
    return sum(len(t) + (2 if " " in t else 0) for t in tags) + max(0, len(tags) - 1)


def _hashtag(s):
    return "#" + re.sub(r"[^0-9A-Za-z]", "", s.title().replace("'S", "s"))


def auto_tags(job, target):
    b = core.config("brand"); g = core.game_profile(job.get("game")) or {}
    short = target.startswith("short")
    tags = list(g.get("tags", []))
    if job.get("mission"):
        m = job["mission"].lower()
        tags = [m, f"{g.get('short', '').lower()} {m}".strip()] + tags
        if job.get("mission_number"): tags.insert(2, f"{g.get('short', '').lower()} mission {job['mission_number']}")
    tags += b["tags"]["short" if short else "long"] + b["tags"]["brand"]
    if not job["probe"].get("hdr"): tags = [t for t in tags if "hdr" not in t.lower()]  # never claim HDR for SDR
    out, seen = [], set()
    for t in tags:
        t = t.strip().lower()
        if t and t not in seen and _tag_chars(out + [t]) <= b["tags"]["max_chars"]:
            out.append(t); seen.add(t)
    return out


def auto_hashtags(job, target):
    b = core.config("brand"); g = core.game_profile(job.get("game")) or {}
    short = target.startswith("short")
    hs = g.get("hashtags", [])[-1:] + ([_hashtag(job["mission"])] if job.get("mission") else []) + b["hashtags"]["always"]
    hs += g.get("hashtags", [])[:-1] + b["hashtags"]["short" if short else "long"]
    out = []
    for h in hs:
        if h.lower() not in [x.lower() for x in out]: out.append(h)
    return out[: b["hashtags"]["max_in_description"]]


def draft(job, force=False):
    path = core.job_dir(job["id"], "metadata.json")
    meta = core.load_json(path, {}) if not force else {}
    chapters = core.load_json(core.job_dir(job["id"], "edit", "chapters.json"), {}).get("chapters", [])
    for t in targets(job):
        if t in meta: continue
        entry = {"title": PLACEHOLDER, "hook_lines": [PLACEHOLDER, PLACEHOLDER], "body": PLACEHOLDER,
                 "tags": auto_tags(job, t), "hashtags": auto_hashtags(job, t)}
        if t == "long":
            entry["chapters"] = [{"time": c["label"], "title": c.get("title") or PLACEHOLDER} for c in chapters]
        meta[t] = entry
    meta["_help"] = ("Replace every <<WRITE>>. hook_lines = the two lines above '...more' (what the viewer gets, in "
                     "search words). body = what happens, accurate to the footage. Leave chapters [] to omit them. "
                     "Then run `ytm.py meta build`.")
    core.save_json(path, meta)
    core.mark(job, "metadata", status="drafted")
    return path


def build(job):
    b = core.config("brand"); g = core.game_profile(job.get("game")) or {}
    meta = core.load_json(core.job_dir(job["id"], "metadata.json"))
    if not meta: core.die("run `meta draft` first")
    final = {}
    for t in targets(job):
        m = meta.get(t)
        if not m: core.die(f"metadata.json has no entry for {t} - run `meta draft` again")
        short = t.startswith("short")
        parts = ["\n".join(l for l in m["hook_lines"] if l.strip())]
        if m.get("body", "").strip(): parts.append(m["body"].strip())
        if not short and m.get("chapters"):
            parts.append("⏱ Chapters\n" + "\n".join(f"{c['time']} {c['title']}" for c in m["chapters"]))
        if not short:
            info = f"🎮 Game: {g.get('name', job.get('game') or '')}"
            if job.get("mission"):
                info += f"\n🎯 Mission{(' ' + str(job['mission_number'])) if job.get('mission_number') else ''}: {job['mission']}"
            parts.append(info)
        footer = b["description"]["short_footer" if short else "footer"]
        if not job["probe"].get("hdr"): footer = footer.replace("4K HDR", "4K")  # never claim HDR for an SDR recording
        parts.append(footer)
        parts.append(" ".join(m["hashtags"]))
        final[t] = {"title": m["title"].strip(), "description": "\n\n".join(parts).strip(), "tags": m["tags"],
                    "categoryId": b["upload"]["category_id"], "defaultLanguage": b["upload"]["language"],
                    "defaultAudioLanguage": b["upload"]["language"]}
    meta["final"] = final
    core.save_json(core.job_dir(job["id"], "metadata.json"), meta)
    report = lint(job, meta)
    return final, report


# ------------------------------------------------------------------ lint

def _shingles(text):
    b = core.config("brand")
    for f in (b["description"]["footer"], b["description"]["footer"].replace("4K HDR", "4K"), b["description"]["short_footer"]):
        text = text.replace(f, "")
    w = re.findall(r"[a-z0-9']+", re.sub(r"#\w+", "", text.lower()))
    return {" ".join(w[i:i + 3]) for i in range(len(w) - 2)}


def _corpus(job):
    docs = []
    idx = core.load_json(os.path.join(core.DATA, "channel_index.json"), {})
    mine = {u.get("video_id") for u in job.get("uploads", {}).values()}
    for v in idx.get("videos", []):
        if v["id"] not in mine: docs.append((f"channel video {v['id']}", v.get("description", "")))
    for j in core.all_jobs():
        if j["id"] == job["id"]: continue
        for t, f in (core.load_json(core.job_dir(j["id"], "metadata.json"), {}).get("final") or {}).items():
            docs.append((f"{j['id']}/{t}", f["description"]))
    return docs


def _title_check(title, thumb):
    cmd = [sys.executable, os.path.join(core.SKILLS, "yt-package", "title.py"), "--title", title, "--json"]
    if thumb: cmd += ["--thumb", thumb]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    return json.loads(p.stdout)[0] if p.returncode == 0 else None


def lint(job, meta=None):
    meta = meta or core.load_json(core.job_dir(job["id"], "metadata.json"))
    final = meta.get("final") or core.die("run `meta build` first")
    b = core.config("brand"); g = core.game_profile(job.get("game")) or {}
    names = [g.get("name", ""), g.get("short", "")] + g.get("aliases", [])
    corpus = _corpus(job)
    report, ok_all = {}, True
    for t, f in final.items():
        short = t.startswith("short")
        err, warn = [], []
        title, desc, tags = f["title"], f["description"], f["tags"]
        blob = json.dumps(meta.get(t, {}), ensure_ascii=False)
        if PLACEHOLDER in blob: err.append("unwritten <<WRITE>> placeholder left in metadata.json")
        if not 1 <= len(title) <= 100: err.append(f"title is {len(title)} chars (1-100)")
        if "<" in title + desc or ">" in title + desc: err.append("'<' or '>' in title/description - the API rejects them")
        if len(desc.encode("utf-8")) > 5000: err.append(f"description is {len(desc.encode('utf-8'))} bytes (max 5000)")
        if _tag_chars(tags) > 500: err.append(f"tags total {_tag_chars(tags)} chars (max 500)")
        n_hash = len(re.findall(r"#\w+", desc + " " + title))
        if n_hash > 15: err.append(f"{n_hash} hashtags - over 15 and YouTube ignores all of them")
        if not any(nm and nm.lower() in title.lower() for nm in names): err.append(f"title does not name the game ({g.get('short', job.get('game'))})")
        if not short and re.search(r"#shorts\b", title + desc, re.I): err.append("#Shorts on a long-form video")
        if not job["probe"].get("hdr") and re.search(r"\bhdr\b", " ".join([title, desc, *tags]), re.I):
            err.append("says HDR but the recording is SDR")
        if short and not re.search(r"#shorts\b", title + desc, re.I): err.append("Short without #Shorts")
        if short:
            sh = next((s for s in job.get("shorts", []) if f"short{s['n']}" == t), {})
            if sh.get("duration", 0) > 180: err.append(f"Short is {sh['duration']}s - over 3 minutes is not a Short")
        if job.get("mission") and not short and job["mission"].lower() not in title.lower():
            warn.append(f"long-form title does not name the mission '{job['mission']}'")
        first2 = "\n".join(desc.splitlines()[:2]).lower()
        if not any(nm and nm.lower() in first2 for nm in names): warn.append("first two description lines do not name the game (search snippet)")
        if len(graphics.EMOJI.findall(title)) > 2: warn.append("more than 2 emoji groups in the title")
        if not short and meta.get(t, {}).get("chapters"):
            ch = meta[t]["chapters"]
            if len(ch) < 3 or ch[0]["time"] not in ("0:00", "00:00"): err.append("chapters need 3+ entries starting at 0:00")
        mine = _shingles(desc)
        for name, other in corpus:
            o = _shingles(other)
            if mine and o and len(mine & o) / len(mine | o) >= 0.5:
                err.append(f"description is {len(mine & o) / len(mine | o):.0%} the same as {name} - must be unique")
                break
        thumb = job.get("thumbnails", {}).get(t, {}).get("text")
        tc = _title_check(title, thumb)
        if tc:
            for k, m in tc["issues"]:
                if k in ("duplicate", "thumb-length", "length", "shouting"): warn.append(f"title.py {k}: {m}")
        report[t] = {"errors": err, "warnings": warn, "title_score": tc["score"] if tc else None}
        ok_all &= not err
    meta["lint"] = {"ok": ok_all, "at": core.now(), "report": report}
    core.save_json(core.job_dir(job["id"], "metadata.json"), meta)
    core.mark(job, "metadata", status="done" if ok_all else "lint-failed")
    return meta["lint"]
