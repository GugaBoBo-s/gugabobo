# gugabobo server deployment

Target: Tencent Lighthouse, Ubuntu 24.04, login user `ubuntu`. Everything lives
under a single root directory `/opt/gugabobo`.

## Layout

```
/opt/gugabobo/
├─ repo/            git clone (service working directory)
│  ├─ .venv/        Python virtual environment
│  └─ .env          config + secrets (chmod 600, gitignored)
└─ data/            runtime state, separate from source
   ├─ gugabobo.db
   ├─ logs/
   └─ sandbox/      self-improvement sandbox clones
```

Runtime data uses absolute paths so the source clone stays clean and the
self-improvement diff never picks up runtime files. `.env` is gitignored, so it
is never copied into a sandbox clone — the bot token stays out of sandboxes.

## 1. First-time setup

SSH in as `ubuntu`, then:

```bash
sudo apt-get update -y && sudo apt-get install -y git
sudo git clone https://github.com/GugaBoBo-s/gugabobo.git /opt/gugabobo/repo
sudo bash /opt/gugabobo/repo/deploy/setup.sh
```

`setup.sh` is idempotent: it installs packages, creates the layout, sets up the
venv with dev extras, seeds `.env` from the template, and installs the systemd
service.

## 2. Configure secrets

Edit `/opt/gugabobo/repo/.env`:

- `GUGABOBO_ADMIN_TOKEN` — long random string for dashboard admin actions
- `GUGABOBO_GITHUB_TOKEN` — a PAT from the **GuGabobo** bot account (see below)
- `GUGABOBO_MOONSHOT_API_KEY` — LLM key
- optional: Telegram / QQ settings

Keep it locked down:

```bash
chmod 600 /opt/gugabobo/repo/.env
```

## 3. GuGabobo bot account (so PRs come from the bot, not you)

1. Log in to GitHub as **GuGabobo**.
2. Create a fine-grained PAT scoped to the `GugaBoBo-s/gugabobo` repo with
   Contents: read/write and Pull requests: read/write.
3. Put it in `GUGABOBO_GITHUB_TOKEN`.
4. Make sure GuGabobo is a member of `GugaBoBo-s` with write access to the repo,
   otherwise it cannot push branches.

Commits are already authored as `GuGabobo <263493647+GuGabobo@users.noreply.github.com>`
via `GUGABOBO_GIT_AUTHOR_NAME/EMAIL`.

## 4. Claude Code (self-improvement runner)

gugabobo does not implement its own coding agent — `improve run` / `improve ship`
call Claude Code. Install and authenticate it for the `ubuntu` user:

```bash
sudo apt-get install -y nodejs npm
npm install -g @anthropic-ai/claude-code
claude   # run once interactively to log in, then exit
```

The service runs as `ubuntu`, so authenticate as `ubuntu` (not root). Until
Claude Code is authenticated, `improve run` / `improve ship` return a clear
error and nothing else breaks.

## 5. Start and verify

```bash
sudo systemctl restart gugabobo-api
sudo systemctl status gugabobo-api --no-pager
sudo journalctl -u gugabobo-api -n 50 --no-pager
```

Smoke test on the server:

```bash
/opt/gugabobo/repo/.venv/bin/gugabobo status
curl -s http://127.0.0.1:8765/health
```

## 6. Reach the dashboard

The API binds to `127.0.0.1` only — do not expose it publicly. Open an SSH
tunnel from your local machine:

```bash
ssh -L 8765:127.0.0.1:8765 ubuntu@154.8.222.13
# then browse http://127.0.0.1:8765/dashboard
```

## 7. Update to a new version

```bash
sudo bash /opt/gugabobo/repo/deploy/setup.sh   # pulls, reinstalls deps
sudo systemctl restart gugabobo-api
```

## 8. Telegram (optional)

With `GUGABOBO_TELEGRAM_BOT_TOKEN` set, start local polling from the dashboard
(Runtime controls) or run `gugabobo telegram poll --send`. No public webhook is
required, which suits a localhost-only API.

## Security notes

- API stays on localhost; access via SSH tunnel, not a public port.
- `.env` is `chmod 600` and holds the bot token and LLM key — never commit it.
- Claude Code runs with `bypassPermissions` **inside a throwaway sandbox clone**
  only; it never touches `/opt/gugabobo/repo` or `main` directly.
- Self-improvement still requires owner approval before a PR is opened, and PRs
  are never auto-merged.
- Do not run the service as root; keep it as `ubuntu`.

