"""Moment detection from audio energy.

No paid APIs: we extract the audio track, compute RMS energy in short
windows with numpy, smooth it, and pick the loudest peaks. Loud = reactions,
shouting, big plays — the parts worth clipping.
"""

import subprocess
import wave

import numpy as np

FFMPEG = "ffmpeg"


def extract_audio(video_path, wav_path, sample_rate=16000):
    """Extract mono 16kHz PCM wav from a video file."""
    cmd = [
        FFMPEG, "-y", "-v", "error",
        "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-f", "wav", str(wav_path),
    ]
    subprocess.run(cmd, check=True)
    return wav_path


def _read_wav(wav_path):
    with wave.open(str(wav_path), "rb") as w:
        n_frames = w.getnframes()
        rate = w.getframerate()
        raw = w.readframes(n_frames)
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return audio, rate


def _smooth(x, width):
    """Simple moving average (width in samples)."""
    if width <= 1:
        return x
    kernel = np.ones(width, dtype=np.float32) / width
    return np.convolve(x, kernel, mode="same")


def detect_moments(wav_path, clip_len=45, max_clips=3, lead=12.0,
                   window=0.5, min_energy_pct=70.0):
    """Find highlight moments in a wav file.

    Returns a list of dicts: {start, end, peak_time, score}.
    - window: seconds per energy measurement.
    - clip_len: seconds per clip. lead: seconds of context before the peak.
    - min_energy_pct: peaks must be above this percentile of the smoothed
      energy, so boring stretches never become clips.
    """
    audio, rate = _read_wav(wav_path)
    duration = len(audio) / rate
    if duration < 5:
        return []

    win = max(1, int(window * rate))
    n_win = len(audio) // win
    trimmed = audio[: n_win * win].reshape(n_win, win)
    rms = np.sqrt(np.mean(trimmed ** 2, axis=1) + 1e-12)

    # Smooth over ~3 seconds so a single clap doesn't win on its own.
    smooth_w = max(1, int(3.0 / window))
    energy = _smooth(rms, smooth_w)

    threshold = np.percentile(energy, min_energy_pct)
    # Candidate peaks: local maxima above threshold.
    candidates = []
    for i in range(1, len(energy) - 1):
        if energy[i] >= threshold and energy[i] >= energy[i - 1] and energy[i] >= energy[i + 1]:
            candidates.append((float(energy[i]), i * window))
    if not candidates:
        # Fallback: the single loudest window.
        i = int(np.argmax(energy))
        candidates = [(float(energy[i]), i * window)]

    # Loudest first, keep clips at least clip_len apart.
    candidates.sort(key=lambda c: -c[0])
    chosen = []
    for score, peak_time in candidates:
        if all(abs(peak_time - c["peak_time"]) >= clip_len for c in chosen):
            start = peak_time - lead
            start = max(0.0, min(start, max(0.0, duration - clip_len)))
            chosen.append({
                "start": round(start, 2),
                "end": round(min(start + clip_len, duration), 2),
                "peak_time": round(peak_time, 2),
                "score": round(score, 4),
            })
        if len(chosen) >= max_clips:
            break

    chosen.sort(key=lambda c: c["start"])
    return chosen


def probe_duration(video_path):
    """Video duration in seconds (ffprobe)."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0", str(video_path),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(out.stdout.strip())
