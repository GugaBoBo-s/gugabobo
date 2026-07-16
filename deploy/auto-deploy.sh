#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${GUGABOBO_ROOT:-/opt/gugabobo}"
REPO_DIR="$ROOT/repo"
DATA_DIR="$ROOT/data"
STAGING_ROOT="$ROOT/deploy-staging"
RUN_USER="${GUGABOBO_RUN_USER:-ubuntu}"
BRANCH="main"
RUNNER_IMAGE="${GUGABOBO_RUNNER_IMAGE:-gugabobo-runner:local}"
STATUS_FILE="$DATA_DIR/deploy-status.json"
FAILED_TARGET_FILE="$DATA_DIR/deploy-failed-target"
LOCK_FILE="/run/lock/gugabobo-deploy.lock"
staging=""
reporter=""
target_revision=""
old_revision=""
old_image=""
activated=0
telegram_was_active=0
failure_detail="Automated deployment failed during initialization."
deployment_current_revision=""

if [ "$(id -u)" -ne 0 ]; then
  echo "gugabobo auto deployment must run as root" >&2
  exit 1
fi

mkdir -p "$DATA_DIR" "$STAGING_ROOT"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  exit 0
fi

write_status() {
  local status="$1"
  local detail="$2"
  python3 - "$STATUS_FILE" "$status" "$old_revision" "$target_revision" "$detail" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "status": sys.argv[2],
    "current_revision": sys.argv[3],
    "target_revision": sys.argv[4],
    "detail": sys.argv[5],
    "updated_at": datetime.now(timezone.utc).isoformat(),
}
temporary = path.with_suffix(".tmp")
temporary.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
os.chmod(temporary, 0o644)
os.replace(temporary, path)
PY
}

run_as_user() {
  runuser -u "$RUN_USER" -- "$@"
}

read_env_value() {
  local key="$1"
  local value
  value=$(sed -n "s/^${key}=//p" "$REPO_DIR/.env" | head -n 1 | tr -d '\r')
  case "$value" in
    \"*\") value="${value#\"}"; value="${value%\"}" ;;
    \'*\') value="${value#\'}"; value="${value%\'}" ;;
  esac
  printf '%s' "$value"
}

verify_github_target() {
  local github_token="$1"
  local github_api_url="$2"
  local github_owner="$3"
  local github_repo="$4"
  local pull_request_number="$5"
  GITHUB_TOKEN="$github_token" python3 - \
    "$github_api_url" "$github_owner" "$github_repo" "$target_revision" \
    "$pull_request_number" <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request

base_url, owner, repo, revision, pull_request_number = sys.argv[1:]
headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
    "X-GitHub-Api-Version": "2022-11-28",
}

def get(path):
    request = urllib.request.Request(f"{base_url.rstrip('/')}{path}", headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


try:
    pulls = get(f"/repos/{owner}/{repo}/commits/{revision}/pulls")
    checks = get(f"/repos/{owner}/{repo}/commits/{revision}/check-runs?per_page=100")
except (urllib.error.URLError, ValueError, KeyError) as error:
    print(f"GitHub deployment verification failed: {error}", file=sys.stderr)
    raise SystemExit(1)

merged = [
    pull
    for pull in pulls
    if str(pull.get("number")) == pull_request_number
    and pull.get("merged_at")
    and (pull.get("base") or {}).get("ref") == "main"
]
if not merged:
    raise SystemExit(2)
test_runs = [run for run in checks.get("check_runs", []) if run.get("name") == "test"]
if not test_runs or any(run.get("status") != "completed" for run in test_runs):
    raise SystemExit(2)
if any(run.get("conclusion") != "success" for run in test_runs):
    raise SystemExit(3)
PY
}

verify_pending_deployment() {
  local db_path="$1"
  python3 - "$db_path" "$target_revision" <<'PY'
import sqlite3
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(2)
try:
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT pull_requests.github_owner, pull_requests.github_repo, "
            "pull_requests.number FROM deployment_records "
            "JOIN pull_requests ON pull_requests.id = deployment_records.pull_request_id "
            "WHERE deployment_records.target_revision = ? "
            "AND deployment_records.status = 'pending'",
            (sys.argv[2],),
        ).fetchall()
except sqlite3.Error:
    raise SystemExit(2)
if len(rows) != 1:
    raise SystemExit(2)
print(f"{rows[0][0]}\t{rows[0][1]}\t{rows[0][2]}")
PY
}

