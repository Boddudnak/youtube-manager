"""YouTube Data API: upload, thumbnail, verify, metadata update, privacy change, channel index.

Auth is the existing ~/.youtube-api/yt.py (one OAuth flow, one token). Every write is preceded by
a channel guard - the token must belong to config/channel.json's channel_id - and there is
deliberately no delete operation anywhere in this module.
"""
import datetime, os, re, sys, time
from . import core, voice

COST = {"list": 1, "insert": 1600, "update": 50, "thumbnail": 50, "search": 100}
_yt = None; _svc = None; _guarded = False


def _ytmod():
    global _yt
    if _yt is None:
        sys.path.insert(0, os.path.expanduser(core.config("channel").get("oauth_dir", "~/.youtube-api")))
        import yt as _m
        _yt = _m
    return _yt


def service():
    global _svc
    if _svc is None:
        from googleapiclient.discovery import build
        _svc = build("youtube", "v3", credentials=_ytmod().credentials(), cache_discovery=False)
    return _svc


def analytics_service():
    from googleapiclient.discovery import build
    return build("youtubeAnalytics", "v2", credentials=_ytmod().credentials(), cache_discovery=False)


def spend(kind, n=1):
    """Local ledger of estimated quota units per Pacific-time day (the quota resets at PT midnight)."""
    day = (datetime.datetime.utcnow() - datetime.timedelta(hours=8)).strftime("%Y-%m-%d")
    path = os.path.join(core.DATA, "quota.json")
    q = core.load_json(path, {})
    q[day] = q.get(day, 0) + COST[kind] * n
    core.save_json(path, {k: q[k] for k in sorted(q)[-30:]})
    return q[day]


def quota_today():
    day = (datetime.datetime.utcnow() - datetime.timedelta(hours=8)).strftime("%Y-%m-%d")
    return core.load_json(os.path.join(core.DATA, "quota.json"), {}).get(day, 0)


def guard():
    """Abort unless the token is for the configured channel (the account also owns other channels)."""
    global _guarded
    if _guarded: return
    want = core.config("channel")["channel_id"]
    items = service().channels().list(part="snippet", mine=True).execute().get("items", []); spend("list")
    got = items[0]["id"] if items else None
    if got != want:
        name = items[0]["snippet"]["title"] if items else "no channel"
        core.die(f"token is for '{name}' ({got}), not {core.config('channel')['title']} ({want}). "
                 "Re-run sign-in and pick your channel on Google's channel chooser.")
    _guarded = True


def _iso_seconds(iso):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m: return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


# ------------------------------------------------------------------ channel index / backups

def index():
    """All uploads' metadata -> data/channel_index.json and a dated backup (protects existing videos)."""
    guard()
    s = service()
    pl = s.channels().list(part="contentDetails", mine=True).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, tok = [], None
    while True:
        r = s.playlistItems().list(part="contentDetails", playlistId=pl, maxResults=50, pageToken=tok).execute(); spend("list")
        ids += [i["contentDetails"]["videoId"] for i in r["items"]]
        tok = r.get("nextPageToken")
        if not tok: break
    vids = []
    for i in range(0, len(ids), 50):
        r = s.videos().list(part="snippet,status,contentDetails,statistics", id=",".join(ids[i:i + 50])).execute(); spend("list")
        for v in r["items"]:
            sn = v["snippet"]
            vids.append({"id": v["id"], "title": sn["title"], "description": sn.get("description", ""), "tags": sn.get("tags", []),
                         "categoryId": sn.get("categoryId"), "publishedAt": sn["publishedAt"],
                         "privacy": v["status"]["privacyStatus"], "seconds": _iso_seconds(v["contentDetails"]["duration"]),
                         "views": int(v["statistics"].get("viewCount", 0)), "snippet": sn, "status": v["status"]})
    data = {"at": core.now(), "count": len(vids), "videos": vids}
    core.save_json(os.path.join(core.DATA, "channel_index.json"), data)
    core.save_json(os.path.join(core.BACKUPS, "channel", f"channel-{datetime.datetime.now():%Y%m%d-%H%M%S}.json"), data)
    return data


def _backup_video(v, why):
    p = os.path.join(core.BACKUPS, "videos", f"{v['id']}-{datetime.datetime.now():%Y%m%d-%H%M%S}-{why}.json")
    core.save_json(p, {"id": v["id"], "snippet": v["snippet"], "status": v.get("status")})
    return p


def _get(vid, parts="snippet,status,contentDetails,processingDetails"):
    r = service().videos().list(part=parts, id=vid).execute(); spend("list")
    return r["items"][0] if r.get("items") else None


