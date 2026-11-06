"""One-page YouTube Manager dashboard: data/dashboard.html, built by Python from the files the sync writes.

No Claude involved - `ytm.py dashboard` (and every `ytm.py sync`) rebuilds it. Sources:
  data/ypp/daily.json             monetization rows (one per day)
  data/analytics/<date>.json      28-day snapshot (totals, traffic, top videos)
  data/analytics/search-terms-latest.json
  library/*/job.json              YouTube uploads + schedule (live status: one videos.list call, 1 unit)
  data/posts/instagram-*.json     Instagram Reels queue
  data/mission/plan.md            weekly targets;  data/mission/decisions.json  open decisions
  data/sync/latest.json, data/quota.json, data/ypp/reports/<date>.md (next action)
"""
import datetime, glob, html, json, os, re
from . import core, ypp

OUT = os.path.join(core.DATA, "dashboard.html")
DECISIONS = os.path.join(core.DATA, "mission", "decisions.json")
TZ_NOTE = "times in your PC's local time"
e = lambda s: html.escape(str(s))


def _latest(pattern):
    files = sorted(f for f in glob.glob(pattern) if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.(json|md)", os.path.basename(f)))
    return files[-1] if files else None


def _targets():
    """Weekly hour targets from the plan's table: [(date, hours)]."""
    try: txt = open(os.path.join(core.DATA, "mission", "plan.md"), encoding="utf-8").read()
    except OSError: return []
    out = []
    for mon, day, hrs in re.findall(r"^\|\s*\**(Nov|Dec) (\d+)[^|]*\|\s*\**([\d,]+)\**\s*\|", txt, re.M):
        out.append((datetime.date(datetime.date.today().year, 11 if mon == "Nov" else 12, int(day)), int(hrs.replace(",", ""))))
    return out


def _youtube_live(jobs):
    """Current privacy/views of every job upload, in one API call; {} if offline."""
    ids = [u["video_id"] for j in jobs for u in j.get("uploads", {}).values() if u.get("video_id")]
    if not ids: return {}
    try:
        from . import youtube
        got = {}
        for i in range(0, len(ids), 50):
            r = youtube.service().videos().list(part="status,statistics", id=",".join(ids[i:i + 50])).execute(); youtube.spend("list")
            got.update({v["id"]: v for v in r.get("items", [])})
        return got
    except Exception as ex:
        print(f"dashboard: live YouTube status unavailable ({ex!r}); using job files")
        return {}


def _when(iso, tz=None):
    if not iso: return None
    d = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if d.tzinfo is None:  # Instagram rows carry a timezone name instead
        try:
            from zoneinfo import ZoneInfo
            d = d.replace(tzinfo=ZoneInfo(tz or "UTC"))
        except Exception: d = d.astimezone()
    return d.astimezone()


# ------------------------------------------------------------------ pieces of the page

def _bar(have, need, label, sub):
    p = min(100, have / need * 100) if need else 0
    return (f'<div class="req"><div class="req-top"><span>{e(label)}</span><b>{have:,.1f}</b>'.replace(".0</b>", "</b>")
            + f'<span class="muted"> / {need:,}</span></div>'
            f'<div class="track"><div class="fill{" met" if p >= 100 else ""}" style="width:{max(p, 0.6):.2f}%"></div></div>'
            f'<div class="muted small">{p:.2f}% · {e(sub)}</div></div>')


def _line(points, color="var(--accent)", target=None, h=150, w=560, unit=""):
    """Small SVG line chart. points: [(date, value)]; target: [(date, value)] drawn dashed."""
    pts = [(d, v) for d, v in points if v is not None]
    if not pts: return '<p class="muted">No data yet - it fills in day by day.</p>'
    allp = pts + (target or [])
    d0 = min(d for d, _ in allp); d1 = max(d for d, _ in allp)
    span = max(1, (d1 - d0).days); vmax = max(v for _, v in allp) or 1
    X = lambda d: 36 + (d - d0).days / span * (w - 48)
    Y = lambda v: h - 22 - v / vmax * (h - 36)
    path = lambda ps: " ".join(f"{'M' if i == 0 else 'L'}{X(d):.1f},{Y(v):.1f}" for i, (d, v) in enumerate(ps))
    svg = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">',
           f'<line x1="36" x2="{w - 12}" y1="{h - 22}" y2="{h - 22}" class="axis"/>',
           f'<text x="30" y="{Y(vmax) + 4:.0f}" class="tick" text-anchor="end">{vmax:,.0f}{unit}</text>',
           f'<text x="30" y="{h - 18}" class="tick" text-anchor="end">0</text>',
           f'<text x="36" y="{h - 4}" class="tick">{d0:%b %d}</text>',
           f'<text x="{w - 12}" y="{h - 4}" class="tick" text-anchor="end">{d1:%b %d}</text>']
    if target: svg.append(f'<path d="{path(target)}" class="target"/>')
    svg.append(f'<path d="{path(pts)}" fill="none" stroke="{color}" stroke-width="2.5"/>')
    svg += [f'<circle cx="{X(d):.1f}" cy="{Y(v):.1f}" r="3.5" fill="{color}"><title>{d:%b %d}: {v:,.1f}{unit}</title></circle>' for d, v in pts]
    return "".join(svg) + "</svg>"


