"""StreamClip web — paste a YouTube link, get vertical captioned Shorts.

Thin web front-end over the existing CLI (../run.sh). Jobs run in a
background thread, one at a time (this VM has ~1.5 CPUs; Whisper already
uses 2 threads). Each job gets its own outbox/work dir under jobs/<id>/.

Run:  python app.py            (http://localhost:5000)
"""

import json
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                     # ~/workspace/streamclip-mvp
RUN_SH = ROOT / "run.sh"
JOBS_DIR = HERE / "jobs"
JOBS_DIR.mkdir(exist_ok=True)

app = Flask(__name__)

# ---------------------------------------------------------------- jobs ---

STAGES = ["queued", "fetching", "detecting", "captioning", "rendering",
          "done", "error"]

jobs = {}          # id -> job dict (also persisted to jobs/<id>/job.json)
jobs_lock = threading.Lock()
queue = []         # job ids waiting to run
worker_started = False


def _save(job):
    (JOBS_DIR / job["id"] / "job.json").write_text(json.dumps(job, indent=2))


def _new_job(url, mode, max_clips, clip_len, max_segments):
    jid = uuid.uuid4().hex[:8]
    jobdir = JOBS_DIR / jid
    (jobdir / "outbox").mkdir(parents=True)
    (jobdir / "work").mkdir(parents=True)
    job = {
        "id": jid, "url": url, "mode": mode,
        "max_clips": max_clips, "clip_len": clip_len,
        "max_segments": max_segments,
        "status": "queued", "stage": "queued", "progress": 0,
        "message": "Waiting for a free slot…", "log": [],
        "clips": [], "error": None,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with jobs_lock:
        jobs[jid] = job
        queue.append(jid)
    _save(job)
    return job


def _set(job, **kw):
    with jobs_lock:
        job.update(kw)
    _save(job)


def _log(job, line):
    with jobs_lock:
        job["log"].append(line)
        job["log"] = job["log"][-200:]
    _save(job)


def _caption_text(ass_path):
    """Join the word-per-event ASS lines into one readable caption string."""
    words = []
    try:
        for line in Path(ass_path).read_text(errors="ignore").splitlines():
            if line.startswith("Dialogue:"):
                text = line.split(",", 9)[-1].strip()
                text = re.sub(r"\{[^}]*\}", "", text).strip()
                if text and (not words or words[-1] != text):
                    words.append(text)
    except OSError:
        pass
    return " ".join(words)


def _collect_clips(job):
    outbox = JOBS_DIR / job["id"] / "outbox"
    work = JOBS_DIR / job["id"] / "work"
    clips = []
    for mp4 in sorted(outbox.glob("*.mp4")):
        tag = mp4.stem                      # e.g. vod_clip1 / live001_clip1
        ass = work / f"{tag}.ass"
        # live segments keep their ASS in work/<tag>/<tag>_clip1.ass
        if not ass.exists():
            for cand in work.rglob(f"{tag}.ass"):
                ass = cand
                break
        clips.append({
            "name": mp4.name,
            "size_mb": round(mp4.stat().st_size / 1e6, 1),
            "captions": _caption_text(ass) if ass.exists() else "",
        })
    return clips


def _stage_from_line(job, line):
    """Map CLI stdout lines to the progress stages."""
    if "Live check:" in line or "SIMULATED live" in line:
        _set(job, stage="fetching", progress=15,
             message="Stream found — capturing the first segment…")
    elif "video ->" in line and "moment(s)" in line:
        _set(job, stage="detecting", progress=30,
             message="Loud moments found — transcribing speech…")
    elif "words transcribed" in line:
        _set(job, stage="captioning", progress=55,
             message="Transcribing speech (local Whisper)…")
    elif "->" in line and line.strip().endswith(")") and "clip" in line:
        _set(job, stage="rendering", progress=80,
             message="Cutting + captioning the vertical clip…")
    elif "no moments above threshold" in line:
        _set(job, message="No loud moment in this part — skipping…")


def _run_job(job):
    jid = job["id"]
    jobdir = JOBS_DIR / jid
    outbox, work = jobdir / "outbox", jobdir / "work"
    if job["mode"] == "live":
        cmd = [str(RUN_SH), "watch", job["url"],
               "--max-segments", str(job["max_segments"]),
               "--clip-len", str(job["clip_len"]),
               "--outbox", str(outbox), "--work", str(work)]
    else:
        cmd = [str(RUN_SH), "clip", job["url"],
               "--max-clips", str(job["max_clips"]),
               "--clip-len", str(job["clip_len"]),
               "--outbox", str(outbox), "--work", str(work)]
    _set(job, status="running", stage="fetching", progress=5,
         message="Fetching the video…")
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                _log(job, line)
                _stage_from_line(job, line)
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"pipeline exited with code {proc.returncode}")
        clips = _collect_clips(job)
        if not clips:
            raise RuntimeError("Pipeline finished but produced no clips — "
                               "the video may have no loud moments.")
        _set(job, status="done", stage="done", progress=100,
             message=f"Done — {len(clips)} clip(s) ready.",
             clips=clips)
    except Exception as exc:  # noqa: BLE001 — surfaced to the user as text
        _set(job, status="error", stage="error",
             message="Job failed.", error=str(exc))


