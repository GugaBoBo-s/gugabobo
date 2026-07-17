from __future__ import annotations

import base64
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from gugabobo.config import Settings, get_settings


@dataclass(frozen=True)
class PullRequestResult:
    number: int
    url: str
    branch_name: str
    status: str = "open"
    merged_at: str = ""


@dataclass(frozen=True)
class MergeResult:
    merged: bool
    sha: str
    message: str


@dataclass(frozen=True)
class ReviewResult:
    review_id: int
    url: str


class GitHubClient:
    def __init__(
        self,
        settings: Settings | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._owner = owner or self.settings.github_owner
        self._repo = repo or self.settings.github_repo
        self._canonical_owner = ""

    @property
    def configured(self) -> bool:
        return bool(self.settings.github_token)

    @property
    def owner(self) -> str:
        return self._owner

    @property
    def repo(self) -> str:
        return self._repo

    @property
    def token(self) -> str:
        return self.settings.github_token

    @property
    def push_url(self) -> str:
        return f"https://x-access-token@github.com/{self.owner}/{self.repo}.git"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _url(self, path: str) -> str:
        owner = quote(self.owner, safe="")
        repo = quote(self.repo, safe="")
        return f"{self.settings.github_api_url.rstrip('/')}/repos/{owner}/{repo}{path}"

    def _api_url(self, path: str) -> str:
        return f"{self.settings.github_api_url.rstrip('/')}{path}"

    def _request_url(
        self,
        method: str,
        url: str,
        payload: dict | None = None,
        params: dict[str, object] | None = None,
    ) -> object:
        if not self.configured:
            raise RuntimeError("GUGABOBO_GITHUB_TOKEN is not configured")
        with httpx.Client(timeout=30) as client:
            response = client.request(
                method,
                url,
                headers=self._headers(),
                json=payload,
                params=params,
            )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    def _request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        params: dict[str, object] | None = None,
    ) -> object:
        return self._request_url(method, self._url(path), payload, params)

    def _paginate(
        self,
        url: str,
        params: dict[str, object] | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        page = 1
        items: list[dict] = []
        while limit is None or len(items) < limit:
            page_params = dict(params or {})
            page_params.update({"per_page": 100, "page": page})
            data = self._request_url("GET", url, params=page_params)
            if not isinstance(data, list):
                break
            items.extend(dict(item) for item in data if isinstance(item, dict))
            if len(data) < 100:
                break
            page += 1
        return items if limit is None else items[:limit]

    def get_default_branch(self) -> str:
        data = self._request("GET", "")
        self._remember_canonical_owner(data)
        return str(data.get("default_branch", "main"))

    def get_repository_owner_login(self) -> str:
        if self._canonical_owner:
            return self._canonical_owner
        data = self._request("GET", "")
        self._remember_canonical_owner(data)
        return self._canonical_owner or self.owner

    def get_authenticated_login(self) -> str:
        data = self._request_url("GET", self._api_url("/user"))
        return str(data.get("login", "")) if isinstance(data, dict) else ""

    def get_branch_sha(self, branch: str) -> str:
        data = self._request("GET", f"/git/ref/heads/{branch}")
        return str(data["object"]["sha"])

    def try_get_branch_sha(self, branch: str) -> str:
        try:
            return self.get_branch_sha(branch)
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                return ""
            raise

    def create_branch(self, branch: str, from_sha: str) -> dict:
        return self._request(
            "POST",
            "/git/refs",
            {"ref": f"refs/heads/{branch}", "sha": from_sha},
        )

    def put_file(self, path: str, content: str, message: str, branch: str) -> dict:
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        return self._request(
            "PUT",
            f"/contents/{path}",
            {"message": message, "content": encoded, "branch": branch},
        )

    def create_pull_request(
        self,
        title: str,
        head: str,
        base: str,
        body: str = "",
    ) -> PullRequestResult:
        data = self._request(
            "POST",
            "/pulls",
            {"title": title, "head": head, "base": base, "body": body},
        )
        return PullRequestResult(
            number=int(data["number"]),
            url=str(data["html_url"]),
            branch_name=head,
        )

    def get_pull_request(self, number: int) -> dict:
        result = self._request("GET", f"/pulls/{number}")
        return dict(result) if isinstance(result, dict) else {}

    def merge_pull_request(
        self,
        number: int,
        commit_title: str,
        merge_method: str = "squash",
        sha: str = "",
    ) -> MergeResult:
        payload = {"commit_title": commit_title, "merge_method": merge_method}
        if sha:
            payload["sha"] = sha
        data = self._request(
            "PUT",
            f"/pulls/{number}/merge",
            payload,
        )
        return MergeResult(
            merged=bool(data.get("merged")),
            sha=str(data.get("sha", "")),
            message=str(data.get("message", "")),
        )

    def close_pull_request(self, number: int) -> dict:
        result = self._request("PATCH", f"/pulls/{number}", {"state": "closed"})
        return dict(result) if isinstance(result, dict) else {}

    def get_commit_status(self, ref: str) -> dict:
        result = self._request("GET", f"/commits/{ref}/status")
        return dict(result) if isinstance(result, dict) else {}

    def get_check_runs(self, ref: str) -> dict:
        result = self._request("GET", f"/commits/{ref}/check-runs")
        return dict(result) if isinstance(result, dict) else {}

    def get_checks_status(self, ref: str, required_name: str = "") -> str:
        try:
            data = self.get_check_runs(ref)
        except httpx.HTTPStatusError as error:
            if error.response.status_code in {403, 404}:
                return "unknown"
            raise
        check_runs = data.get("check_runs", [])
        if required_name and isinstance(check_runs, list):
            check_runs = [
                item for item in check_runs if str(item.get("name", "")) == required_name
            ]
        if not isinstance(check_runs, list) or not check_runs:
            return "unknown"
        if any(str(item.get("status", "")) != "completed" for item in check_runs):
            return "pending"
        successful = {"success", "neutral", "skipped"}
        conclusions = {str(item.get("conclusion", "")) for item in check_runs}
        if required_name:
            return "success" if conclusions == {"success"} else "failure"
        return "success" if conclusions <= successful else "failure"

    def list_organization_repositories(self, organization: str) -> list[dict]:
        organization_name = quote(organization, safe="")
        return self._paginate(
            self._api_url(f"/orgs/{organization_name}/repos"),
            {"type": "all", "sort": "full_name", "direction": "asc"},
        )

    def list_pull_requests(self, state: str = "open") -> list[dict]:
        return self._paginate(self._url("/pulls"), {"state": state})

    def list_issues(self, state: str = "open", limit: int | None = None) -> list[dict]:
        page = 1
        issues: list[dict] = []
        while limit is None or len(issues) < limit:
            data = self._request(
                "GET",
                "/issues",
                params={
                    "state": state,
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": 100,
                    "page": page,
                },
            )
            if not isinstance(data, list):
                break
            issues.extend(
                dict(item)
                for item in data
                if isinstance(item, dict) and "pull_request" not in item
            )
            if len(data) < 100:
                break
            page += 1
        return issues if limit is None else issues[:limit]

    def has_open_linked_pull_request(self, issue_number: int) -> bool:
        timeline = self._paginate(self._url(f"/issues/{issue_number}/timeline"))
        for event in timeline:
            if str(event.get("event", "")) != "cross-referenced":
                continue
            source = event.get("source", {})
            linked = source.get("issue", {}) if isinstance(source, dict) else {}
            if (
                isinstance(linked, dict)
                and "pull_request" in linked
                and str(linked.get("state", "")) == "open"
            ):
                return True
        return False

    def find_pull_request_by_head(self, branch: str) -> dict:
        canonical_owner = self.get_repository_owner_login()
        pulls = self._paginate(
            self._url("/pulls"),
            {"state": "all", "head": f"{canonical_owner}:{branch}"},
            limit=1,
        )
        return pulls[0] if pulls else {}

    def _remember_canonical_owner(self, data: object) -> None:
        if not isinstance(data, dict):
            return
        owner = data.get("owner", {})
        if isinstance(owner, dict):
            self._canonical_owner = str(owner.get("login", ""))

    def list_pull_request_files(self, number: int, limit: int = 100) -> list[dict]:
        return self._paginate(self._url(f"/pulls/{number}/files"), limit=limit)

    def list_pull_request_reviews(self, number: int) -> list[dict]:
        return self._paginate(self._url(f"/pulls/{number}/reviews"))

    def create_pull_request_review(
        self,
        number: int,
        body: str,
        commit_id: str,
    ) -> ReviewResult:
        data = self._request(
            "POST",
            f"/pulls/{number}/reviews",
            {"body": body, "commit_id": commit_id, "event": "COMMENT"},
        )
        return ReviewResult(
            review_id=int(data["id"]),
            url=str(data.get("html_url", "")),
        )
