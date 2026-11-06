"""Daily read-only sync: everything the APIs can read about the channel, saved under data/ so Claude
always starts from fresh numbers. Runs from Windows Task Scheduler (`ytm.py sync`); never writes to YouTube.

Studio-only charts the API cannot read (e.g. "When your viewers are on YouTube") go in data/studio/ as
screenshots - Claude reads the newest ones on request.
"""
import datetime, json, os, traceback
from . import core, youtube, analytics, ypp, dashboard

CH = core.config("channel")["channel_id"]
SYNC = os.path.join(core.DATA, "sync")


def _comments(days=30):
    s = youtube.service()
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    idx = core.load_json(os.path.join(core.DATA, "channel_index.json"), {"videos": []})
    title = {v["id"]: v["title"] for v in idx["videos"]}
    out, tok = [], None
    while True:
        r = s.commentThreads().list(part="snippet,replies", allThreadsRelatedToChannelId=CH, maxResults=100,
                                    order="time", pageToken=tok).execute(); youtube.spend("list")
        done = False
        for it in r["items"]:
            top = it["snippet"]["topLevelComment"]; sn = top["snippet"]
            if sn["publishedAt"] < since: done = True; break
            if sn.get("authorChannelId", {}).get("value") == CH: continue
            replies = it.get("replies", {}).get("comments", [])
            out.append({"comment_id": top["id"], "video_id": sn.get("videoId"), "video": title.get(sn.get("videoId"), "?"),
                        "author": sn["authorDisplayName"], "text": sn["textOriginal"], "date": sn["publishedAt"][:10],
                        "likes": sn.get("likeCount", 0),
                        "channel_replied": any(x["snippet"].get("authorChannelId", {}).get("value") == CH for x in replies)})
        tok = r.get("nextPageToken")
        if done or not tok: break
    core.save_json(os.path.join(core.DATA, "comments", "latest.json"), {"at": core.now(), "since": since[:10], "comments": out})
    return {"total": len(out), "unreplied": sum(not c["channel_replied"] for c in out)}


def _audience():
    ya = youtube.analytics_service()
    start, end = analytics._period(28)
    geo = analytics._q(ya, start, end, "views,estimatedMinutesWatched", dimensions="country", sort="-views", maxResults=15)
    s90, _ = analytics._period(90)
    daily = analytics._q(ya, s90, end, "views", dimensions="day", sort="day")
    dow = {}
    for r in daily: dow.setdefault(datetime.date.fromisoformat(r["day"]).strftime("%a"), []).append(r["views"])
    data = {"at": core.now(), "period": [str(start), str(end)], "countries": geo,
            "day_of_week_avg_views_90d": {k: round(sum(v) / len(v)) for k, v in dow.items()}, "daily_90d": daily}
    core.save_json(os.path.join(core.DATA, "analytics", "audience-latest.json"), data)
    return {"top_countries": [g["country"] for g in geo[:5]]}


def run():
    os.makedirs(SYNC, exist_ok=True); os.makedirs(os.path.join(core.DATA, "studio"), exist_ok=True)
    status = {"at": core.now(), "steps": {}}
    try:
        youtube.guard(); status["token"] = "ok"
    except BaseException as e:  # guard() exits on a wrong channel; an expired token raises from google-auth
        status["token"] = f"FAILED: {e!r} - sign in again: move ~/.youtube-api/token.json aside, run `py -3.12 ytm.py yt whoami`, pick your channel"
        core.save_json(os.path.join(SYNC, "latest.json"), status)
        return status
    for name, fn in (("analytics", lambda: analytics.report(28)), ("comments", _comments), ("audience", _audience), ("ypp", ypp.measure), ("report", ypp.daily_report)):
        try:
            r = fn()
            status["steps"][name] = {"ok": True, **({"views_28d": r["growth"]["views"]["now"], "subscribers": r["channel"]["subscriberCount"]}
                                                    if name == "analytics" else {"hours_365d": r["organic_hours_365d"], "shorts_90d": r["organic_shorts_views_90d"]} if name == "ypp" else {"file": r} if name == "report" else r)}
        except Exception as e:
            status["steps"][name] = {"ok": False, "error": repr(e)[:300]}
            with open(os.path.join(SYNC, "errors.log"), "a", encoding="utf-8") as f:
                f.write(f"\n[{core.now()}] {name}\n{traceback.format_exc()}")
    status["ok"] = all(s["ok"] for s in status["steps"].values())
    core.save_json(os.path.join(SYNC, "latest.json"), status)
    try: dashboard.build()  # after latest.json, so the page shows this run's health
    except Exception as e: print(f"dashboard failed: {e!r}")
    return status
