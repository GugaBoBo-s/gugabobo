#!/usr/bin/env bash
# gugabobo server setup (Ubuntu 24.04). Idempotent: safe to re-run.
# Usage: sudo bash deploy/setup.sh
set -euo pipefail

ROOT=/opt/gugabobo
REPO_DIR="$ROOT/repo"
DATA_DIR="$ROOT/data"
RUN_USER="${SUDO_USER:-ubuntu}"
REPO_URL="https://github.com/GugaBoBo-s/gugabobo.git"

echo "[gugabobo] target root: $ROOT (run user: $RUN_USER)"

# 1. System packages
apt-get update -y
apt-get install -y python3-venv python3-pip git curl

# 2. Directory layout, owned by the run user
mkdir -p "$REPO_DIR" "$DATA_DIR/logs" "$DATA_DIR/sandbox"
chown -R "$RUN_USER":"$RUN_USER" "$ROOT"

# 3. Clone or update the repository (as the run user)
if [ -d "$REPO_DIR/.git" ]; then
  echo "[gugabobo] updating existing clone"
  sudo -u "$RUN_USER" git -C "$REPO_DIR" pull --ff-only
else
  echo "[gugabobo] cloning repository"
  sudo -u "$RUN_USER" git clone "$REPO_URL" "$REPO_DIR"
fi

# 4. Python virtual environment and dependencies (dev extras: ruff+pytest
#    are needed because self-improvement runs checks inside the sandbox)
if [ ! -d "$REPO_DIR/.venv" ]; then
  sudo -u "$RUN_USER" python3 -m venv "$REPO_DIR/.venv"
fi
sudo -u "$RUN_USER" "$REPO_DIR/.venv/bin/python" -m pip install --upgrade pip
sudo -u "$RUN_USER" "$REPO_DIR/.venv/bin/python" -m pip install -e "$REPO_DIR[dev]"

# 5. Environment file (never overwrite an existing one)
if [ ! -f "$REPO_DIR/.env" ]; then
  cp "$REPO_DIR/deploy/gugabobo.env.example" "$REPO_DIR/.env"
  chown "$RUN_USER":"$RUN_USER" "$REPO_DIR/.env"
  echo "[gugabobo] created .env from template — edit it and set secrets"
fi
chmod 600 "$REPO_DIR/.env"

# 6. systemd service
cp "$REPO_DIR/deploy/gugabobo-api.service" /etc/systemd/system/gugabobo-api.service
systemctl daemon-reload
systemctl enable gugabobo-api.service

echo "[gugabobo] setup done."
echo "  1. Edit $REPO_DIR/.env (admin token, GuGabobo GitHub token, LLM key)."
echo "  2. Install + authenticate Claude Code for user $RUN_USER (see DEPLOY.md)."
echo "  3. Start:  sudo systemctl restart gugabobo-api"
echo "  4. Tunnel: ssh -L 8765:127.0.0.1:8765 $RUN_USER@<server-ip>"
