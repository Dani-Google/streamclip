"""Uploaders package — outbox/ is the handoff point until auth is wired up."""

from .base import Uploader

__all__ = ["Uploader"]
