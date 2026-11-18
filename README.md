# LiveClip — live stream → vertical captioned clips

LiveClip watches a YouTube Live stream as it airs, finds the loud moments
(reactions, shouting, big plays), and cuts them into vertical **1080×1920**
clips with burned-in captions — ready to post as Shorts / TikTok / Reels.
It also clips recorded videos and VOD URLs the same way.

No paid APIs, no sign-ups, no accounts. Transcription runs locally with
[faster-whisper](https://github.com/SYSTRAN/faster-whisper); everything else
is ffmpeg + numpy.

## How it works

```
source (file / VOD URL / YouTube Live)
  -> moments: audio RMS energy peaks (loud reactions = highlights)
  -> clip: 30–60s window around each peak
  -> captions: faster-whisper (small, local CPU), word-level -> ASS
  -> render: center-crop 9:16, scale 1080x1920, burn captions, keep audio
  -> outbox/*.mp4
```

## Install

Requirements: **Python 3.10+**, **ffmpeg** (with libx264 + libass), **yt-dlp**.

```bash
git clone https://github.com/Dani-Google/liveclip.git
cd liveclip

python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

The Whisper `small` model downloads automatically from Hugging Face on
first use (~500 MB). If you already have a local model, point at it with
`LIVECLIP_WHISPER_MODEL=/path/to/model`.

## Usage

```bash
# Clip a local file or a VOD URL (3 clips x 45s)
./run.sh clip video.mp4 --max-clips 3 --clip-len 45
./run.sh clip https://www.youtube.com/watch?v=XXXX

# Watch a YouTube Live stream, clip each 60s segment as it airs
./run.sh watch https://www.youtube.com/watch?v=XXXX --max-segments 4

# Test the live loop without a stream on air (segments a local file)
./run.sh watch --simulate video.mp4 --max-segments 3
```

Finished clips land in `outbox/`. Options: `--clip-len` (seconds per clip),
`--max-clips`, `--segment` (live segment length), `--max-segments`.

## Costs

- **$0 for the MVP**: local Whisper, ffmpeg, yt-dlp — no paid APIs.
- **24/7 watching** needs an always-on machine: an Oracle Cloud free-tier
  VM works, or a ~$5/month VPS (Hetzner / Contabo). A free-tier box that
  sleeps (e.g. Hoody) is *not* reliable for 24/7 watching.

## Project layout

```
src/
  moments.py         audio-energy peak detection (numpy, no APIs)
  captions.py        faster-whisper word timestamps -> ASS subtitles
  render.py          vertical reframe + burned captions (ffmpeg)
  pipeline.py        VOD + live orchestration (shared code path)
  cli.py             `clip` and `watch` commands
  sources/
    base.py          Source / LiveSource interfaces
    file_source.py   local file + VOD URL (yt-dlp)
    youtube_live.py  YouTube Live watcher (yt-dlp resolve + ffmpeg segments)
    twitch_live.py   STUB — plug in later, same interface
  uploaders/
    base.py          Uploader interface (TikTok/Shorts/Reels go here)
outbox/              finished clips (handoff point)
work/                intermediate files (wav, ASS, segments)
```

## Status / honest limits

- **Live path proven**: tested end-to-end on a real live YouTube stream
  (Kai Cenat, GTA 6) — 3 segments → 3 verified 30s vertical clips with
  real transcribed captions.
- **Uploaders are stubs**: auto-upload to TikTok / Shorts / Reels is not
  built — it needs your own accounts and OAuth logins. Until then clips
  land in `outbox/`, ready to post by hand.
- **Captions are one word at a time**, uppercase, bottom-center — readable
  but basic.
- **Reframing is a center crop** — side content can be cut off; there is
  no face tracking yet.
- **Live capture can lag on slow networks**: on a proxied/slow connection
  a 60s segment took ~2.5–4 min to capture, so clips lag the live moment
  by a few minutes. On a normal VPS this should not happen.
- **Twitch is a stub** by design (YouTube Live first).
- yt-dlp may warn about a missing JavaScript runtime — install node or
  deno for full format support.

## License

MIT — see [LICENSE](LICENSE).
