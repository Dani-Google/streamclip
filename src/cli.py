"""LiveClip MVP — command line.

Run from ~/workspace/liveclip-mvp with the whisper venv python:

  # Clip a local file or a VOD URL into vertical captioned clips:
  python -m src.cli clip work/test-video.mp4 --max-clips 3 --clip-len 45
  python -m src.cli clip https://www.youtube.com/watch?v=XXXX

  # Watch a YouTube Live stream and clip segments as they air:
  python -m src.cli watch https://www.youtube.com/watch?v=XXXX --max-segments 4

  # Test the live watch loop without a stream on air:
  python -m src.cli watch --simulate work/test-video.mp4 --max-segments 3

Clips land in outbox/. No upload auth yet — outbox/ is the handoff point.
"""

import argparse
from pathlib import Path

from .pipeline import run_live, run_vod

HERE = Path(__file__).resolve().parent.parent
OUTBOX = HERE / "outbox"
WORK = HERE / "work"


def main():
    parser = argparse.ArgumentParser(description="LiveClip MVP")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_clip = sub.add_parser("clip", help="clip a file or VOD URL")
    p_clip.add_argument("input", help="local video file or video URL")
    p_clip.add_argument("--max-clips", type=int, default=3)
    p_clip.add_argument("--clip-len", type=int, default=45)
    p_clip.add_argument("--outbox", default=str(OUTBOX))
    p_clip.add_argument("--work", default=str(WORK))

    p_watch = sub.add_parser("watch", help="watch a YouTube Live stream")
    p_watch.add_argument("url", nargs="?", default="",
                         help="YouTube live video URL")
    p_watch.add_argument("--segment", type=int, default=60,
                         help="segment length in seconds")
    p_watch.add_argument("--max-segments", type=int, default=None)
    p_watch.add_argument("--clip-len", type=int, default=30)
    p_watch.add_argument("--simulate", default=None,
                         help="local file to segment as if live (test mode)")
    p_watch.add_argument("--outbox", default=str(OUTBOX))
    p_watch.add_argument("--work", default=str(WORK))

    args = parser.parse_args()

    if args.cmd == "clip":
        outs = run_vod(args.input, args.outbox, args.work,
                       clip_len=args.clip_len, max_clips=args.max_clips)
        print(f"\nDone: {len(outs)} clip(s) in {args.outbox}")
        for o in outs:
            print(f"  {o}")
    elif args.cmd == "watch":
        if not args.url and not args.simulate:
            parser.error("watch needs a live URL or --simulate <file>")
        run_live(args.url or "https://www.youtube.com/watch?v=SIMULATED",
                 args.outbox, args.work,
                 segment_seconds=args.segment,
                 max_segments=args.max_segments,
                 clip_len=args.clip_len,
                 simulate_from=args.simulate)


if __name__ == "__main__":
    main()