def _worker():
    while True:
        jid = None
        with jobs_lock:
            if queue:
                jid = queue.pop(0)
        if jid is None:
            time.sleep(1)
            continue
        _run_job(jobs[jid])


def _ensure_worker():
    global worker_started
    if not worker_started:
        threading.Thread(target=_worker, daemon=True).start()
        worker_started = True


# --------------------------------------------------------------- routes ---

@app.route("/")
def index():
    recent = sorted(jobs.values(), key=lambda j: j["created_at"],
                    reverse=True)[:8]
    return render_template("index.html", jobs=recent)


@app.route("/job/<jid>")
def job_page(jid):
    job = jobs.get(jid)
    if not job:
        abort(404)
    return render_template("job.html", job=job)


@app.route("/api/jobs", methods=["POST"])
def create_job():
    _ensure_worker()
    url = (request.form.get("url") or "").strip()
    mode = request.form.get("mode") or "vod"
    try:
        max_clips = max(1, min(5, int(request.form.get("max_clips") or 3)))
        clip_len = max(15, min(60, int(request.form.get("clip_len") or 30)))
        max_segments = max(1, min(10, int(request.form.get("max_segments")
                                           or 3)))
    except ValueError:
        return jsonify({"error": "Numbers only for clips / length."}), 400
    if mode not in ("vod", "live"):
        return jsonify({"error": "Unknown mode."}), 400
    if not re.match(r"^https?://(www\.)?(youtube\.com|youtu\.be)/", url):
        return jsonify({"error": "Paste a YouTube link "
                        "(youtube.com or youtu.be)."}), 400
    job = _new_job(url, mode, max_clips, clip_len, max_segments)
    return jsonify({"id": job["id"]}), 201


@app.route("/api/jobs/<jid>")
def job_status(jid):
    job = jobs.get(jid)
    if not job:
        return jsonify({"error": "unknown job"}), 404
    return jsonify(job)


@app.route("/jobs/<jid>/clip/<name>")
def serve_clip(jid, name):
    if not re.match(r"^[\w.\-]+$", name) or ".." in name:
        abort(400)
    path = JOBS_DIR / jid / "outbox" / name
    if not path.is_file() or path.suffix.lower() != ".mp4":
        abort(404)
    return send_file(path, mimetype="video/mp4", conditional=True,
                     download_name=name)


@app.route("/jobs/<jid>/clip/<name>/download")
def download_clip(jid, name):
    if not re.match(r"^[\w.\-]+$", name) or ".." in name:
        abort(400)
    path = JOBS_DIR / jid / "outbox" / name
    if not path.is_file() or path.suffix.lower() != ".mp4":
        abort(404)
    return send_file(path, mimetype="video/mp4", as_attachment=True,
                     download_name=name)


# ------------------------------------------------------------ boot state ---

def _load_existing():
    for jf in JOBS_DIR.glob("*/job.json"):
        try:
            job = json.loads(jf.read_text())
        except (OSError, ValueError):
            continue
        if job.get("status") in ("queued", "running"):
            job["status"] = "error"
            job["stage"] = "error"
            job["error"] = "Server restarted while this job was running."
        jobs[job["id"]] = job


_load_existing()

if __name__ == "__main__":
    _ensure_worker()
    app.run(host="0.0.0.0", port=5000, threaded=True)