# ------------------------------------------------------------------ upload

def media_path(job, target):
    if target == "long":
        lf = job.get("long_form") or core.die("long-form not rendered - run `edit render` first")
        return lf["path"]
    n = int(target.replace("short", ""))
    sh = next((s for s in job.get("shorts", []) if s["n"] == n), None)
    if not sh or not sh.get("path"): core.die(f"{target} not rendered - run `shorts render` first")
    return sh["path"]


def upload(job, target, privacy=None, force=False):
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    b = core.config("brand")["upload"]
    privacy = privacy or b["default_privacy"]
    if privacy not in b["allowed_privacy_before_review"]:
        core.die(f"uploads start as {' or '.join(b['allowed_privacy_before_review'])} - go public later with `publish`")
    meta = core.load_json(core.job_dir(job["id"], "metadata.json"), {})
    if not (meta.get("lint") or {}).get("ok"): core.die("metadata has not passed lint - run `meta build` and fix the errors")
    f = meta["final"].get(target) or core.die(f"no final metadata for {target}")
    prev = job.get("uploads", {}).get(target)
    if prev and prev.get("video_id") and not force:
        core.die(f"{target} was already uploaded as {prev['video_id']} - not uploading a duplicate (use --force to override)")
    path = media_path(job, target)
    guard()
    print(f"Quota used today (est.): {quota_today()} / 10000; an upload costs ~{COST['insert']}")
    if quota_today() + COST["insert"] + COST["thumbnail"] > 10000:
        core.die("not enough API quota left today for another upload - it resets at midnight Pacific time; upload the rest tomorrow")
    body = {"snippet": {k: f[k] for k in ("title", "description", "tags", "categoryId", "defaultLanguage", "defaultAudioLanguage")},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": b["made_for_kids"],
                       "containsSyntheticMedia": voice.needs_disclosure(job)}}
    req = service().videos().insert(part="snippet,status", body=body, notifySubscribers=b.get("notify_subscribers", True),
                                    media_body=MediaFileUpload(path, chunksize=32 * 2**20, resumable=True))
    size = os.path.getsize(path); resp, tries, last = None, 0, -10
    print(f"Uploading {target}: {os.path.basename(path)} ({size / 2**30:.2f} GB) as {privacy}...")
    while resp is None:
        try:
            st, resp = req.next_chunk()
            if st and int(st.progress() * 100) >= last + 10:
                last = int(st.progress() * 100); print(f"  {last}%", flush=True)
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and tries < 6:
                tries += 1; time.sleep(2 ** tries); continue
            raise
    spend("insert")
    vid = resp["id"]
    job.setdefault("uploads", {})[target] = {"video_id": vid, "privacy_requested": privacy, "uploaded_at": core.now(),
                                            "file": path, "url": f"https://youtu.be/{vid}"}
    core.save_job(job)
    print(f"Uploaded: https://youtu.be/{vid}")
    if job.get("thumbnails", {}).get(target):
        set_thumbnail(job, target)
    core.mark(job, "upload", targets=sorted(job["uploads"]))
    return verify(job, target)


def set_thumbnail(job, target):
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    up = job["uploads"][target]; th = job["thumbnails"][target]
    guard()
    try:
        r = service().thumbnails().set(videoId=up["video_id"], media_body=MediaFileUpload(th["path"], mimetype="image/jpeg")).execute()
        spend("thumbnail")
        up["thumbnail"] = {"set": True, "at": core.now(), "url": r["items"][0].get("maxres", r["items"][0]["default"])["url"]}
        print("Custom thumbnail set.")
    except HttpError as e:
        up["thumbnail"] = {"set": False, "error": str(e)[:300]}
        print(f"Thumbnail NOT set: {str(e)[:200]}\n  (custom thumbnails need a phone-verified channel)")
    core.save_job(job)


# ------------------------------------------------------------------ verify

def _norm(s): return re.sub(r"[ \t]+\n", "\n", (s or "").replace("\r\n", "\n")).strip()


