"""Pipeline: source -> moments -> clip -> captions -> render -> outbox/.

One code path serves both VODs (whole file) and live segments (60s chunks
from the YouTube Live watcher): process_video() does the whole job for any
input video file. Live mode just calls it once per segment.
"""

from pathlib import Path
import subprocess

from . import captions, moments, render
from .sources import YouTubeLiveWatcher, resolve_source


def process_video(video_path, outbox, workdir, tag,
                  clip_len=45, max_clips=3, min_energy_pct=70.0):
    """Cut the best moments out of one video file into vertical clips.

    Returns a list of output clip paths.
    """
    video_path = Path(video_path)
    outbox = Path(outbox)
    workdir = Path(workdir)
    outbox.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)

    duration = moments.probe_duration(video_path)
    wav = workdir / f"{tag}.wav"
    moments.extract_audio(video_path, wav)
    found = moments.detect_moments(
        wav, clip_len=min(clip_len, duration),
        max_clips=max_clips, min_energy_pct=min_energy_pct,
    )
    if not found:
        print(f"[{tag}] no moments above threshold — no clips.")
        return []

    print(f"[{tag}] {duration:.0f}s video -> {len(found)} moment(s): "
          + ", ".join(f"{m['start']:.0f}s (peak {m['peak_time']:.0f}s)"
                      for m in found))

    # Transcribe all clips first (one model load), then render.
    jobs = []
    for i, m in enumerate(found, 1):
        clip_wav = workdir / f"{tag}_clip{i}.wav"
        # Reuse the full wav via ffmpeg trim (fast: audio only).
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-ss", str(m["start"]), "-i", str(wav),
            "-t", str(round(m["end"] - m["start"], 2)),
            "-f", "wav", str(clip_wav),
        ], check=True)
        jobs.append((i, m, clip_wav))

    words_by_clip = {}
    for i, m, clip_wav in jobs:
        words = captions.transcribe_words(clip_wav)
        words_by_clip[i] = words
        print(f"[{tag}] clip {i}: {len(words)} words transcribed")

    outputs = []
    for i, m, clip_wav in jobs:
        words = words_by_clip[i]
        ass = workdir / f"{tag}_clip{i}.ass"
        captions.words_to_ass(words, ass)
        out = outbox / f"{tag}_clip{i}.mp4"
        render.render_clip(video_path, m["start"],
                           round(m["end"] - m["start"], 2), ass, out)
        outputs.append(out)
        print(f"[{tag}] clip {i} -> {out} "
              f"({m['start']:.0f}s–{m['end']:.0f}s, peak {m['peak_time']:.0f}s)")
    return outputs


def run_vod(input_arg, outbox, workdir, clip_len=45, max_clips=3):
    """Full VOD/file run: resolve the input, clip it, render to outbox/."""
    src = resolve_source(input_arg)
    video = src.prepare(workdir)
    return process_video(video, outbox, workdir, tag="vod",
                         clip_len=clip_len, max_clips=max_clips)


def run_live(url, outbox, workdir, segment_seconds=60, max_segments=None,
             clip_len=30, simulate_from=None):
    """Watch a YouTube Live stream and clip each segment as it airs.

    simulate_from: local file path — segment that file as if it were live
    (tests the watch loop without a stream on air).
    """
    watcher = YouTubeLiveWatcher(url)
    if simulate_from is None:
        meta = watcher.info()
        print(f"Live check: {meta['title']} ({meta['channel']}) "
              f"is_live={meta['is_live']}")
        if not meta["is_live"]:
            print("WARNING: that video is not live right now — "
                  "capture will end when the VOD URL runs out.")
    else:
        print(f"SIMULATED live: segmenting {simulate_from}")

    seg_work = Path(workdir) / "live_segments"
    counter = {"n": 0}

    def on_segment(seg_path):
        counter["n"] += 1
        tag = f"live{counter['n']:03d}"
        seg_dir = Path(workdir) / tag
        seg_dir.mkdir(parents=True, exist_ok=True)
        try:
            outs = process_video(
                seg_path, outbox, seg_dir, tag=tag,
                clip_len=clip_len, max_clips=1, min_energy_pct=60.0,
            )
            if not outs:
                print(f"[{tag}] segment had no loud moment — skipped.")
        except Exception as exc:  # one bad segment must not kill the watch
            print(f"[{tag}] segment failed ({exc}) — continuing.")

    watcher.watch(seg_work, segment_seconds=segment_seconds,
                  max_segments=max_segments, on_segment=on_segment,
                  source=simulate_from)
    print(f"Live run done: {counter['n']} segment(s) processed.")
