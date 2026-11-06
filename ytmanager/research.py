"""Competitor research through the official API (public data only): discover, track, scan, rank outliers."""
import collections, datetime, html, json, os, re, statistics, subprocess, sys
from . import core, youtube

PATH = os.path.join(core.CONFIG, "competitors.json")


def tracked():
    return core.load_json(PATH, {"channels": []})["channels"]


def discover(queries, per_query=25):
    """Channels publishing videos that match the queries, ranked by how often they show up."""
    s = youtube.service()
    hits = collections.Counter(); examples = collections.defaultdict(list)
    for q in queries:
        r = s.search().list(part="snippet", q=q, type="video", maxResults=min(50, per_query), order="relevance",
                            relevanceLanguage="en").execute(); youtube.spend("search")
        for it in r["items"]:
            cid = it["snippet"]["channelId"]; hits[cid] += 1
            if len(examples[cid]) < 2: examples[cid].append(html.unescape(it["snippet"]["title"]))
    own = core.config("channel")["channel_id"]
    ids = [c for c, _ in hits.most_common() if c != own]
    rows = []
    for i in range(0, len(ids), 50):
        r = s.channels().list(part="snippet,statistics", id=",".join(ids[i:i + 50])).execute(); youtube.spend("list")
        for c in r["items"]:
            st = c["statistics"]
            rows.append({"id": c["id"], "title": c["snippet"]["title"], "handle": c["snippet"].get("customUrl"),
                         "subscribers": int(st.get("subscriberCount", 0)), "videos": int(st.get("videoCount", 0)),
                         "query_hits": hits[c["id"]], "examples": examples[c["id"]],
                         "tracked": any(t["id"] == c["id"] for t in tracked())})
    rows.sort(key=lambda r: (-r["query_hits"], -r["subscribers"]))
    core.save_json(os.path.join(core.DATA, "competitors", f"discover-{datetime.date.today()}.json"), {"queries": queries, "channels": rows})
    return rows


def add(ref, why):
    s = youtube.service()
    kw = {"forHandle": ref} if ref.startswith("@") else {"id": ref}
    r = s.channels().list(part="snippet,statistics", **kw).execute(); youtube.spend("list")
    if not r.get("items"): core.die(f"no channel {ref}")
    c = r["items"][0]
    data = core.load_json(PATH, {"channels": []})
    if any(t["id"] == c["id"] for t in data["channels"]): print(f"already tracked: {c['snippet']['title']}"); return
    data["channels"].append({"id": c["id"], "title": c["snippet"]["title"], "handle": c["snippet"].get("customUrl"),
                             "why": why, "added": str(datetime.date.today()),
                             "subscribers_at_add": int(c["statistics"].get("subscriberCount", 0))})
    core.save_json(PATH, data)
    print(f"tracking {c['snippet']['title']} ({len(data['channels'])} competitors)")


def remove(ref):
    data = core.load_json(PATH, {"channels": []})
    data["channels"] = [c for c in data["channels"] if ref not in (c["id"], c.get("handle"), c["title"])]
    core.save_json(PATH, data)


def scan(recent=15):
    chans = tracked()
    if len(chans) < 10: print(f"note: only {len(chans)} competitors tracked - the brief asks for at least 10")
    s = youtube.service()
    vids, profiles = [], []
    for i in range(0, len(chans), 50):
        r = s.channels().list(part="contentDetails,statistics,snippet", id=",".join(c["id"] for c in chans[i:i + 50])).execute(); youtube.spend("list")
        for c in r["items"]:
            pl = c["contentDetails"]["relatedPlaylists"]["uploads"]
            items = s.playlistItems().list(part="contentDetails", playlistId=pl, maxResults=min(50, recent)).execute()["items"]; youtube.spend("list")
            ids = [x["contentDetails"]["videoId"] for x in items]
            if not ids: continue
            vr = s.videos().list(part="snippet,statistics,contentDetails", id=",".join(ids)).execute(); youtube.spend("list")
            mine = []
            for v in vr["items"]:
                secs = youtube._iso_seconds(v["contentDetails"]["duration"])
                row = {"channel": c["snippet"]["title"], "title": v["snippet"]["title"], "views": int(v["statistics"].get("viewCount", 0)),
                       "url": f"https://youtu.be/{v['id']}", "duration": secs, "is_short": secs <= 180,
                       "published": v["snippet"]["publishedAt"], "tags": v["snippet"].get("tags", [])}
                mine.append(row); vids.append(row)
            dates = sorted(datetime.datetime.fromisoformat(v["published"].replace("Z", "+00:00")) for v in mine)
            span_w = max(1.0, (dates[-1] - dates[0]).days / 7) if len(dates) > 1 else 1.0
            longs = [v["views"] for v in mine if not v["is_short"]]; shorts_ = [v["views"] for v in mine if v["is_short"]]
            profiles.append({"channel": c["snippet"]["title"], "subscribers": int(c["statistics"].get("subscriberCount", 0)),
                             "uploads_per_week": round(len(mine) / span_w, 1),
                             "median_long_views": int(statistics.median(longs)) if longs else None,
                             "median_short_views": int(statistics.median(shorts_)) if shorts_ else None,
                             "share_shorts": round(len(shorts_) / len(mine), 2)})
    day = datetime.date.today()
    scan_path = os.path.join(core.DATA, "competitors", f"scan-{day}.json")
    core.save_json(scan_path, {"at": core.now(), "profiles": profiles, "videos": vids})
    swipe_in = os.path.join(core.DATA, "competitors", f"swipe-input-{day}.json")
    with open(swipe_in, "w", encoding="utf-8") as f:
        json.dump([{k: v[k] for k in ("channel", "title", "views", "url", "duration")} for v in vids], f, ensure_ascii=True)
    p = subprocess.run([sys.executable, os.path.join(core.SKILLS, "yt-viral", "swipe.py"), swipe_in, "--min", "1.5", "--json"],
                       capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    outliers = json.loads(p.stdout)["outliers"] if p.returncode == 0 else []
    tags = collections.Counter(t.lower() for v in vids for t in v["tags"])
    res = {"profiles": profiles, "outliers": outliers[:20], "top_tags": tags.most_common(30), "scan_file": scan_path}
    core.save_json(os.path.join(core.DATA, "competitors", f"report-{day}.json"), res)
    return res
