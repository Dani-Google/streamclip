#!/usr/bin/env bash
# StreamClip — Oracle Cloud free-tier setup (Ampere A1 ARM, Ubuntu 22.04).
#
# What it does, on a FRESH VM, as the `ubuntu` user (sudo required):
#   1. Installs system deps: Python 3.12 (deadsnakes PPA — the app is
#      tested on 3.12), ffmpeg, git, curl, Noto Sans fonts (captions).
#   2. Clones the public StreamClip repo to ~/streamclip (or pulls latest
#      if it is already there).
#   3. Creates the pipeline venv (faster-whisper + numpy) and installs
#      yt-dlp into it, symlinked to /usr/local/bin so the pipeline finds it.
#   4. Downloads the faster-whisper `small` model (~464 MB) to
#      ~/models/whisper-small.
#   5. Creates the web venv (Flask 3.1.3, the tested version).
#   6. Installs + starts a systemd service (streamclip-web) on port 5000.
#   7. Opens port 5000 in ufw IF ufw is active (the OCI security list
#      still needs a manual ingress rule — see deploy/README.md).
#
# Idempotent: safe to re-run — every step skips work that is already done.
# No credentials, keys, or personal data in this file. No money is spent:
# everything here is free-tier / open source.
#
# Usage:  bash deploy/oracle-setup.sh
#   (run it from anywhere; it finds the repo itself. Do NOT run as root —
#    run as the `ubuntu` user, which has passwordless sudo on Oracle images.)

set -euo pipefail

REPO="https://github.com/Dani-Google/streamclip.git"
APP_DIR="$HOME/streamclip"
MODEL_DIR="$HOME/models/whisper-small"
MODEL_REPO="Systran/faster-whisper-small"
SERVICE="streamclip-web.service"

if [ "$(id -u)" -eq 0 ]; then
  echo "ERROR: run this as the ubuntu user (with sudo), not as root." >&2
  exit 1
fi

APP_USER="$(id -un)"
echo "== StreamClip setup — user $APP_USER, app dir $APP_DIR =="

# --- 1. System packages -------------------------------------------------
echo "== [1/7] system packages (python3.12, ffmpeg, git, fonts) =="
sudo apt-get update -qq
sudo apt-get install -y -qq software-properties-common curl git ffmpeg \
  fonts-noto-core fonts-dejavu-core

if ! command -v python3.12 >/dev/null 2>&1; then
  echo "Adding deadsnakes PPA for Python 3.12 (app is tested on 3.12)..."
  sudo add-apt-repository -y ppa:deadsnakes/ppa >/dev/null
  sudo apt-get update -qq
fi
sudo apt-get install -y -qq python3.12 python3.12-venv

# --- 2. Repo ------------------------------------------------------------
echo "== [2/7] StreamClip repo -> $APP_DIR =="
if [ -d "$APP_DIR/.git" ]; then
  echo "Repo already present — pulling latest..."
  git -C "$APP_DIR" pull --ff-only || echo "NOTE: pull failed, keeping local copy."
else
  git clone --depth 1 "$REPO" "$APP_DIR"
fi
cd "$APP_DIR"

# Guard: the web app must be in the repo (it is pushed to GitHub separately
# from the CLI). Fail clearly here instead of later in systemd.
if [ ! -f "$APP_DIR/web/app.py" ]; then
  echo "ERROR: web/app.py not found in the cloned repo." >&2
  echo "The web app (web/) has not been pushed to GitHub yet — push web/" >&2
  echo "and deploy/ to the repo first, then re-run this script." >&2
  exit 1
fi

# --- 3. Pipeline venv (faster-whisper + numpy + yt-dlp) -----------------
echo "== [3/7] pipeline venv (faster-whisper, numpy, yt-dlp) =="
if [ ! -x "$APP_DIR/venv/bin/python" ]; then
  python3.12 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
