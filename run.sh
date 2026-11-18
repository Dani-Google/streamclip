#!/bin/bash
# StreamClip runner.
# Prefers a venv next to this script (./venv), then the whisper venv,
# then system python3. Install: python3 -m venv venv && venv/bin/pip install -r requirements.txt
# Usage: ./run.sh clip video.mp4
#        ./run.sh watch https://www.youtube.com/watch?v=XXXX
set -e
cd "$(dirname "$0")"
if [ -x "venv/bin/python" ]; then
  exec venv/bin/python -m src.cli "$@"
elif [ -x "$HOME/workspace/venvs/whisper/bin/python" ]; then
  exec "$HOME/workspace/venvs/whisper/bin/python" -m src.cli "$@"
else
  exec python3 -m src.cli "$@"
fi
