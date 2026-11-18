# StreamClip on Oracle Cloud free tier

Run the StreamClip web app (paste a YouTube link → vertical captioned
Shorts) on a **free** Oracle Cloud VM, so it has a public link anyone can
open. No money is spent anywhere in this setup.

## What the free tier gives

- **Ampere A1 (ARM) — Always Free:** up to **4 OCPU + 24 GB RAM** total
  across your A1 instances. One instance with 4 OCPU / 24 GB is plenty
  for StreamClip (Whisper runs on CPU; one job at a time by design).
- **Boot volume:** 200 GB Always Free total — the default 50 GB is more
  than enough (app + model ≈ 2 GB, clips are small).
- **Outbound data:** 10 TB/month free. Inbound is free.
- The VM never sleeps, unlike free boxes that pause — that is the point:
  it can watch a live stream 24/7.

## 1. Create the instance (Oracle Cloud console)

1. Sign up / sign in at https://cloud.oracle.com (a card is asked for
   verification only; the Always Free tier itself costs $0).
2. **Compute → Instances → Create instance.**
3. **Image:** Ubuntu **22.04** (Canonical Ubuntu 22.04 aarch64).
4. **Shape:** `VM.Standard.A1.Flex` — set **4 OCPU, 24 GB memory**.
   (If the region says "out of capacity", try again later or try another
   home region — A1 capacity in popular regions often needs a few retries.
   That is normal; keep the shape, do not pay for a bigger one.)
5. **Networking:** keep the default VCN. After creation, open port 5000:
   **Networking → Virtual Cloud Networks → your VCN → Security List →
   Add Ingress Rule:** Source `0.0.0.0/0`, IP Protocol TCP, Destination
   Port Range `5000`. (Without this the page will not load, even though
   the app is running.)
6. **SSH key:** add your public key (or let Oracle generate a pair and
   download the private key — keep it safe).
7. Create. Note the instance's **public IP**.

## 2. Run the setup script

SSH in as `ubuntu` and run:

```bash
git clone https://github.com/Dani-Google/streamclip.git
cd streamclip
bash deploy/oracle-setup.sh
```

The script is idempotent (safe to re-run). It installs Python 3.12,
ffmpeg, fonts, the repo, the pipeline venv (faster-whisper + yt-dlp),
downloads the Whisper `small` model (~464 MB, once), the Flask venv,
and installs + starts a systemd service on port 5000. Takes roughly
10–20 minutes on first run (mostly the model download).

## 3. Verify

- Open **`http://<your-public-IP>:5000`** in a browser — the StreamClip
  form should load.
- Paste a short public YouTube video URL, pick **Recorded video / VOD**,
  2 clips × 30s, and confirm clips render with captions.
- On the VM: `sudo systemctl status streamclip-web` and
  `sudo journalctl -u streamclip-web -f` for logs.

## 4. Update later

```bash
cd ~/streamclip && git pull && sudo systemctl restart streamclip-web
```

## Honest limits

- **Live capture lag:** on this VM the 60s live segment took 2–4 min to
  capture (slow/proxied connection). On a proper VPS it should be much
  closer to real time — but **verify with a real live stream** before
  promising anyone real-time clips.
- **Free-tier capacity:** A1 instances in popular regions often show
  "out of capacity" — retry later or try another region. Never pay to
  work around it; the free shape is enough.
- **One job at a time** by design (CPU Whisper is the bottleneck);
  extra jobs queue.
- **No auto-upload yet** — clips land in the job's outbox; download and
  post them by hand. Uploaders need your own TikTok/Shorts/Reels logins.
- **Music-only videos transcribe 0 words** (Whisper's VAD drops sung
  audio) — speech videos caption properly.
- **No HTTPS yet** — the link is plain `http://IP:5000`. Fine for testing
  and sharing with clients; add a domain + reverse proxy (Caddy/Nginx)
  later if you want `https://`.
- Port 5000 must stay open in the OCI security list; the script cannot
  do that part for you.