"$APP_DIR/venv/bin/pip" install -q yt-dlp
# Make yt-dlp findable on PATH for the pipeline (it also checks ~/.local/bin).
sudo ln -sf "$APP_DIR/venv/bin/yt-dlp" /usr/local/bin/yt-dlp
echo "yt-dlp: $(/usr/local/bin/yt-dlp --version)"

# --- 4. Whisper model ----------------------------------------------------
echo "== [4/7] faster-whisper small model -> $MODEL_DIR =="
if [ ! -f "$MODEL_DIR/model.bin" ]; then
  echo "Downloading model (~464 MB, one time)..."
  "$APP_DIR/venv/bin/pip" install -q huggingface_hub
  "$APP_DIR/venv/bin/python" - "$MODEL_REPO" "$MODEL_DIR" <<'EOF'
import sys
from huggingface_hub import snapshot_download
snapshot_download(repo_id=sys.argv[1], local_dir=sys.argv[2])
print("model downloaded")
EOF
fi
test -f "$MODEL_DIR/model.bin" || { echo "ERROR: model.bin missing after download." >&2; exit 1; }
echo "Model OK: $(du -sh "$MODEL_DIR" | cut -f1) in $MODEL_DIR"

# --- 5. Web venv (Flask) -------------------------------------------------
echo "== [5/7] web venv (Flask 3.1.3) =="
if [ ! -x "$APP_DIR/web/venv/bin/python" ]; then
  python3.12 -m venv "$APP_DIR/web/venv"
fi
"$APP_DIR/web/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/web/venv/bin/pip" install -q "flask==3.1.3"

# --- 6. systemd service ---------------------------------------------------
echo "== [6/7] systemd service $SERVICE =="
sudo tee "/etc/systemd/system/$SERVICE" >/dev/null <<EOF
[Unit]
Description=StreamClip web — paste a YouTube link, get Shorts
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR/web
Environment=STREAMCLIP_WHISPER_MODEL=$MODEL_DIR
Environment=STREAMCLIP_FONTS_DIR=/usr/share/fonts/truetype/noto
Environment=PATH=$APP_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$APP_DIR/web/venv/bin/python app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE" >/dev/null
sudo systemctl restart "$SERVICE"
sleep 3
sudo systemctl --no-pager status "$SERVICE" | head -12 || true

# --- 7. Firewall (ufw only if active) + verify ---------------------------
echo "== [7/7] firewall + verify =="
if sudo ufw status 2>/dev/null | grep -q "Status: active"; then
  sudo ufw allow 5000/tcp >/dev/null
  echo "ufw: port 5000 allowed."
else
  echo "ufw not active — skipping (OCI security list is the gate)."
fi

if curl -fsS --max-time 10 http://127.0.0.1:5000/ -o /dev/null; then
  echo "Web app responding on http://127.0.0.1:5000/"
else
  echo "WARNING: app did not answer on port 5000 yet — check logs:" >&2
  echo "  sudo journalctl -u $SERVICE -n 50" >&2
fi

PUBLIC_IP="$(curl -fsS --max-time 5 http://169.254.169.254/opc/v1/instance/ \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["canonicalVnics"][0].get("publicIp") or "")' 2>/dev/null || true)"
if [ -z "$PUBLIC_IP" ]; then
  PUBLIC_IP="$(curl -fsS --max-time 5 https://ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
fi

echo
echo "================ DONE ================"
echo "StreamClip web should be live at:  http://$PUBLIC_IP:5000"
echo
echo "If the page does not load from your browser, open port 5000 in the"
echo "OCI console: Networking -> your VCN -> Security List -> Add Ingress"
echo "Rule: Source 0.0.0.0/0, TCP, destination port 5000."
echo
echo "Useful commands:"
echo "  status:  sudo systemctl status $SERVICE"
echo "  logs:    sudo journalctl -u $SERVICE -f"
echo "  restart: sudo systemctl restart $SERVICE"
echo "  update:  cd $APP_DIR && git pull && sudo systemctl restart $SERVICE"
echo "======================================"
