"""YouTube Partner Program tracker: how far the channel is from monetization, and whether the pace is enough.

Only what YouTube counts: public long-form + live watch hours over 365 days and Shorts views over
90 days, both WITHOUT paid (ADVERTISING) traffic - promoted views never qualify. Studio's own
"qualified" figures (Earn tab) are a little stricter still; record them with `--studio` when read.

data/ypp/daily.json keeps one row per day so the daily report and weekly review compare like for like.
"""
import datetime, os
from . import core, youtube, analytics

DEADLINE = datetime.date(datetime.date.today().year, 12, 31)  # your monetization goal date
NEED = {"subs": 1000, "hours": 4000, "shorts_views": 10_000_000}        # full YPP (ads)
NEED_LOW = {"subs": 500, "hours": 3000, "shorts_views": 3_000_000}      # fan-funding tier
PATH = os.path.join(core.DATA, "ypp", "daily.json")


def _split(ya, start, end, ctype):
    """(all views, all hours, paid views, paid hours) for one content type."""
    rows = analytics._q(ya, start, end, "views,estimatedMinutesWatched", dimensions="insightTrafficSourceType",
                        filters=f"creatorContentType=={ctype}")
    ad = next((r for r in rows if r["insightTrafficSourceType"] == "ADVERTISING"), {"views": 0, "estimatedMinutesWatched": 0})
    return (sum(r["views"] for r in rows), sum(r["estimatedMinutesWatched"] for r in rows) / 60,
            ad["views"], ad["estimatedMinutesWatched"] / 60)


def measure(studio=None):
    ya = youtube.analytics_service(); s = youtube.service()
    ch = s.channels().list(part="statistics", id=core.config("channel")["channel_id"]).execute(); youtube.spend("list")
    subs = int(ch["items"][0]["statistics"]["subscriberCount"])
    end = datetime.date.today() - datetime.timedelta(days=analytics.LAG)
    y0, q0 = end - datetime.timedelta(days=364), end - datetime.timedelta(days=89)
    vod, live, sh = _split(ya, y0, end, "videoOnDemand"), _split(ya, y0, end, "liveStream"), _split(ya, q0, end, "shorts")
    hours = (vod[1] - vod[3]) + (live[1] - live[3])
    shorts_views = sh[0] - sh[2]
    # the latest single day, for the daily report
    # the newest single day is often still empty at LAG days; step back to the latest complete one
    for back in range(3):
        last = end - datetime.timedelta(days=back)
        day = analytics._q(ya, last, last, "views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost",
                           dimensions="creatorContentType")
        if day: break
    by = {r["creatorContentType"]: r for r in day}
    g = lambda k, m: by.get(k, {}).get(m, 0)
    days_left = (DEADLINE - datetime.date.today()).days
    row = {
        "date": str(datetime.date.today()), "data_through": str(end), "subscribers": subs,
        "organic_hours_365d": round(hours, 1), "organic_shorts_views_90d": int(shorts_views),
        "paid_excluded": {"long_hours": round(vod[3] + live[3], 1), "shorts_views": int(sh[2])},
        "day": {"date": str(last), "subs_gained": sum(r["subscribersGained"] for r in day), "subs_lost": sum(r["subscribersLost"] for r in day),
                "shorts_views": g("shorts", "views"), "long_views": g("videoOnDemand", "views") + g("liveStream", "views"),
                "long_hours": round((g("videoOnDemand", "estimatedMinutesWatched") + g("liveStream", "estimatedMinutesWatched")) / 60, 1),
                "long_avg_view_sec": g("videoOnDemand", "averageViewDuration")},
        "days_left": days_left,
        "pace_needed": {"hours_per_day": round(max(0, NEED["hours"] - hours) / max(days_left, 1), 1),
                        "shorts_views_per_day": int(max(0, NEED["shorts_views"] - shorts_views) / max(min(days_left, 90), 1))},
    }
    if studio: row["studio_qualified"] = studio
    log = core.load_json(PATH, {"rows": []})
    log["rows"] = [r for r in log["rows"] if r["date"] != row["date"]] + [row]
    core.save_json(PATH, log)
    return row


def report(row=None):
    log = core.load_json(PATH, {"rows": []})
    row = row or (log["rows"][-1] if log["rows"] else measure())
    prev = next((r for r in reversed(log["rows"]) if r["date"] < row["date"]), None)
    d = lambda k: f" ({row[k] - prev[k]:+,})" if prev and isinstance(row[k], (int, float)) else ""
    pct = lambda have, need: f"{min(100, have / need * 100):.2f}%"
    print(f"Monetization - {row['date']} (data through {row['data_through']}), {row['days_left']} days to {DEADLINE}")
    print(f"  Subscribers        {row['subscribers']:>12,}{d('subscribers')}   need 1,000  -> {'MET' if row['subscribers'] >= 1000 else pct(row['subscribers'], 1000)}")
    print(f"  Watch hours (365d) {row['organic_hours_365d']:>12,}{d('organic_hours_365d')}   need 4,000  -> {pct(row['organic_hours_365d'], 4000)}"
          f"   pace needed {row['pace_needed']['hours_per_day']} h/day")
    print(f"  Shorts views (90d) {row['organic_shorts_views_90d']:>12,}{d('organic_shorts_views_90d')}   need 10M    -> {pct(row['organic_shorts_views_90d'], 10_000_000)}"
          f"   pace needed {row['pace_needed']['shorts_views_per_day']:,}/day")
    dy = row["day"]
    print(f"  {dy['date']}: +{dy['subs_gained']}/-{dy['subs_lost']} subs, {dy['shorts_views']:,} Shorts views, {dy['long_views']:,} long views "
          f"({dy['long_hours']} h, avg {dy['long_avg_view_sec'] // 60}:{dy['long_avg_view_sec'] % 60:02d})")
    print(f"  Excluded paid traffic: {row['paid_excluded']['long_hours']} long h, {row['paid_excluded']['shorts_views']:,} Shorts views")
    if row.get("studio_qualified"): print(f"  Studio Earn tab: {row['studio_qualified']}")
    return row