def _table(head, rows, empty="Nothing here."):
    if not rows: return f'<p class="muted">{e(empty)}</p>'
    return ('<div class="tw"><table><thead><tr>' + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table></div>")


def _pill(text, kind=""): return f'<span class="pill {kind}">{e(text)}</span>'


# ------------------------------------------------------------------ build

def build(live=True):
    now = datetime.datetime.now().astimezone()
    rows = core.load_json(ypp.PATH, {"rows": []})["rows"]
    r = rows[-1] if rows else None
    jobs = core.all_jobs()
    snap = core.load_json(_latest(os.path.join(core.DATA, "analytics", "*.json")) or "", {})
    terms = core.load_json(os.path.join(core.DATA, "analytics", "search-terms-latest.json"), {})
    sync = core.load_json(os.path.join(core.DATA, "sync", "latest.json"), {})
    decisions = core.load_json(DECISIONS, {"open": []})["open"]
    from . import youtube
    quota = youtube.quota_today()
    yt = _youtube_live(jobs) if live else {}

    S = []  # sections
    # --- headline
    if r:
        week = next((x for x in reversed(rows[:-1]) if x["date"] <= str(datetime.date.fromisoformat(r["date"]) - datetime.timedelta(days=7))), rows[0])
        days = max(1, (datetime.date.fromisoformat(r["date"]) - datetime.date.fromisoformat(week["date"])).days)
        pace = (r["organic_hours_365d"] - week["organic_hours_365d"]) / days if week is not r else 0
        need = r["pace_needed"]["hours_per_day"]
        verdict = "AHEAD" if pace >= need * 1.1 else "ON PACE" if pace >= need * 0.9 else "BEHIND"
        dy = r["day"]
        S.append('<section class="card wide"><h2>Monetization (YouTube Partner Program)</h2><div class="reqs">'
                 + _bar(r["subscribers"], 1000, "Subscribers", "met" if r["subscribers"] >= 1000 else "need 1,000")
                 + _bar(r["organic_hours_365d"], 4000, "Organic watch hours · 365 days", f"need {need} h/day from now")
                 + _bar(r["organic_shorts_views_90d"], 10_000_000, "Organic Shorts views · 90 days", f"need {r['pace_needed']['shorts_views_per_day']:,}/day")
                 + f'</div><div class="kpis"><div><b>{r["days_left"]}</b><span>days to Dec 31</span></div>'
                 f'<div><b>{pace:.1f}</b><span>h/day actual (7-day)</span></div><div><b>{need}</b><span>h/day needed</span></div>'
                 f'<div>{_pill(verdict, "bad" if verdict == "BEHIND" else "good")}<span>verdict</span></div></div>'
                 f'<p class="muted small">Paid (ad) traffic excluded - it never counts: {r["paid_excluded"]["long_hours"]} long h, '
                 f'{r["paid_excluded"]["shorts_views"]:,} Shorts views. Data through {e(r["data_through"])} (YouTube Analytics lags ~2 days).'
                 + (f' Studio Earn tab: {e(r["studio_qualified"])}.' if r.get("studio_qualified") else "") + "</p></section>")
        tgt = _targets()
        hours = [(datetime.date.fromisoformat(x["date"]), x["organic_hours_365d"]) for x in rows]
        S.append('<section class="card"><h2>Watch hours vs plan</h2>'
                 + _line(hours, target=[(hours[0][0], hours[0][1])] + tgt if tgt else None, unit=" h")
                 + '<p class="muted small">Solid: organic hours (365d). Dashed: weekly targets from the mission plan; Dec 6 is GO/NO-GO at 1,000 h.</p>'
                 + _table(["Week ending", "Target h", "Status"], [[f"{d:%b %d}", f"{t:,}", _pill("passed" if hours[-1][1] >= t else "missed" if d < now.date() else "upcoming",
                          "good" if hours[-1][1] >= t else "bad" if d < now.date() else "")] for d, t in tgt]) + "</section>")
        S.append('<section class="card"><h2>Daily trend</h2>'
                 + _line([(datetime.date.fromisoformat(x["day"]["date"]), x["day"]["shorts_views"]) for x in rows], "var(--c2)")
                 + '<p class="muted small">Shorts views per day</p>'
                 + _line([(datetime.date.fromisoformat(x["day"]["date"]), x["day"]["long_hours"]) for x in rows], "var(--accent)", unit=" h")
                 + '<p class="muted small">Long-form hours per day</p>'
                 + f'<p><b>{e(dy["date"])}:</b> +{dy["subs_gained"]}/−{dy["subs_lost"]} subs · {dy["shorts_views"]:,} Shorts views · '
                 f'{dy["long_views"]:,} long views · avg view {dy["long_avg_view_sec"] // 60}:{dy["long_avg_view_sec"] % 60:02d}</p></section>')
    else:
        S.append('<section class="card wide"><h2>Monetization</h2><p class="muted">No tracker rows yet - run <code>ytm.py sync</code>.</p></section>')

    # --- next action + decisions
    rep = _latest(os.path.join(core.DATA, "ypp", "reports", "*.md"))
    action = ""
    if rep:
        m = re.search(r"\*\*Next action:\*\*\s*(.+)", open(rep, encoding="utf-8").read())
        action = m.group(1) if m else ""
    S.append('<section class="card"><h2>Next action</h2>' + (f'<p class="big">{e(action)}</p>' if action else '<p class="muted">No report yet.</p>')
             + '<h3>Open decisions</h3>' + ("<ul>" + "".join(f"<li>{e(d)}</li>" for d in decisions) + "</ul>" if decisions else '<p class="muted">None.</p>')
             + '<p class="muted small">Edit data/mission/decisions.json to change this list.</p></section>')

    # --- channel 28 days
    if snap:
        t = snap["totals"]; tr = snap.get("traffic", [])
        tot = sum(x["views"] for x in tr) or 1
        S.append('<section class="card"><h2>YouTube · last 28 days</h2><div class="kpis">'
                 f'<div><b>{t["views"]:,}</b><span>views</span></div><div><b>{t["estimatedMinutesWatched"] / 60:,.0f}</b><span>hours</span></div>'
                 f'<div><b>+{t["subscribersGained"] - t["subscribersLost"]:,}</b><span>net subs</span></div><div><b>{t["averageViewDuration"]}s</b><span>avg view</span></div></div>'
                 '<h3>Where views came from</h3>' + "".join(
                     f'<div class="src"><span>{e(x["insightTrafficSourceType"].replace("_", " ").title().replace("Yt ", "YouTube "))}{" (paid)" if x["insightTrafficSourceType"] == "ADVERTISING" else ""}</span>'
                     f'<div class="track sm"><div class="fill{" paid" if x["insightTrafficSourceType"] == "ADVERTISING" else ""}" style="width:{x["views"] / tot * 100:.1f}%"></div></div><b>{x["views"]:,}</b></div>'
                     for x in tr[:7])
                 + f'<p class="muted small">{e(snap["period"][0])} → {e(snap["period"][1])}</p></section>')
        S.append('<section class="card"><h2>Top videos · 28 days</h2>' + _table(["Video", "Type", "Views", "Avg %", "Subs"], [
            [f'<a href="https://youtu.be/{e(v["video"])}">{e(v["title"][:60])}</a>', e(v.get("format", "")), f'{v["views"]:,}',
             f'{v.get("averageViewPercentage", 0):.0f}%', f'+{v.get("subscribersGained", 0)}'] for v in snap.get("videos", [])[:8]]) + "</section>")
    if terms.get("terms"):
        S.append('<section class="card"><h2>What people search to find you</h2>' + _table(["Search term", "Views", "Minutes"], [
            [e(x["insightTrafficSourceDetail"]), f'{x["views"]:,}', f'{x["estimatedMinutesWatched"]:,}'] for x in terms["terms"][:10]])
            + f'<p class="muted small">YouTube search, {e(terms["period"][0])} → {e(terms["period"][1])}</p></section>')

    # --- schedule: YouTube
    yrows = []
    for j in jobs:
        ups = j.get("uploads", {})
        for tname, u in sorted(ups.items(), key=lambda kv: kv[1].get("publish_at") or ""):
            v = yt.get(u.get("video_id"), {})
            when = _when(u.get("publish_at"))
            st = v.get("status", {}).get("privacyStatus") or u.get("privacy_requested", "?")
            state = "public" if st == "public" else "scheduled" if when and when > now else "live?" if when else st
            yrows.append([f'<a href="https://youtu.be/{e(u.get("video_id"))}">{e(tname)}</a>', e(j["id"][-4:]),
                          f'{when:%a %b %d %H:%M}' if when else "-", _pill(state, "good" if state == "public" else ""),
                          f'{int(v["statistics"].get("viewCount", 0)):,}' if v else "-"])
        for s in j.get("shorts", []):
            if f"short{s['n']}" not in ups: yrows.append([f"short{s['n']}", e(j["id"][-4:]), "-", _pill("rendered, not uploaded", "warn"), "-"])
    S.append('<section class="card wide"><h2>YouTube schedule</h2>' + _table(["Video", "Job", "Goes public", "Status", "Views"], yrows, "No uploads yet.")
             + f'<p class="muted small">{TZ_NOTE}; status and views {"live from YouTube" if yt else "from job files (offline)"}.</p></section>')

    # --- schedule: Instagram
    irows = []
    for f in sorted(glob.glob(os.path.join(core.DATA, "posts", "instagram-*.json"))):
        q = core.load_json(f, {})
        for p in q.get("posts", []):
            when = _when(p.get("date"), p.get("timezone"))
            state = "posted" if p.get("posted") else "due - check" if when and when < now else "scheduled" if p.get("scheduled") else "draft"
            irows.append([e(p.get("file", "").rsplit("-", 1)[-1].removesuffix(".mp4")), f'{when:%a %b %d %H:%M}' if when else "-", e(p.get("type", "")),
                          _pill(state, "good" if state == "posted" else "warn" if state.startswith("due") else ""),
                          e("Metricool" if p.get("metricool_id") else p.get("via", "Meta Business Suite"))])
    S.append('<section class="card wide"><h2>Instagram Reels</h2>' + _table(["Reel", "Time", "Type", "Status", "Scheduler"], irows, "No Reels queued.")
             + '<p class="muted small">From the local post records. Instagram\'s own numbers (reach, plays) need a Meta access token - not connected yet.</p></section>')

    # --- health
    tok = sync.get("token", "never run")
    steps = sync.get("steps", {})
    S.append('<section class="card"><h2>System health</h2><div class="kpis">'
             f'<div><b>{quota:,}</b><span>/ 10,000 API units today</span></div>'
             f'<div>{_pill("sign-in OK" if tok == "ok" else "sign-in needed", "good" if tok == "ok" else "bad")}<span>YouTube login</span></div></div>'
             + _table(["Sync step", "Result"], [[e(k), _pill("ok", "good") if v.get("ok") else _pill(v.get("error", "failed")[:80], "bad")] for k, v in steps.items()])
             + f'<p class="muted small">Last sync {e(sync.get("at", "never"))}.' + ("" if tok == "ok" else f" {e(tok)}") + "</p></section>")

    page = TEMPLATE.replace("{{BUILT}}", f"{now:%a %b %d %Y, %H:%M}").replace("{{SECTIONS}}", "\n".join(S))
    with open(OUT, "w", encoding="utf-8") as f: f.write(page)
    print(f"dashboard: {OUT}")
    return OUT


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>YouTube Manager Dashboard</title>
<style>
:root { --bg:#f6f6fa; --card:#fff; --ink:#1b1b26; --muted:#6b6b80; --line:#e3e3ec; --accent:#6d4aff; --c2:#0e8f7e;
        --good:#137a3d; --goodbg:#e2f5e9; --bad:#b3261e; --badbg:#fbe5e3; --warn:#8a5a00; --warnbg:#fdf1d6; --paid:#c9c9d6; }
@media (prefers-color-scheme: dark) { :root { --bg:#0b0b12; --card:#15151f; --ink:#e8e8f0; --muted:#9a9ab0; --line:#2a2a3a; --accent:#a58bff;
        --c2:#3cc9b4; --good:#6fd99a; --goodbg:#163222; --bad:#ff8a80; --badbg:#3a1714; --warn:#f2c46b; --warnbg:#3a2d10; --paid:#4a4a5e; } }
* { box-sizing:border-box } body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif }
header { padding:20px 16px 4px; max-width:1180px; margin:0 auto } header h1 { margin:0; font-size:22px; color:var(--accent) }
main { max-width:1180px; margin:0 auto; padding:12px 16px 40px; display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:14px }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; min-width:0 } .wide { grid-column:1/-1 }
h2 { font-size:16px; margin:0 0 12px } h3 { font-size:13px; margin:14px 0 6px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em }
.muted { color:var(--muted) } .small { font-size:12.5px } .big { font-size:16px; font-weight:600 } a { color:var(--accent) }
.reqs { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:16px }
.req-top { display:flex; gap:6px; align-items:baseline; flex-wrap:wrap } .req-top b { font-size:22px; margin-left:auto }
.track { height:10px; background:var(--line); border-radius:6px; overflow:hidden; margin:6px 0 4px; flex:1 } .track.sm { height:7px; margin:0 }
.fill { height:100%; background:var(--accent); border-radius:6px } .fill.met { background:var(--good) } .fill.paid { background:var(--paid) }
.kpis { display:flex; flex-wrap:wrap; gap:18px; margin:14px 0 6px } .kpis div { display:flex; flex-direction:column }
.kpis b { font-size:20px } .kpis span { font-size:12px; color:var(--muted) }
.pill { display:inline-block; padding:1px 9px; border-radius:20px; font-size:12px; font-weight:600; background:var(--line); width:max-content }
.pill.good { background:var(--goodbg); color:var(--good) } .pill.bad { background:var(--badbg); color:var(--bad) } .pill.warn { background:var(--warnbg); color:var(--warn) }
.src { display:grid; grid-template-columns:130px 1fr 60px; gap:8px; align-items:center; font-size:13px; margin:5px 0 } .src b { text-align:right }
.tw { overflow-x:auto } table { width:100%; border-collapse:collapse; font-size:13px } th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line) }
th { color:var(--muted); font-weight:600 } .chart { width:100%; height:auto; display:block }
.axis { stroke:var(--line) } .tick { fill:var(--muted); font-size:10px } .target { fill:none; stroke:var(--muted); stroke-width:1.5; stroke-dasharray:5 4 }
ul { margin:0; padding-left:18px } code { background:var(--line); padding:1px 5px; border-radius:4px }
</style></head><body>
<header><h1>YouTube Manager Dashboard</h1><div class="muted small">Built {{BUILT}} by <code>ytm.py dashboard</code> · refreshes with every daily sync</div></header>
<main>
{{SECTIONS}}
</main></body></html>
"""
