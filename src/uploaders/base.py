"""Uploaders — plug-in point for TikTok / YouTube Shorts / Instagram Reels.

NOT built yet on purpose: uploading needs the user's own accounts and
OAuth logins, which must be connected by him (never stored here).
Until then the pipeline's handoff point is the outbox/ folder: finished
clips land there, ready to post.

Each uploader implements upload(clip_path, title, description) and returns
the published URL.
"""

from abc import ABC, abstractmethod


class Uploader(ABC):
    name = "base"

    @abstractmethod
    def upload(self, clip_path, title, description=""):
        raise NotImplementedError


# Future plug-ins (one module each): uploaders/tiktok.py, youtube_shorts.py,
# instagram_reels.py — each wraps that platform's official upload API.
