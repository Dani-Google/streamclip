"""Twitch live source — STUB, not built yet.

Kept as a separate module on purpose: when Twitch support is added it
plugs into the same LiveSource interface (watch() yielding segment files)
and the pipeline does not change. Twitch needs either:
- streamlink (pip) to resolve the stream URL, or
- the Twitch API (client ID + OAuth) for EventSub/chat-spike detection.
"""

from .base import LiveSource


class TwitchLiveWatcher(LiveSource):
    def __init__(self, channel):
        self.channel = channel

    def watch(self, workdir, segment_seconds=60, max_segments=None,
              on_segment=None):
        raise NotImplementedError(
            "Twitch live source is not built yet — YouTube Live is the "
            "live source for this MVP. See src/sources/youtube_live.py "
            "for the interface to implement."
        )
