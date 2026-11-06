"""Performance and organic growth tracking via the YouTube Analytics API (read-only)."""
import csv, datetime, json, os, subprocess, sys
from . import core, youtube

LAG = 2  # Analytics data is complete about two days behind


def _q(ya, start, end, metrics, **kw):
    r = ya.reports().query(ids="channel==MINE", startDate=str(start), endDate=str(end), metrics=metrics, **kw).execute()
    cols = [h["name"] for h in r["columnHeaders"]]
    return [dict(zip(cols, row)) for row in r.get("rows", [])]


def _period(days, back=0):
    end = datetime.date.today() - datetime.timedelta(days=LAG + back * days)
    return end - datetime.timedelta(days=days - 1), end


TOTALS = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost,likes,shares,comments"


def snapshot(days=28):
    youtube.guard()
    ya = youtube.analytics_service()
    start, end = _period(days)
    ch = youtube.service().channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]
    idx = youtube.index()
    dur = {v["id"]: v["seconds"] for v in idx["videos"]}
    title = {v["id"]: v["title"] for v in idx["videos"]}
    per_video = _q(ya, start, end, "views,estimatedMinutesWatched,averageViewPercentage,subscribersGained",
                   dimensions="video", sort="-views", maxResults=200)
    for r in per_video:
        r["title"] = title.get(r["video"], "?"); r["format"] = "short" if dur.get(r["video"], 999) <= 180 else "long"
    snap = {"at": core.now(), "period": [str(start), str(end)],
            "channel": {k: int(ch.get(k, 0)) for k in ("subscriberCount", "viewCount", "videoCount")},
            "totals": (_q(ya, start, end, TOTALS) or [{}])[0],
            "traffic": _q(ya, start, end, "views", dimensions="insightTrafficSourceType", sort="-views"),
            "videos": per_video}
    core.save_json(os.path.join(core.DATA, "analytics", f"{datetime.date.today()}.json"), snap)
    return snap


def report(days=28):
    """This period vs the one before, organic share, Shorts vs long-form, and the top movers."""
    snap = snapshot(days)
    ya = youtube.analytics_service()
    ps, pe = _period(days, back=1)
    prev = (_q(ya, ps, pe, TOTALS) or [{}])[0]
    cur = snap["totals"]
    def delta(k):
        a, b = cur.get(k, 0) or 0, prev.get(k, 0) or 0
        return {"now": a, "before": b, "change_pct": round((a - b) / b * 100, 1) if b else None}
    traffic = {r["insightTrafficSourceType"]: r["views"] for r in snap["traffic"]}
    total = sum(traffic.values()) or 1
    paid = traffic.get("ADVERTISING", 0)
    fmt = {"short": 0, "long": 0}
    for v in snap["videos"]: fmt[v["format"]] += v["views"]
    snaps = sorted(os.listdir(os.path.join(core.DATA, "analytics")))
    since = None
    if len(snaps) >= 2:
        first = core.load_json(os.path.join(core.DATA, "analytics", snaps[0]))
        since = {"since": snaps[0][:10], "subscribers": snap["channel"]["subscriberCount"] - first["channel"]["subscriberCount"],
                 "views": snap["channel"]["viewCount"] - first["channel"]["viewCount"]}
    rep = {"period": snap["period"], "previous": [str(ps), str(pe)],
           "growth": {k: delta(k) for k in ("views", "estimatedMinutesWatched", "subscribersGained", "subscribersLost", "averageViewPercentage")},
           "net_subscribers": (cur.get("subscribersGained", 0) or 0) - (cur.get("subscribersLost", 0) or 0),
           "organic_share": round(1 - paid / total, 3),
           "traffic_sources": {k: round(v / total, 3) for k, v in sorted(traffic.items(), key=lambda x: -x[1])},
           "format_views": fmt, "top_videos": snap["videos"][:8], "tracked_since_first_snapshot": since,
           "channel": snap["channel"]}
    core.save_json(os.path.join(core.DATA, "analytics", "reports", f"report-{datetime.date.today()}.json"), rep)
    return rep


def retention(video_id):
    """Audience-retention curve from the API, written as the CSV that /yt-retention's retention.py reads."""
    youtube.guard()
    ya = youtube.analytics_service()
    v = youtube._get(video_id, "snippet,contentDetails") or core.die("no such video")
    secs = youtube._iso_seconds(v["contentDetails"]["duration"])
    start = v["snippet"]["publishedAt"][:10]; end = datetime.date.today() - datetime.timedelta(days=1)
    rows = _q(ya, start, end, "audienceWatchRatio", dimensions="elapsedVideoTimeRatio", filters=f"video=={video_id}")
    if not rows: core.die("no retention data yet (needs some views and ~2 days)")
    path = os.path.join(core.DATA, "analytics", "retention", f"{video_id}.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["position_percent", "watching_percent"])
        for r in rows: w.writerow([round(r["elapsedVideoTimeRatio"] * 100, 1), round(r["audienceWatchRatio"] * 100, 1)])
    p = subprocess.run([sys.executable, os.path.join(core.SKILLS, "yt-retention", "retention.py"), path, "--duration", str(secs)],
                       capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    return {"title": v["snippet"]["title"], "seconds": secs, "csv": path, "report": p.stdout or p.stderr}
