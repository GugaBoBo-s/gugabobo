#!/usr/bin/env bash
set -euo pipefail

ROOT="${GUGABOBO_ROOT:-/opt/gugabobo}"
REPO_DIR="$ROOT/repo"
DATA_DIR="$ROOT/data"
RUN_USER="${GUGABOBO_RUN_USER:-${SUDO_USER:-ubuntu}}"
REPO_URL="${GUGABOBO_REPO_URL:-git@github.com:GugaBoBo-s/gugabobo.git}"
HTTPS_REPO_URL="${GUGABOBO_HTTPS_REPO_URL:-https://github.com/GugaBoBo-s/gugabobo.git}"
RUNNER_IMAGE="${GUGABOBO_RUNNER_IMAGE:-gugabobo-runner:local}"
CREDENTIAL_HELPER="$REPO_DIR/deploy/git-credential-gugabobo"

configure_repo_auth() {
  if [ ! -f "$CREDENTIAL_HELPER" ] || [ ! -f "$REPO_DIR/.env" ]; then
    return
  fi
  if ! grep -Eq '^GUGABOBO_GITHUB_TOKEN=.+$' "$REPO_DIR/.env"; then
    return
  fi
  chown "$RUN_USER":"$RUN_USER" "$CREDENTIAL_HELPER"
  chmod 700 "$CREDENTIAL_HELPER"
  sudo -u "$RUN_USER" git -C "$REPO_DIR" config --local credential.helper "$CREDENTIAL_HELPER"
  sudo -u "$RUN_USER" git -C "$REPO_DIR" remote set-url origin "$HTTPS_REPO_URL"
}

echo "[gugabobo] root=$ROOT user=$RUN_USER"

apt-get update -y
apt-get install -y python3-venv python3-pip git curl docker.io
systemctl enable --now docker
usermod -aG docker "$RUN_USER"

mkdir -p "$REPO_DIR" "$DATA_DIR/logs" "$DATA_DIR/sandbox" "$DATA_DIR/claude-home"
chown -R "$RUN_USER":"$RUN_USER" "$ROOT"

if [ -d "$REPO_DIR/.git" ]; then
  configure_repo_auth
  sudo -u "$RUN_USER" git -C "$REPO_DIR" pull --ff-only
else
  sudo -u "$RUN_USER" git clone "$REPO_URL" "$REPO_DIR"
fi

if [ ! -d "$REPO_DIR/.venv" ]; then
  sudo -u "$RUN_USER" python3 -m venv "$REPO_DIR/.venv"
fi
sudo -u "$RUN_USER" "$REPO_DIR/.venv/bin/python" -m pip install --upgrade pip
sudo -u "$RUN_USER" "$REPO_DIR/.venv/bin/python" -m pip install -e "$REPO_DIR[dev]"

if [ ! -f "$REPO_DIR/.env" ]; then
  cp "$REPO_DIR/deploy/gugabobo.env.example" "$REPO_DIR/.env"
  chown "$RUN_USER":"$RUN_USER" "$REPO_DIR/.env"
fi
chmod 600 "$REPO_DIR/.env"
configure_repo_auth

docker build -f "$REPO_DIR/deploy/Dockerfile.runner" -t "$RUNNER_IMAGE" "$REPO_DIR"

sudo -u "$RUN_USER" "$REPO_DIR/.venv/bin/python" -m ruff check "$REPO_DIR"
sudo -u "$RUN_USER" "$REPO_DIR/.venv/bin/python" -m pytest -q "$REPO_DIR"

cp "$REPO_DIR/deploy/gugabobo-api.service" /etc/systemd/system/gugabobo-api.service
cp "$REPO_DIR/deploy/gugabobo-telegram.service" /etc/systemd/system/gugabobo-telegram.service
systemctl daemon-reload
systemctl enable gugabobo-api.service

echo "[gugabobo] setup complete"
echo "Edit $REPO_DIR/.env, authenticate the runner, then restart gugabobo-api."
