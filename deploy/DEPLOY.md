# gugabobo server deployment

Target platform: Ubuntu 24.04 with the API bound to localhost. The repository is
private, so the server must have its own GitHub deploy key before cloning.

## Filesystem layout

```text
/opt/gugabobo/
├── repo/
│   ├── .venv/
│   └── .env
└── data/
    ├── gugabobo.db
    ├── logs/
    ├── sandbox/
    └── claude-home/
```

Runtime data and Claude credentials stay outside the source tree. A local Git
clone used for an improvement therefore cannot copy `.env`, the production
database, or the runner credential directory.

## Private repository access

Create a dedicated SSH key as the service user:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
ssh-keygen -t ed25519 -f ~/.ssh/gugabobo_deploy -C gugabobo-server
cat ~/.ssh/gugabobo_deploy.pub
```

Add the public key in the repository's GitHub settings under **Deploy keys**.
Read-only access is sufficient for deployment because self-improvement pushes
use `GUGABOBO_GITHUB_TOKEN`, not this key.

Configure SSH on the server:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/gugabobo_deploy
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
ssh-keyscan github.com >> ~/.ssh/known_hosts
ssh -T git@github.com
```

## First installation

```bash
sudo mkdir -p /opt/gugabobo
sudo chown -R ubuntu:ubuntu /opt/gugabobo
git clone git@github.com:GugaBoBo-s/gugabobo.git /opt/gugabobo/repo
sudo bash /opt/gugabobo/repo/deploy/setup.sh
```

The setup script installs Python and Docker, installs the package, builds the
isolated runner image, runs Ruff and pytest, and installs the systemd units. It
does not overwrite an existing `.env`.

## Configuration

Edit `/opt/gugabobo/repo/.env` and keep it mode `600`:

```bash
sudo -u ubuntu nano /opt/gugabobo/repo/.env
chmod 600 /opt/gugabobo/repo/.env
```

At minimum, set a long random `GUGABOBO_ADMIN_TOKEN`, one LLM provider and key,
and the relevant QQ or Telegram values. For self-improvement, use a fine-grained
PAT from the GuGabobo GitHub account with **Contents: read/write** and **Pull
requests: read/write** on this repository.

## Isolated Claude Code authentication

Claude Code runs only in `gugabobo-runner:local`. Its dedicated home directory
is mounted into the container; the service user's normal home and the host
environment are not mounted or forwarded.

```bash
sudo -u ubuntu docker run --rm -it \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  --mount type=bind,source=/opt/gugabobo/data/claude-home,target=/home/runner \
  --env HOME=/home/runner \
  gugabobo-runner:local claude auth login
```

Verify the dedicated login:

```bash
sudo -u ubuntu docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  --mount type=bind,source=/opt/gugabobo/data/claude-home,target=/home/runner \
  --env HOME=/home/runner \
  gugabobo-runner:local claude auth status
```

Generated edits run with a read-only container root, dropped capabilities,
resource limits, no Docker socket, and only the sandbox clone plus dedicated
runner home mounted. Ruff and pytest run in a second container with networking
disabled. There is no host-execution fallback.

## Start and verify

```bash
sudo systemctl restart gugabobo-api
sudo systemctl status gugabobo-api --no-pager
sudo journalctl -u gugabobo-api -n 50 --no-pager
curl --fail http://127.0.0.1:8765/health
/opt/gugabobo/repo/.venv/bin/gugabobo status
```

Open an SSH tunnel from the local computer:

```bash
ssh -L 8765:127.0.0.1:8765 ubuntu@<server-ip>
```

Then open `http://127.0.0.1:8765/dashboard`.

## Telegram polling

The Dashboard can start and stop Telegram polling. Alternatively, enable the
separate service for automatic startup:

```bash
sudo systemctl enable --now gugabobo-telegram
```

Use only one polling process. The Dashboard runtime controls do not manage the
optional systemd polling unit.

## Updates

```bash
sudo bash /opt/gugabobo/repo/deploy/setup.sh
sudo systemctl restart gugabobo-api
curl --fail http://127.0.0.1:8765/health
```

The setup command uses `git pull --ff-only`, rebuilds the runner image, and
reruns the complete test suite before the service is restarted.

## Security invariants

- Keep the API on `127.0.0.1` and use an SSH tunnel.
- Never commit `.env`, backup environment files, bot tokens, or PATs.
- Never mount `/var/run/docker.sock` into the runner container.
- Never enable `bypassPermissions` or a host-execution fallback.
- Require owner approval and explicit confirmation before running or shipping an
  improvement.
- Never auto-merge generated pull requests.