# ------------------------------------------------------------------ daily report (pure Python, no Claude needed)

def _upcoming():
    """(published in the last 24h, due in the next 24h, Shorts rendered but not uploaded) across all jobs."""
    now = datetime.datetime.now(datetime.timezone.utc)
    past, due, waiting = [], [], []
    for j in core.all_jobs():
        ups = j.get("uploads", {})
        for t, u in ups.items():
            at = u.get("publish_at")
            if not at: continue
            when = datetime.datetime.fromisoformat(at.replace("Z", "+00:00"))
            item = f"{t} ({u.get('video_id')}) {when.astimezone().strftime('%a %H:%M')}"
            if now - datetime.timedelta(days=1) <= when <= now: past.append(item)
            elif now < when <= now + datetime.timedelta(days=1): due.append(item)
        rendered = [f"short{s['n']}" for s in j.get("shorts", [])]
        missing = [t for t in rendered if t not in ups]
        if missing: waiting.append(f"{j['id']}: {', '.join(missing)}")
    return past, due, waiting


def _top_videos(day):
    ya = youtube.analytics_service()
    rows = analytics._q(ya, day, day, "views,estimatedMinutesWatched,subscribersGained", dimensions="video",
                        sort="-views", maxResults=5)
    idx = {v["id"]: v for v in core.load_json(os.path.join(core.DATA, "channel_index.json"), {"videos": []})["videos"]}
    return [(r["views"], r["subscribersGained"], idx.get(r["video"], {}).get("title", r["video"])[:70],
             "Short" if idx.get(r["video"], {}).get("seconds", 999) <= 180 else "long") for r in rows]


def daily_report(row=None):
    """Write data/ypp/reports/<date>.md from the logged numbers - the daily report costs no Claude usage."""
    log = core.load_json(PATH, {"rows": []})
    today = str(datetime.date.today())
    row = row or next((r for r in log["rows"] if r["date"] == today), None) or measure()  # sync already measured today
    rows = [r for r in log["rows"] if r["date"] < row["date"]]
    prev = rows[-1] if rows else None
    wk = next((r for r in reversed(rows) if r["date"] <= str(datetime.date.fromisoformat(row["date"]) - datetime.timedelta(days=7))), rows[0] if rows else None)
    delta = lambda k, base: f"{row[k] - base[k]:+,.1f}" if base else "n/a"
    pace = (row["organic_hours_365d"] - wk["organic_hours_365d"]) / max(1, (datetime.date.fromisoformat(row["date"]) - datetime.date.fromisoformat(wk["date"])).days) if wk else 0
    need = row["pace_needed"]["hours_per_day"]
    verdict = "AHEAD" if pace >= need * 1.1 else "ON PACE" if pace >= need * 0.9 else "BEHIND"
    past, due, waiting = _upcoming()
    dy = row["day"]
    try: top = _top_videos(datetime.date.fromisoformat(dy["date"]))
    except Exception as e: top = []; print(f"top videos unavailable: {e!r}")
    if waiting: action = f"Upload + schedule the rendered Shorts ({'; '.join(waiting)}) - say 'continue' in a NEW Claude session."
    elif not any("long" in x for x in past + due) and dy["long_views"] < 20:
        action = "Long-form is the only route that counts: record/publish the next full mission (or stream)."
    else: action = "Schedule is running - record the next mission; no Claude session needed today."
    conv = f"{dy['subs_gained'] / max(1, dy['shorts_views'] + dy['long_views']) * 100:.2f}%"
    md = [f"# Daily report - {row['date']}", "",
          f"Data through {dy['date']} (YouTube Analytics lags ~2 days). {row['days_left']} days to {DEADLINE}.", "",
          "| Requirement | Now | vs yesterday | vs 7 days | Need |", "|---|---|---|---|---|",
          f"| Subscribers | {row['subscribers']:,} | {delta('subscribers', prev)} | {delta('subscribers', wk)} | 1,000 |",
          f"| Organic watch hours, 365d | {row['organic_hours_365d']:,} | {delta('organic_hours_365d', prev)} | {delta('organic_hours_365d', wk)} | 4,000 |",
          f"| Organic Shorts views, 90d | {row['organic_shorts_views_90d']:,} | {delta('organic_shorts_views_90d', prev)} | {delta('organic_shorts_views_90d', wk)} | 10M |", "",
          f"**Pace:** {pace:.1f} h/day actual (7-day) vs {need} h/day needed -> **{verdict}**", "",
          f"**{dy['date']}:** +{dy['subs_gained']}/-{dy['subs_lost']} subs, {dy['shorts_views']:,} Shorts views, "
          f"{dy['long_views']:,} long views ({dy['long_hours']} h, avg {dy['long_avg_view_sec'] // 60}:{dy['long_avg_view_sec'] % 60:02d}), "
          f"subscriber conversion {conv}. Paid traffic excluded.", "",
          "**Best content that day:**"] + [f"- {v:,} views, +{s} subs - {t} ({k})" for v, s, t, k in top[:3]] + ["",
          "**Went live (24h):** " + (", ".join(past) or "none"),
          "**Due (next 24h):** " + (", ".join(due) or "none"), "",
          f"**Next action:** {action}", ""]
    out = os.path.join(core.DATA, "ypp", "reports", f"{row['date']}.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f: f.write("\n".join(md))
    print("\n".join(md)); return out
