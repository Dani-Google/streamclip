"""Sources: local files and VOD URLs (YouTube / Twitch VODs via yt-dlp)."""

import shutil
import subprocess
from pathlib import Path

from .base import Source

# yt-dlp from PATH when available, else the common per-user install.
YTDLP = shutil.which("yt-dlp") or str(Path.home() / ".local/bin/yt-dlp")


class FileSource(Source):
    """A video file already on disk."""

    def __init__(self, path):
        self.path = Path(path)

    def prepare(self, workdir):
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        return self.path


class VodSource(Source):
    """A VOD URL (YouTube video, Twitch VOD...). Downloads it with yt-dlp."""

    def __init__(self, url):
        self.url = url

    def prepare(self, workdir):
        out = Path(workdir) / "vod.%(ext)s"
        cmd = [
            YTDLP, "-f",
            "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/b[height<=720]",
            "--no-playlist", "-o", str(out), self.url,
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        files = sorted(Path(workdir).glob("vod.*"))
        if not files:
            raise RuntimeError(f"yt-dlp produced no file for {self.url}")
        return files[0]


def resolve_source(input_arg):
    """File path -> FileSource, anything else -> VodSource (URL)."""
    p = Path(input_arg)
    if p.exists():
        return FileSource(p)
    return VodSource(input_arg)
