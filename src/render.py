"""Render one vertical clip: center-crop to 9:16, scale to 1080x1920,
burn in the ASS captions, keep the original audio.
"""

import os
import subprocess

FFMPEG = "ffmpeg"
FONTS_DIR = os.environ.get("STREAMCLIP_FONTS_DIR",
                           "/usr/share/fonts/truetype/noto")


def render_clip(src, start, duration, ass_path, out_path):
    """Cut [start, start+duration) from src and render a vertical MP4."""
    vf = (
        "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,"
        "scale=1080:1920:flags=lanczos,"
        "fps=30,"
        f"subtitles={ass_path}:fontsdir={FONTS_DIR}"
    )
    cmd = [
        FFMPEG, "-y", "-v", "error",
        "-ss", str(start), "-i", str(src),
        "-t", str(duration),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_path