def verify(job, target):
    up = job.get("uploads", {}).get(target) or core.die(f"{target} has not been uploaded")
    want = core.load_json(core.job_dir(job["id"], "metadata.json"))["final"][target]
    v = _get(up["video_id"])
    checks = []
    def c(name, ok, detail=""): checks.append({"check": name, "ok": bool(ok), "detail": detail})
    if not v:
        c("video exists", False, "videos.list returned nothing")
    else:
        sn, st = v["snippet"], v["status"]
        c("video exists", True, up["video_id"])
        c("on your channel", sn["channelId"] == core.config("channel")["channel_id"], sn["channelId"])
        c("title", sn["title"] == want["title"], sn["title"])
        c("description", _norm(sn.get("description")) == _norm(want["description"]))
        # YouTube may return tags in a different order (e.g. sorted), so compare as sets
        c("tags", sorted(t.lower() for t in sn.get("tags", [])) == sorted(t.lower() for t in want["tags"]), f"{len(sn.get('tags', []))} tags")
        c("category", sn.get("categoryId") == want["categoryId"], sn.get("categoryId"))
        c("privacy", st["privacyStatus"] == up.get("privacy_now", up["privacy_requested"]), st["privacyStatus"])
        if up["privacy_requested"] == "unlisted" and st["privacyStatus"] == "private":
            c("not locked private", False, "requested unlisted but YouTube kept it private - unverified API projects lock uploads to private")
        c("upload status", st["uploadStatus"] in ("uploaded", "processed"),
          st["uploadStatus"] + (f" ({st.get('rejectionReason') or st.get('failureReason')})" if st["uploadStatus"] in ("rejected", "failed") else ""))
        proc = v.get("processingDetails", {}).get("processingStatus", "?")
        c("processing", proc in ("processing", "succeeded"), proc)
        secs = _iso_seconds(v["contentDetails"].get("duration"))
        if proc == "succeeded" and secs:
            exp = job["long_form"]["duration"] if target == "long" else next(s["duration"] for s in job["shorts"] if f"short{s['n']}" == target)
            c("duration matches file", abs(secs - exp) <= 2, f"{secs}s vs {exp:.0f}s")
        if job.get("thumbnails", {}).get(target):
            c("custom thumbnail", up.get("thumbnail", {}).get("set"), up.get("thumbnail", {}).get("error", ""))
    ok = all(x["ok"] for x in checks)
    pending = v and v.get("processingDetails", {}).get("processingStatus") == "processing"
    up["verify"] = {"at": core.now(), "ok": ok, "processing": bool(pending), "checks": checks}
    core.mark(job, "verify", status="done" if ok and not pending else ("pending" if ok else "failed"),
              **{t: u.get("verify", {}).get("ok") for t, u in job["uploads"].items()})
    return up["verify"]


# ------------------------------------------------------------------ changes to live videos

def update(video_id, changes, apply=False, job=None):
    """Change title/description/tags/category on ANY channel video. Backs up first, verifies after."""
    allowed = {"title", "description", "tags", "categoryId"}
    bad = set(changes) - allowed
    if bad: core.die(f"only {sorted(allowed)} can be changed here, not {sorted(bad)}")
    guard()
    v = _get(video_id, "snippet,status") or core.die(f"no video {video_id} on this channel")
    if v["snippet"]["channelId"] != core.config("channel")["channel_id"]: core.die("that video is not on your channel")
    sn = v["snippet"]
    new = {k: sn[k] for k in ("title", "description", "tags", "categoryId", "defaultLanguage", "defaultAudioLanguage") if k in sn}
    new.update(changes)
    diff = {k: (sn.get(k), new[k]) for k in changes if sn.get(k) != new[k]}
    if not diff:
        print("No change - the video already has these values."); return {"changed": False}
    for k, (a, bb) in diff.items():
        print(f"  {k}:\n    OLD: {str(a)[:300]}\n    NEW: {str(bb)[:300]}")
    if not apply:
        print("\nDry run. Re-run with --apply to change the live video."); return {"changed": False, "dry_run": True}
    bpath = _backup_video(v, "before-update")
    r = service().videos().update(part="snippet", body={"id": video_id, "snippet": new}).execute(); spend("update")
    got = r["snippet"]
    norm = lambda k, x: _norm(x) if k == "description" else sorted(t.lower() for t in x or []) if k == "tags" else x  # API returns tags re-ordered
    fails = [k for k in changes if norm(k, got.get(k)) != norm(k, new[k])]
    res = {"changed": True, "backup": bpath, "verified": not fails, "mismatch": fails, "at": core.now()}
    log = os.path.join(core.DATA, "changes.json")
    core.save_json(log, core.load_json(log, []) + [{"video_id": video_id, "fields": sorted(changes), **res}])
    print(f"Backup: {bpath}\nVerified from API response: {'OK' if not fails else 'MISMATCH ' + ', '.join(fails)}")
    return res


