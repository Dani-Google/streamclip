# StreamClip web

A small web front-end for StreamClip — paste a YouTube link, get vertical
captioned Shorts. It is a thin wrapper over the CLI in
`~/workspace/streamclip-mvp/` (`./run.sh`); it does not re-implement the
pipeline.

## Run

```bash
cd ~/workspace/streamclip-mvp/web
./venv/bin/python app.py
# open http://localhost:5000
```

First time only:

```bash
python3 -m venv venv
venv/bin/pip install flask
```

System tools needed (already on this VM): `ffmpeg`, `yt-dlp`, and the
Whisper model at `~/workspace/models/whisper-small` (used by `run.sh`
via the whisper venv).

## Use

1. Paste a YouTube Live or video link.
2. Pick a mode:
   - **📼 Recorded video / VOD** — downloads the video, finds the loud
     moments, cuts 1–5 clips of 15–60s each. This is the fast path.
   - **🔴 YouTube Live** — watches the stream as it airs and clips each
     segment. Slower on this machine (see limits).
3. Watch the progress (fetching → detecting → captioning → rendering →
   done), then play each clip in the browser or download it. The caption
   text is shown under each clip.

Jobs run one at a time (this VM has ~1.5 CPUs); new jobs queue up.
Each job keeps its clips under `jobs/<id>/outbox/` and intermediates
under `jobs/<id>/work/`.

## Files

```
app.py                  Flask app + job queue + progress tracking
templates/index.html    the form + honest-limits box + recent jobs
templates/job.html      live progress page + playable clips + log
static/style.css        dark theme, red accent
jobs/                   per-job outbox/work + job.json (created at runtime)
venv/                   python venv with Flask (created at setup)
```

## Honest limits

- **Live capture lags on this VM.** A 60s live segment can take 2–4
  minutes to capture here (proxied/slow connection), so live clips trail
  the live moment by minutes. Real-time watching needs a VPS (Oracle
  Cloud free tier or a ~$5/mo VPS).
- **Local only.** The app binds `0.0.0.0:5000`, so it is reachable on
  your local network, but there is no public link. For a public link,
  run it on a VPS behind a domain/reverse proxy.
- **No auto-upload yet.** Uploaders in the CLI are stubs — download the
  clips and post them by hand.
- **One job at a time**, by design — Whisper on CPU is the bottleneck.
