"""YouTube Manager - YouTube channel management engine.  Run:  py ytm.py <command> ...   (py ytm.py -h)

Pipeline per recording:  intake -> analyze -> identify -> moments -> [grade, SDR only] -> edit -> shorts -> thumb -> meta -> yt upload -> yt verify -> yt publish
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ytmanager import core  # noqa: E402

core.utf8_stdout()

NEXT = {  # keyed by the first stage that is not done yet
    "intake": "py ytm.py intake <recording>",
    "analyze": "py ytm.py analyze {id}",
    "identify": "view the contact sheet, then: py ytm.py identify {id} --game \"...\" --mission \"...\"",
    "moments": "py ytm.py moments {id}",
    "edit": "py ytm.py edit plan {id}   (review the cuts)   then  py ytm.py edit render {id}",
    "shorts": "pick from the moments sheet: py ytm.py shorts add {id} --start .. --end .. --hook \"..\"   then  shorts render {id}",
    "thumbnail": "py ytm.py thumb candidates {id}   then  thumb make {id} --index N --text \"...\"",
    "metadata": "py ytm.py meta draft {id}   (write the text)   then  meta build {id}",
    "upload": "py ytm.py yt upload {id} long   (and short1..15) - uploads PRIVATE",
    "verify": "py ytm.py yt verify {id}",
    "publish": "user reviews the private videos in Studio, then: py ytm.py yt publish {id} <target> --privacy public --confirm",
}


def out(x):
    print(json.dumps(x, indent=1, ensure_ascii=False, default=str))


def job_status(j):
    st = j.get("stages", {})
    print(f"\n{j['id']}\n  source : {j['source']['path']}  ({j['source']['size_bytes'] / 2**30:.2f} GB, "
          f"{'read-only' if j['source'].get('read_only') else 'writable'})")
    p = j["probe"]
    print(f"  video  : {core.mmss(p['duration'])}  {p['width']}x{p['height']} @{p['fps']}  {p['vcodec']}"
          f"{'  HDR' if p['hdr'] else ''}  audio={p['acodec']}")
    print(f"  game   : {j.get('game') or '?'}  mission: {j.get('mission') or '?'}  ({j.get('game_confidence') or 'unconfirmed'})")
    for s in core.STAGES:
        v = st.get(s, {})
        print(f"    {'x' if v.get('status') == 'done' else ' '} {s:<10} {v.get('status', '')}")
    for t, u in j.get("uploads", {}).items():
        vf = u.get("verify", {})
        print(f"  upload : {t:<7} {u['url']}  {u.get('privacy_now', u['privacy_requested'])}  verify={vf.get('ok')}"
              f"{' (processing)' if vf.get('processing') else ''}")
    n = core.next_stage(j)
    print(f"  next   : {NEXT.get(n, 'done').format(id=j['id']) if n else 'all stages done'}")


def main():
    ap = argparse.ArgumentParser(prog="ytm.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    def P(name, **kw): return sp.add_parser(name, **kw)

    P("jobs"); s = P("status"); s.add_argument("job", nargs="?")
    P("scan"); P("sync", help="daily read-only refresh of analytics, comments and audience data")
    P("ypp", help="monetization progress vs the YouTube Partner Program (organic only, logged daily)")
    P("report", help="write today's daily report to data/ypp/reports/ (no Claude needed)")
    P("dashboard", help="rebuild data/dashboard.html (no Claude needed)")
    s = P("intake"); s.add_argument("path", nargs="+", help="one recording, or every part of one session in order"); s.add_argument("--copy", action="store_true"); s.add_argument("--full-hash", action="store_true")
    s.add_argument("--no-protect", action="store_true")
    s = P("split", help="session holding several missions -> one job per mission (lossless slices)"); s.add_argument("job")
    s.add_argument("--at", nargs="+", required=True, help="boundaries, e.g. 43:23 1:05:50"); s.add_argument("--names", nargs="+", required=True)
    s.add_argument("--reuse", action="store_true", help="keep pieces that already exist (re-split after moving a boundary)")
    s = P("check-original"); s.add_argument("job")
    s = P("analyze"); s.add_argument("job"); s.add_argument("--no-transcribe", action="store_true"); s.add_argument("--force", action="store_true")
    s = P("identify"); s.add_argument("job"); s.add_argument("--game", required=True); s.add_argument("--mission")
    s.add_argument("--number", type=int); s.add_argument("--confidence", default="high"); s.add_argument("--evidence", default="")
    s = P("moments"); s.add_argument("job"); s.add_argument("--length", type=int); s.add_argument("--count", type=int, default=10)
    s.add_argument("--min-dead", type=int, default=8)

    s = P("grade", help="optional SDR colour grade: preview BEFORE/AFTER, then approve (applied by edit render, shorts, thumbs)")
    s.add_argument("action", choices=["preview", "approve", "off", "show"]); s.add_argument("job")
    s.add_argument("--at"); s.add_argument("--seconds", type=float, default=20)
    for k in ("brightness", "contrast", "saturation", "gamma", "sharpen", "shadows", "vibrance"): s.add_argument(f"--{k}", type=float)

    s = P("edit"); s.add_argument("action", choices=["plan", "render", "chapters", "show"]); s.add_argument("job")
    s.add_argument("--mode", choices=["copy", "encode"]); s.add_argument("--min-dead", type=int, default=8)
    s.add_argument("--keep-head", action="store_true"); s.add_argument("--keep-tail", action="store_true"); s.add_argument("--target", type=int)

    s = P("shorts"); s.add_argument("action", choices=["add", "remove", "list", "render"]); s.add_argument("job")
    s.add_argument("n", nargs="?", type=int); s.add_argument("--start"); s.add_argument("--end"); s.add_argument("--hook")
    s.add_argument("--layout"); s.add_argument("--zoom", type=float, default=1.0); s.add_argument("--crop-x", type=float, default=0.5)
    s.add_argument("--note", default="")

    s = P("thumb"); s.add_argument("action", choices=["candidates", "make"]); s.add_argument("job")
    s.add_argument("--text"); s.add_argument("--target", default="long"); s.add_argument("--index", type=int); s.add_argument("--time")
    s.add_argument("--side", default="left", choices=["left", "right"]); s.add_argument("--zoom", type=float, default=1.0)

    s = P("meta"); s.add_argument("action", choices=["draft", "build", "lint", "show"]); s.add_argument("job"); s.add_argument("--force", action="store_true")

    s = P("yt"); s.add_argument("action", choices=["index", "upload", "verify", "thumbnail", "update", "publish", "schedule", "quota", "whoami"])
    s.add_argument("ref", nargs="?", help="job (or video id for update)"); s.add_argument("target", nargs="?")
    s.add_argument("--privacy"); s.add_argument("--force", action="store_true"); s.add_argument("--apply", action="store_true")
    s.add_argument("--per-day", type=int); s.add_argument("--start", help="first day, YYYY-MM-DD (default tomorrow)")
    s.add_argument("--times", help="local post times, e.g. 12:00,17:00,20:00")
    s.add_argument("--confirm", action="store_true"); s.add_argument("--at", help="scheduled publish time, ISO 8601 UTC")
    s.add_argument("--title"); s.add_argument("--description-file"); s.add_argument("--tags", help="comma separated")

    s = P("competitors"); s.add_argument("action", choices=["discover", "add", "remove", "list", "scan"])
    s.add_argument("args", nargs="*"); s.add_argument("--why", default=""); s.add_argument("--recent", type=int, default=15)

    s = P("analytics"); s.add_argument("action", choices=["snapshot", "report", "retention"]); s.add_argument("video", nargs="?")
    s.add_argument("--days", type=int, default=28)

    s = P("voice", help="cloned-voice narration (local Chatterbox, CPU)"); s.add_argument("action", choices=["prep", "use", "say"])
    s.add_argument("text", help="recording (prep), candidate number (use) or the words to say (say)"); s.add_argument("--out")
    s.add_argument("--ref"); s.add_argument("--job", help="mark this job as AI-narrated (forces the synthetic-content disclosure)")
    s.add_argument("--exaggeration", type=float, default=0.5); s.add_argument("--cfg", type=float, default=0.5)
    s.add_argument("--speed", type=float, help="tempo, e.g. 1.1 (default brand.voice.speed)"); s.add_argument("--no-check", action="store_true", help="skip the hear-back word check")
    s.add_argument("--energy", type=float, help="scale the [mood] tags, e.g. 1.3 (default brand.voice.energy)")

    a = ap.parse_args()
    from ytmanager import intake, analyze, moments, edit, shorts, thumbnail, metadata

    if a.cmd == "jobs":
        for j in core.all_jobs():
            print(f"{j['id']:<48} {j.get('game') or '?':<34} next: {core.next_stage(j) or 'done'}")
        if not core.all_jobs(): print("no jobs - drop recordings in inbox/ and run `py ytm.py scan`")
    elif a.cmd == "status":
        job_status(core.load_job(a.job))
    elif a.cmd == "dashboard":
        from ytmanager import dashboard
        os.startfile(dashboard.build())
    elif a.cmd == "report":
        from ytmanager import ypp
        ypp.daily_report()
    elif a.cmd == "ypp":
        from ytmanager import ypp
        ypp.report(ypp.measure())
    elif a.cmd == "sync":
        from ytmanager import sync
        out(sync.run())
    elif a.cmd == "scan":
        new = intake.scan()
        print("\n".join(new) if new else f"no new recordings in {core.INBOX}")
    elif a.cmd == "intake":
        job_status(intake.intake(a.path, copy=a.copy, full_hash=a.full_hash, protect=not a.no_protect))
    elif a.cmd == "split":
        for k in intake.split(core.load_job(a.job), a.at, a.names, reuse=a.reuse): job_status(k)
    elif a.cmd == "check-original":
        ok, msg = intake.verify_original(core.load_job(a.job)); print(msg); sys.exit(0 if ok else 2)
    elif a.cmd == "analyze":
        out(analyze.run(core.load_job(a.job), transcript=not a.no_transcribe, force=a.force))
    elif a.cmd == "identify":
        j = analyze.identify(core.load_job(a.job), a.game, a.mission, a.number, a.confidence, a.evidence); job_status(j)
    elif a.cmd == "moments":
        r = moments.find(core.load_job(a.job), a.length, a.count, a.min_dead)
        out({"sheet": r["sheet"], "candidates": r["candidates"], "dead_spans": r["dead_spans"]})
    elif a.cmd == "grade":
        from ytmanager import grade
        j = core.load_job(a.job)
        if a.action == "preview":
            out(grade.preview(j, a.at, a.seconds, **{k: getattr(a, k) for k in grade.KEYS}))
        elif a.action == "approve": out(grade.approve(j))
        elif a.action == "off": out(grade.approve(j, on=False))
        else: out({"settings": grade.settings(j), "job": j.get("grade", {}), "active": grade.chain(j)})
    elif a.cmd == "edit":
        j = core.load_job(a.job)
        if a.action == "plan": out(edit.plan(j, a.min_dead, not a.keep_head, not a.keep_tail))
        elif a.action == "render": out(edit.render(j, a.mode))
        elif a.action == "chapters": out(edit.chapter_points(j, a.target))
        else: out(core.load_json(core.job_dir(j["id"], "edit", "edl.json")))
    elif a.cmd == "shorts":
        j = core.load_job(a.job)
        if a.action == "add":
            if not (a.start and a.end and a.hook): core.die("shorts add needs --start --end --hook")
            out(shorts.plan_add(j, a.start, a.end, a.hook, a.layout, a.zoom, a.crop_x, a.note))
        elif a.action == "remove": shorts.plan_remove(j, a.n); out(j.get("shorts"))
        elif a.action == "list": out(j.get("shorts", []))
        else: out(shorts.render(j, a.n))
    elif a.cmd == "thumb":
        j = core.load_job(a.job)
        if a.action == "candidates":
            sheet, rows = thumbnail.candidates(j); out({"sheet": sheet, "candidates": rows})
        else:
            if not a.text: core.die("thumb make needs --text")
            out(thumbnail.make(j, a.text, a.target, a.index, a.time, a.side, a.zoom))
    elif a.cmd == "meta":
        j = core.load_job(a.job)
        if a.action == "draft": print(metadata.draft(j, a.force))
        elif a.action == "build":
            final, rep = metadata.build(j); out({"final": final, "lint": rep})
        elif a.action == "lint": out(metadata.lint(j))
        else: out(core.load_json(core.job_dir(j["id"], "metadata.json")))
    elif a.cmd == "yt":
        from ytmanager import youtube
        if a.action == "whoami":
            youtube.guard(); print(f"OK - token is for {core.config('channel')['title']} ({core.config('channel')['channel_id']})")
        elif a.action == "quota": print(f"estimated quota used today: {youtube.quota_today()} / 10000")
        elif a.action == "index":
            d = youtube.index(); print(f"indexed {d['count']} videos -> data/channel_index.json (+ backup in backups/channel/)")
        elif a.action == "upload": out(youtube.upload(core.load_job(a.ref), a.target or "long", a.privacy, a.force))
        elif a.action == "thumbnail":
            j = core.load_job(a.ref); youtube.set_thumbnail(j, a.target or "long"); out(youtube.verify(j, a.target or "long"))
        elif a.action == "verify":
            j = core.load_job(a.ref)
            for t in ([a.target] if a.target else sorted(j.get("uploads", {}))):
                r = youtube.verify(j, t)
                print(f"\n{t}: {'VERIFIED' if r['ok'] else 'PROBLEMS'}{' (still processing - verify again later)' if r['processing'] else ''}")
                for c in r["checks"]: print(f"  {'ok ' if c['ok'] else 'XX '} {c['check']:<22} {c['detail']}")
        elif a.action == "update":
            ch = {}
            if a.title: ch["title"] = a.title
            if a.description_file: ch["description"] = open(a.description_file, encoding="utf-8").read()
            if a.tags: ch["tags"] = [t.strip() for t in a.tags.split(",") if t.strip()]
            if not ch: core.die("give --title, --description-file and/or --tags")
            out(youtube.update(a.ref, ch, a.apply))
        elif a.action == "schedule":
            out(youtube.schedule(core.load_job(a.ref), a.per_day, a.start, a.times.split(",") if a.times else None, a.confirm))
        elif a.action == "publish":
            out(youtube.publish(core.load_job(a.ref), a.target, a.privacy or "public", a.at, a.confirm))
    elif a.cmd == "competitors":
        from ytmanager import research, youtube
        youtube.guard()
        if a.action == "discover":
            rows = research.discover(a.args or ["PS5 4K campaign gameplay no commentary"])
            for r in rows[:30]:
                print(f"{'*' if r['tracked'] else ' '} {r['query_hits']:>2} hits  {r['subscribers']:>9,} subs  {r['id']}  {r['title'][:34]:<34} | {r['examples'][0][:60]}")
        elif a.action == "add":
            for ref in a.args: research.add(ref, a.why)
        elif a.action == "remove":
            for ref in a.args: research.remove(ref)
        elif a.action == "list":
            for c in research.tracked(): print(f"{c['id']}  {c['title'][:36]:<36} {c.get('why', '')}")
            print(f"{len(research.tracked())} tracked")
        else: out(research.scan(a.recent))
    elif a.cmd == "analytics":
        from ytmanager import analytics
        if a.action == "snapshot":
            s = analytics.snapshot(a.days); out({"period": s["period"], "channel": s["channel"], "totals": s["totals"]})
        elif a.action == "report": out(analytics.report(a.days))
        else:
            r = analytics.retention(a.video or core.die("give a video id")); print(r["title"], f"({r['seconds']}s)"); print(r["report"])
    elif a.cmd == "voice":
        from ytmanager import voice
        if a.action == "prep": out(voice.prep(a.text))
        elif a.action == "use": out(voice.use(int(a.text)))
        else: out(voice.say([a.text], [a.out or core.die("--out <file.wav> is required")], a.ref, a.exaggeration, a.cfg, a.job, a.speed, a.energy, check=not a.no_check))


if __name__ == "__main__":
    main()
