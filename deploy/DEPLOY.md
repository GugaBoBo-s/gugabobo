# gugabobo server deployment

Target platform: Ubuntu 24.04 with the API bound to localhost. The repository is
private, so the server needs deploy-only GitHub authentication before cloning.

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

Prepare the installation directory:

```bash
sudo mkdir -p /opt/gugabobo
sudo chown -R ubuntu:ubuntu /opt/gugabobo
```

If the organization permits repository deploy keys, create a dedicated SSH key
as the service user:

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
git clone git@github.com:GugaBoBo-s/gugabobo.git /opt/gugabobo/repo
```

If organization policy disables deploy keys, clone once with a fine-grained PAT
provided through a temporary credential helper, never inside the remote URL:

```bash
read -rsp "GitHub token: " GUGABOBO_GITHUB_TOKEN && echo
export GUGABOBO_GITHUB_TOKEN
git -c credential.helper='!f() { if [ "$1" = get ]; then printf "username=x-access-token\npassword=%s\n" "$GUGABOBO_GITHUB_TOKEN"; fi; }; f' \
  clone https://github.com/GugaBoBo-s/gugabobo.git /opt/gugabobo/repo
unset GUGABOBO_GITHUB_TOKEN
```

Create `/opt/gugabobo/repo/.env` from the deployment example and set
`GUGABOBO_GITHUB_TOKEN` before running `setup.sh`. The setup script registers
`deploy/git-credential-gugabobo` for this clone and changes `origin` to a
tokenless HTTPS URL. The helper reads the token from the mode-600 `.env` only
when Git requests credentials for `github.com`.

## First installation

After cloning with either authentication method, create the production
configuration before running setup so private Git pulls can use its token:

```bash
cp /opt/gugabobo/repo/deploy/gugabobo.env.example /opt/gugabobo/repo/.env
sudo -u ubuntu nano /opt/gugabobo/repo/.env
chmod 600 /opt/gugabobo/repo/.env
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

If Docker Hub or `github.com` requires the server's local HTTP proxy, set
`GUGABOBO_DOCKER_PROXY=http://127.0.0.1:<port>`. When this value is empty, setup
also accepts a local HTTP `GUGABOBO_TELEGRAM_PROXY`. Only loopback HTTP proxy
URLs are accepted for automatic Docker daemon configuration.

For servers with a slow path to Debian's default repository, set a trusted base
mirror such as `GUGABOBO_DEBIAN_MIRROR=https://mirrors.cloud.tencent.com`.
The value replaces only `http://deb.debian.org` inside the runner build.

## Isolated Claude Code authentication

Claude Code runs only in `gugabobo-runner:local`. Its dedicated home directory
is mounted into the container; the service user's normal home and the host
environment are not mounted or forwarded.

For an Anthropic-compatible gateway, configure the following values in the
mode-600 `.env` file:

```bash
GUGABOBO_CLAUDE_BASE_URL=https://gateway.example.com
GUGABOBO_CLAUDE_AUTH_TOKEN=replace-with-gateway-token
```

The runner maps these values to `ANTHROPIC_BASE_URL` and
`ANTHROPIC_AUTH_TOKEN` only inside the short-lived Claude Code container. The
token is not included in the Docker command line or Dashboard response. No
interactive login is required in this mode.

When no gateway token is configured, authenticate the dedicated runner home:

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

## Lifecycle agent

Enable the persistent PR synchronization, notification retry, and authorized
merge loop:

```bash
sudo systemctl enable --now gugabobo-agent
sudo systemctl status gugabobo-agent --no-pager
```

## Updates

```bash
sudo bash /opt/gugabobo/repo/deploy/setup.sh
sudo systemctl restart gugabobo-api
sudo systemctl restart gugabobo-telegram gugabobo-agent
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
- Never merge without explicit authenticated owner authorization.
- Owner authorization may come from QQ, Telegram, Dashboard, or CLI, but the
  lifecycle agent must still observe successful GitHub checks before merging.
- Keep merge authorization separate from deployment; setup records the deployed
  server revision after tests pass.
