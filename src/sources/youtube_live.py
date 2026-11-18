"""YouTube Live watcher — the LIVE source for this MVP.

How it works:
1. yt-dlp resolves the live stream to a direct HLS URL (no login needed
   for public streams) and tells us whether the video is actually live.
2. ffmpeg reads that URL and writes the stream to disk in fixed-length
   segments (default 60s) as it airs.
3. Each completed segment is handed to the pipeline (same moment detection
   -> clip -> captions -> render as VODs), so clips can go out while the
   stream is still live.

No paid APIs, no account needed for public streams.
"""

import json
import shutil
import subprocess
import time
from pathlib import Path

from .base import LiveSource

# yt-dlp from PATH when available, else the common per-user install.
YTDLP = shutil.which("yt-dlp") or str(Path.home() / ".local/bin/yt-dlp")


def _segment_cmd(inputs, pattern, segment_seconds):
    """ffmpeg segment command for one combined input or [video, audio]."""
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for src in inputs:
        cmd += ["-i", str(src)]
    if len(inputs) == 2:
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += [
        "-c", "copy",
        "-f", "segment", "-segment_time", str(segment_seconds),
        "-segment_format", "matroska",
        "-reset_timestamps", "1",
        pattern,
    ]
    return cmd


class YouTubeLiveWatcher(LiveSource):
    def __init__(self, url):
        self.url = url

    # -- discovery -----------------------------------------------------
    def info(self):
        """yt-dlp metadata: is_live, title, channel. Raises on failure."""
        cmd = [YTDLP, "-J", "--no-playlist", self.url]
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(out.stdout)
        return {
            "is_live": bool(data.get("is_live")),
            "title": data.get("title"),
            "channel": data.get("channel") or data.get("uploader"),
            "id": data.get("id"),
        }

    def resolve_stream_url(self):
        """Direct stream URL(s) for ffmpeg.

        Prefers ONE combined (video+audio) URL — the format live streams
        serve over HLS. Falls back to separate video+audio URLs (DASH),
        which watch() feeds to ffmpeg as two inputs.
        Returns a str (combined) or a [video_url, audio_url] list.
        """
        combined = [
            YTDLP, "-g", "--no-playlist", "-f",
            "b[height<=720]", self.url,
        ]
        out = subprocess.run(combined, capture_output=True, text=True)
        urls = [u.strip() for u in out.stdout.splitlines() if u.strip()]
        if out.returncode == 0 and len(urls) == 1:
            return urls[0]
        separate = [
            YTDLP, "-g", "--no-playlist", "-f",
            "bv*[height<=720]+ba/b[height<=720]", self.url,
        ]
        out = subprocess.run(separate, capture_output=True, text=True,
                             check=True)
        urls = [u.strip() for u in out.stdout.splitlines() if u.strip()]
        if not urls:
            raise RuntimeError(f"yt-dlp could not resolve a stream URL for {self.url}")
        return urls[0] if len(urls) == 1 else urls

    # -- capture -------------------------------------------------------
    def watch(self, workdir, segment_seconds=60, max_segments=None,
              on_segment=None, source=None):
        """Capture the stream into segments, calling on_segment per segment.

        source: override the input for ffmpeg. Default = resolved live URL.
        Pass a local file path to simulate a live stream from a recording
        (used for testing the watch loop without a live stream on air).
        """
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        if source is None:
            source = self.resolve_stream_url()
        # source is either one combined URL (str) or [video_url, audio_url].

        pattern = str(workdir / "seg_%03d.mkv")
        inputs = source if isinstance(source, list) else [source]
        cmd = _segment_cmd(inputs, pattern, segment_seconds)
        proc = subprocess.Popen(cmd)
        seen = set()
        done = 0
        try:
            while True:
                if proc.poll() is not None:
                    # Stream ended (VOD / simulated file): flush leftovers.
                    done = self._flush(workdir, seen, on_segment,
                                       done, max_segments)
                    break
                time.sleep(2)
                done = self._collect(workdir, seen, on_segment, done,
                                     max_segments)
                if max_segments is not None and done >= max_segments:
                    break
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
            # Pick up any segment finished while we were stopping,
            # still within the max_segments budget.
            self._flush(workdir, seen, on_segment, done, max_segments)
        return done

    def _collect(self, workdir, seen, on_segment, done, max_segments):
        files = sorted(Path(workdir).glob("seg_*.mkv"))
        # The newest file is still being written — only hand over older ones.
        for f in files[:-1]:
            if f.name in seen:
                continue
            if time.time() - f.stat().st_mtime < 2:
                continue
            seen.add(f.name)
            if on_segment:
                on_segment(f)
            done += 1
            if max_segments is not None and done >= max_segments:
                break
        return done

    def _flush(self, workdir, seen, on_segment, done, max_segments):
        for f in sorted(Path(workdir).glob("seg_*.mkv")):
            if max_segments is not None and done >= max_segments:
                break
            if f.name not in seen and f.stat().st_size > 0:
                seen.add(f.name)
                if on_segment:
                    on_segment(f)
                done += 1
        return done
