"""Source interface.

A source produces video for the pipeline. Two flavours:
- VOD/file sources: one whole video file (FileSource / VodSource).
- Live sources: a stream of segment files as they air (YouTubeLiveWatcher).
  The pipeline consumes segments with the same moment -> clip -> captions
  functions, so live and VOD share all the clipping logic.
"""

from abc import ABC, abstractmethod


class Source(ABC):
    @abstractmethod
    def prepare(self, workdir):
        """Return a local video file path (VOD/file sources)."""
        raise NotImplementedError


class LiveSource(ABC):
    @abstractmethod
    def watch(self, workdir, segment_seconds=60, max_segments=None,
              on_segment=None):
        """Capture the live stream in segments.

        Calls on_segment(segment_path) for each completed segment file,
        in air order. Blocks until the stream ends, max_segments is
        reached, or the caller stops it.
        """
        raise NotImplementedError