def schedule(job, per_day=None, start=None, times=None, confirm=False):
    """Spread a job's uploaded, verified Shorts over the coming days, N per day at fixed local times.

    Slots already taken (by any job, in data/schedule.json) are skipped, so recordings never stack up
    on the same day. Without --confirm it only prints the plan.
    """
    cfg = core.config("brand")["shorts"]
    per_day = per_day or cfg.get("posts_per_day", 3)
    # --times are the PC's local clock; the brand default is UTC so it follows the audience, not this PC's DST
    tz = datetime.timezone.utc if not times and cfg.get("post_times_utc") else datetime.datetime.now().astimezone().tzinfo
    times = times or cfg.get("post_times_utc") or cfg.get("post_times_local", ["12:00", "17:00", "20:00"])
    if len(times) < per_day: core.die(f"need at least {per_day} post times, got {times}")
    times = sorted(times)[:per_day]
    ledger_path = os.path.join(core.DATA, "schedule.json")
    ledger = core.load_json(ledger_path, {"slots": []})
    taken = {s["at"] for s in ledger["slots"]}
    ups = job.get("uploads", {})
    todo = [t for t in sorted(ups, key=lambda k: int(k[5:]) if k[5:].isdigit() else 0)
            if t.startswith("short") and not ups[t].get("publish_at") and ups[t].get("privacy_now", "private") == "private"]
    if not todo: core.die("no uploaded Shorts waiting to be scheduled (upload + verify them first)")
    local = datetime.datetime.now().astimezone().tzinfo
    day = datetime.date.fromisoformat(start) if start else datetime.date.today() + datetime.timedelta(days=1)
    now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    plan = []
    while len(plan) < len(todo):
        for hm in times:
            h, m = map(int, hm.split(":"))
            at = datetime.datetime.combine(day, datetime.time(h, m), tz).astimezone(datetime.timezone.utc)
            iso = at.strftime("%Y-%m-%dT%H:%M:%SZ")
            if at > now and iso not in taken and len(plan) < len(todo):
                plan.append((todo[len(plan)], iso, at.astimezone(local).strftime("%a %d %b %H:%M")))
        day += datetime.timedelta(days=1)
    for t, iso, local in plan: print(f"  {t:8} {ups[t].get('video_id', '?'):12} -> {local} (local)  {iso}")
    if not confirm:
        print("Plan only. Re-run with --confirm after the user has reviewed these Shorts and said yes.")
        return {"ok": True, "dry_run": True, "plan": [{"target": t, "publish_at": iso} for t, iso, _ in plan]}
    results = []
    for t, iso, _ in plan:
        r = publish(job, t, "public", publish_at=iso, confirm=True)
        if r["ok"]:
            ups[t]["publish_at"] = iso
            ledger["slots"].append({"at": iso, "job": job["id"], "target": t, "video_id": ups[t]["video_id"]})
            core.save_json(ledger_path, ledger)
        results.append({"target": t, **r})
    core.save_job(job)
    return {"ok": all(r["ok"] for r in results), "scheduled": results}


def publish(job, target, privacy, publish_at=None, confirm=False):
    """Change a job upload's privacy. Needs --confirm, which the skill only passes after the user says so."""
    up = job.get("uploads", {}).get(target) or core.die(f"{target} has not been uploaded")
    if privacy not in ("public", "unlisted", "private"): core.die("privacy must be public, unlisted or private")
    if not (up.get("verify") or {}).get("ok"): core.die("the upload has not passed verification - run `verify` first")
    if not confirm: core.die("publishing needs --confirm (only after the user has reviewed the video and said yes)")
    guard()
    v = _get(up["video_id"], "snippet,status")
    _backup_video(v, "before-publish")
    st = {k: v["status"][k] for k in ("privacyStatus", "selfDeclaredMadeForKids", "embeddable", "license",
                                      "publicStatsViewable", "containsSyntheticMedia") if k in v["status"]}
    st["privacyStatus"] = "private" if publish_at else privacy
    if publish_at: st["publishAt"] = publish_at
    r = service().videos().update(part="status", body={"id": up["video_id"], "status": st}).execute(); spend("update")
    got = r["status"]["privacyStatus"]
    up["privacy_now"] = got
    up.setdefault("history", []).append({"at": core.now(), "requested": privacy, "publish_at": publish_at, "result": got})
    ok = got == st["privacyStatus"]
    core.mark(job, "publish", status="done" if ok else "failed", **{target: got})
    if not ok:
        print(f"YouTube kept it {got}. If the API project is unverified, YouTube locks API uploads to private until "
              "the project passes a compliance audit - publish it from YouTube Studio instead.")
    return {"ok": ok, "privacy": got, "publish_at": publish_at}