mark_pending_deployment_failed() {
  local db_path="$1"
  local detail="$2"
  local current_revision="$3"
  if [ -z "$target_revision" ] || [ ! -f "$db_path" ]; then
    return
  fi
  python3 - "$db_path" "$target_revision" "$detail" "$current_revision" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as connection:
    connection.execute(
        "UPDATE deployment_records SET status = 'failed', detail = ?, "
        "deployed_revision = ?, deployed_at = '', updated_at = CURRENT_TIMESTAMP "
        "WHERE target_revision = ? AND status = 'pending'",
        (sys.argv[3], sys.argv[4], sys.argv[2]),
    )
PY
}

health_check() {
  local attempt
  for attempt in $(seq 1 30); do
    if curl --fail --silent http://127.0.0.1:8765/health >/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

install_runtime_files() {
  if [ -f "$REPO_DIR/deploy/auto-deploy.sh" ]; then
    install -m 0755 "$REPO_DIR/deploy/auto-deploy.sh" /usr/local/sbin/gugabobo-auto-deploy
  fi
  if [ -f "$REPO_DIR/deploy/gugabobo-deploy.service" ]; then
    install -m 0644 "$REPO_DIR/deploy/gugabobo-deploy.service" /etc/systemd/system/gugabobo-deploy.service
  fi
  if [ -f "$REPO_DIR/deploy/gugabobo-deploy.timer" ]; then
    install -m 0644 "$REPO_DIR/deploy/gugabobo-deploy.timer" /etc/systemd/system/gugabobo-deploy.timer
  fi
  install -m 0644 "$REPO_DIR/deploy/gugabobo-api.service" /etc/systemd/system/gugabobo-api.service
  install -m 0644 "$REPO_DIR/deploy/gugabobo-telegram.service" /etc/systemd/system/gugabobo-telegram.service
  install -m 0644 "$REPO_DIR/deploy/gugabobo-agent.service" /etc/systemd/system/gugabobo-agent.service
  systemctl daemon-reload
}

restart_runtime() {
  systemctl restart gugabobo-api gugabobo-agent
  if [ "$telegram_was_active" -eq 1 ]; then
    systemctl restart gugabobo-telegram
  fi
}

report_deployment() {
  local status="$1"
  local detail="$2"
  if [ -z "$target_revision" ] || [ ! -x "$reporter" ]; then
    return
  fi
  local current_revision="${deployment_current_revision:-$old_revision}"
  if [ "$status" = "deployed" ]; then
    current_revision="$target_revision"
  fi
  (
    cd "$REPO_DIR"
    run_as_user "$reporter" deployment report "$status" "$target_revision" \
      --current-revision "$current_revision" --detail "$detail"
  ) || true
}

cleanup() {
  if [ -n "$staging" ]; then
    case "$staging" in
      "$STAGING_ROOT"/*) rm -rf -- "$staging" ;;
    esac
  fi
  if [ -n "$target_revision" ]; then
    docker image rm "gugabobo-runner:$target_revision" >/dev/null 2>&1 || true
  fi
}

rollback() {
  if [ "$activated" -ne 1 ] || [ -z "$old_revision" ]; then
    return
  fi
  run_as_user git -C "$REPO_DIR" reset --hard "$old_revision"
  run_as_user "$REPO_DIR/.venv/bin/python" -m pip install -e "$REPO_DIR[dev]"
  if [ -n "$old_image" ]; then
    docker tag "$old_image" "$RUNNER_IMAGE"
  fi
  install_runtime_files
  restart_runtime
  health_check
}

on_error() {
  local exit_code=$?
  trap - ERR
  set +e
  if [ -n "$target_revision" ]; then
    printf '%s\n' "$target_revision" > "$FAILED_TARGET_FILE"
  fi
  rollback_status=0
  rollback || rollback_status=$?
  deployment_current_revision="$old_revision"
  if [ "$rollback_status" -eq 0 ]; then
    rollback_detail="Production remained on or was restored to the previous revision."
  else
    deployment_current_revision=""
    rollback_detail="Rollback did not pass its health check; operator action is required."
  fi
  if [ -n "${db_path:-}" ]; then
    mark_pending_deployment_failed "$db_path" "$failure_detail" "$deployment_current_revision"
  fi
  write_status "failed" "$failure_detail $rollback_detail"
  report_deployment "failed" "$failure_detail $rollback_detail"
  exit "$exit_code"
}

trap on_error ERR
trap cleanup EXIT

auto_deploy_enabled=$(read_env_value GUGABOBO_AUTO_DEPLOY_ENABLED | tr '[:upper:]' '[:lower:]')
case "$auto_deploy_enabled" in
  0|false|no|off)
    write_status "disabled" "Automatic deployment is disabled by configuration."
    exit 0
    ;;
esac

failure_detail="Failed to fetch the canonical deployment branch."
run_as_user git -C "$REPO_DIR" fetch --quiet origin "$BRANCH"
old_revision=$(run_as_user git -C "$REPO_DIR" rev-parse HEAD)
target_revision=$(run_as_user git -C "$REPO_DIR" rev-parse "origin/$BRANCH")

if ! [[ "$target_revision" =~ ^[0-9a-f]{40}$ ]]; then
  write_status "blocked" "The deployment target is not a valid commit SHA."
  trap - ERR
  exit 1
fi

if ! run_as_user git -C "$REPO_DIR" diff-index --quiet HEAD --; then
  write_status "blocked" "The production repository has tracked local changes."
  trap - ERR
  exit 1
fi

if [ "$old_revision" = "$target_revision" ]; then
  rm -f "$FAILED_TARGET_FILE"
  write_status "current" "Production already matches origin/$BRANCH."
  exit 0
fi

if [ -f "$FAILED_TARGET_FILE" ] && [ "$(cat "$FAILED_TARGET_FILE")" = "$target_revision" ]; then
  write_status "blocked" "This revision already failed deployment and will not be retried."
  exit 0
fi

if ! run_as_user git -C "$REPO_DIR" merge-base --is-ancestor "$old_revision" "$target_revision"; then
  write_status "blocked" "The deployment target is not a fast-forward of production."
  trap - ERR
  exit 1
fi

db_path=$(read_env_value GUGABOBO_DB_PATH)
db_path="${db_path:-$DATA_DIR/gugabobo.db}"
case "$db_path" in
  /*) ;;
  *) db_path="$REPO_DIR/$db_path" ;;
esac
set +e
deployment_reference=$(verify_pending_deployment "$db_path")
pending_status=$?
set -e
if [ "$pending_status" -ne 0 ]; then
  write_status "waiting" "Waiting for the lifecycle agent to create a pending deployment record."
  exit 0
fi
IFS=$'\t' read -r deployment_owner deployment_repo deployment_pr_number <<< "$deployment_reference"

github_token=$(read_env_value GUGABOBO_GITHUB_TOKEN)
github_api_url=$(read_env_value GUGABOBO_GITHUB_API_URL)
github_api_url="${github_api_url:-https://api.github.com}"
if [ -z "$github_token" ]; then
  write_status "blocked" "GitHub token is required to verify the deployment target."
  exit 0
fi
set +e
verify_github_target "$github_token" "$github_api_url" "$deployment_owner" \
  "$deployment_repo" "$deployment_pr_number"
verification_status=$?
set -e
case "$verification_status" in
  0) ;;
  2)
    write_status "waiting" "Waiting for a merged main pull request and successful CI check."
    exit 0
    ;;
  3)
    write_status "blocked" "The required GitHub Actions test check failed."
    exit 0
    ;;
  *)
    write_status "blocked" "GitHub could not verify the deployment target."
    exit 0
    ;;
esac

if [ "${GUGABOBO_DEPLOY_DRY_RUN:-0}" = "1" ]; then
  write_status "ready" "A fast-forward deployment candidate is available."
  exit 0
fi

staging="$STAGING_ROOT/$target_revision"
case "$staging" in
  "$STAGING_ROOT"/*) rm -rf -- "$staging" ;;
  *) exit 1 ;;
esac
mkdir -p "$staging"
run_as_user git -C "$REPO_DIR" archive "$target_revision" | tar -x -C "$staging"
chown -R "$RUN_USER":"$RUN_USER" "$staging"

write_status "validating" "Installing and testing the deployment candidate."
failure_detail="Candidate dependency installation or tests failed."
run_as_user python3 -m venv "$staging/.venv"
run_as_user "$staging/.venv/bin/python" -m pip install --upgrade pip
run_as_user "$staging/.venv/bin/python" -m pip install -e "$staging[dev]"
reporter="$staging/.venv/bin/gugabobo"
run_as_user "$staging/.venv/bin/python" -m ruff check "$staging"
(
  cd "$staging"
  run_as_user "$staging/.venv/bin/python" -m pytest -q
)

docker_proxy=$(read_env_value GUGABOBO_DOCKER_PROXY)
if [ -z "$docker_proxy" ]; then
  docker_proxy=$(read_env_value GUGABOBO_TELEGRAM_PROXY)
fi
if ! printf '%s' "$docker_proxy" | grep -Eq '^https?://(127\.0\.0\.1|localhost):[0-9]+/?$'; then
  docker_proxy=""
fi
debian_mirror=$(read_env_value GUGABOBO_DEBIAN_MIRROR)
if ! printf '%s' "$debian_mirror" | grep -Eq '^https?://[A-Za-z0-9._:/-]+$'; then
  debian_mirror=""
fi
build_args=()
if [ -n "$docker_proxy" ]; then
  build_args+=(--network=host)
  build_args+=(--build-arg "HTTP_PROXY=$docker_proxy")
  build_args+=(--build-arg "HTTPS_PROXY=$docker_proxy")
fi
if [ -n "$debian_mirror" ]; then
  build_args+=(--build-arg "DEBIAN_MIRROR=$debian_mirror")
fi

failure_detail="Candidate runner image build failed."
docker build "${build_args[@]}" -f "$staging/deploy/Dockerfile.runner" -t "gugabobo-runner:$target_revision" "$staging"
old_image=$(docker image inspect "$RUNNER_IMAGE" --format '{{.Id}}' 2>/dev/null || true)
if [ -n "$old_image" ]; then
  docker tag "$old_image" gugabobo-runner:rollback
fi

write_status "deploying" "Candidate passed validation; activating production."
failure_detail="Production activation or health verification failed."
telegram_was_active=0
if systemctl is-active --quiet gugabobo-telegram; then
  telegram_was_active=1
fi
run_as_user git -C "$REPO_DIR" merge --ff-only "origin/$BRANCH"
activated=1
run_as_user "$REPO_DIR/.venv/bin/python" -m pip install -e "$REPO_DIR[dev]"
docker tag "gugabobo-runner:$target_revision" "$RUNNER_IMAGE"
install_runtime_files
systemctl enable gugabobo-deploy.timer
restart_runtime
health_check

reporter="$REPO_DIR/.venv/bin/gugabobo"
(
  cd "$REPO_DIR"
  run_as_user "$reporter" deployment record-current
)
report_deployment "deployed" "Tests, runner build, service restart, and health check passed."
rm -f "$FAILED_TARGET_FILE"
activated=0
old_revision="$target_revision"
write_status "deployed" "Production deployment and health verification completed."
trap - ERR
