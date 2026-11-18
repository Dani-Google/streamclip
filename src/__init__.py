"""LiveClip MVP — turn a stream/VOD into vertical captioned clips.

Pipeline: source -> moments (audio energy) -> clip -> captions (Whisper) -> render (1080x1920 MP4) -> outbox/
Uploaders (TikTok / Shorts / Reels) are separate plug-in modules; the outbox
folder is the handoff point until their auth is wired up.
"""

__version__ = "0.1.0"
