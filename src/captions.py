"""Word-level captions with faster-whisper (local, CPU, no API).

Transcribes one clip's audio and writes an ASS subtitle file: one event per
word, so the burned-in caption follows the speech word by word.
"""

import os
import wave

import numpy as np


def _default_model_path():
    """Local model if present, else "small" (faster-whisper downloads it
    from Hugging Face on first use). Override with STREAMCLIP_WHISPER_MODEL."""
    local = os.path.expanduser("~/workspace/models/whisper-small")
    if os.path.isdir(local):
        return local
    return "small"


MODEL_PATH = os.environ.get("STREAMCLIP_WHISPER_MODEL", _default_model_path())


def _fmt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _clean(text):
    return text.replace("{", "").replace("}", "").replace("\n", " ").strip()


def _load_audio_array(audio_path, sample_rate=16000):
    """Decode a wav to a float32 numpy array at 16kHz.

    faster-whisper's built-in decode (PyAV) is version-sensitive, so we
    decode here instead and pass the raw array to transcribe().
    """
    with wave.open(str(audio_path), "rb") as w:
        rate = w.getframerate()
        channels = w.getnchannels()
        raw = w.readframes(w.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != sample_rate:
        # Simple resample via ffmpeg would be needed; our clips are
        # extracted at 16kHz already, so this is just a guard.
        raise ValueError(f"expected {sample_rate}Hz audio, got {rate}Hz")
    return audio


def transcribe_words(audio_path, model_path=MODEL_PATH, language=None):
    """Return a list of {word, start, end} for one audio file.

    The model is loaded fresh per call; the caller should transcribe all
    clips in one process run and let the model go out of scope afterwards
    (keeps peak RAM low on small machines).
    """
    from faster_whisper import WhisperModel

    audio = _load_audio_array(audio_path)
    model = WhisperModel(model_path, device="cpu",
                         compute_type="int8", cpu_threads=2)
    segments, _info = model.transcribe(
        audio, language=language, word_timestamps=True,
        vad_filter=True,
    )
    words = []
    for seg in segments:
        for w in (seg.words or []):
            text = _clean(w.word)
            if text:
                words.append({"word": text.upper(), "start": round(w.start, 2),
                              "end": round(w.end, 2)})
    del model
    return words


def words_to_ass(words, ass_path):
    """Write word-level captions to an ASS file (1080x1920 canvas)."""
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,80,80,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for i, w in enumerate(words):
        start = _fmt_time(w["start"])
        # Hold the word until the next one starts (max +0.4s).
        if i + 1 < len(words):
            end = min(words[i + 1]["start"], w["end"] + 0.4)
        else:
            end = w["end"] + 0.4
        end = max(end, w["start"] + 0.08)
        lines.append(
            f"Dialogue: 0,{start},{_fmt_time(end)},Default,,0,0,0,,{w['word']}\n"
        )
    with open(ass_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return ass_path
