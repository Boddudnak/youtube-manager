"""ffprobe / ffmpeg helpers: probing, HDR tone-mapping, encoder choice, frame grabs."""
import json, os, subprocess, sys
from .core import die

HDR_TRC = {"smpte2084", "arib-std-b67"}


def run(cmd, cwd=None, quiet=True):
    """Run ffmpeg/ffprobe; raise with the tail of stderr on failure."""
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        tail = "\n".join(p.stderr.strip().splitlines()[-15:])
        raise RuntimeError(f"{os.path.basename(cmd[0])} failed ({p.returncode}):\n{tail}")
    return p


def run_progress(cmd, duration, label, cwd=None):
    """Run ffmpeg printing a % line as it goes (needs '-progress pipe:1 -nostats' in cmd)."""
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8", errors="replace")
    last = -10
    import threading
    err = []
    t = threading.Thread(target=lambda: err.extend(p.stderr.readlines()), daemon=True); t.start()
    for line in p.stdout:
        if line.startswith("out_time_us=") and duration:
            try: pct = int(int(line.split("=")[1]) / 1e6 / duration * 100)
            except ValueError: continue
            if pct >= last + 10:
                last = pct - pct % 10
                print(f"  {label}: {min(pct, 100)}%", flush=True)
    p.wait(); t.join(timeout=5)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({p.returncode}):\n" + "".join(err[-15:]))


def probe(path):
    p = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    d = json.loads(p.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    if not v: die(f"no video stream in {path}")
    num, den = (v.get("avg_frame_rate") or "0/1").split("/")
    fps = float(num) / float(den) if float(den) else 0
    trc = v.get("color_transfer", "")
    return {
        "duration": float(d["format"].get("duration") or v.get("duration") or 0),
        "size_bytes": int(d["format"].get("size", 0)),
        "container": d["format"].get("format_name"),
        "vcodec": v.get("codec_name"), "width": v.get("width"), "height": v.get("height"),
        "fps": round(fps, 3), "pix_fmt": v.get("pix_fmt"),
        "color_transfer": trc, "color_primaries": v.get("color_primaries"), "color_space": v.get("color_space"),
        "hdr": trc in HDR_TRC,
        "acodec": a.get("codec_name") if a else None,
        "audio_channels": a.get("channels") if a else 0,
        "sample_rate": int(a.get("sample_rate", 0)) if a else 0,
    }


def sdr_chain(info, width=None, grade=""):
    """Filter chain that grades (approved SDR grade, optional), scales (optionally) and tone-maps HDR to SDR bt709."""
    f = [grade] if grade else []
    if width: f.append(f"scale={width}:-2:flags=lanczos")
    if info.get("hdr"):
        f.append("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
                 "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv")
    f.append("format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709")
    return ",".join(f)


_ENC = None
def h264_encoder():
    """Hardware H.264 if this GPU has one that actually works, else libx264."""
    global _ENC
    if _ENC: return _ENC
    for enc, opts in (("h264_amf", ["-quality", "quality", "-rc", "cqp", "-qp_i", "18", "-qp_p", "20", "-qp_b", "22"]),
                      ("h264_nvenc", ["-preset", "p5", "-cq", "19"]),
                      ("h264_qsv", ["-global_quality", "20"])):
        try:
            run(["ffmpeg", "-hide_banner", "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.2",
                 "-c:v", enc, "-f", "null", "-"])
            _ENC = [enc, *opts]; return _ENC
        except Exception:
            continue
    _ENC = ["libx264", "-preset", "medium", "-crf", "18"]
    return _ENC


def grab_frame(src, t, out, info, width=1280, grade=""):
    """One SDR still at time t (fast keyframe seek, then exact)."""
    pre = max(0.0, t - 2.0)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-ss", f"{pre:.3f}", "-i", src, "-ss", f"{t - pre:.3f}",
         "-frames:v", "1", "-vf", sdr_chain(info, width, grade), "-q:v", "2", out])
    return out
