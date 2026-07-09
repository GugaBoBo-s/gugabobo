from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx

from gugabobo.config import Settings, get_settings


@dataclass(frozen=True)
class PullRequestResult:
    number: int
    url: str
    branch_name: str


class GitHubClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.github_token)

    @property
    def owner(self) -> str:
        return self.settings.github_owner

    @property
    def repo(self) -> str:
        return self.settings.github_repo

    @property
    def push_url(self) -> str:
        return (
            f"https://x-access-token:{self.settings.github_token}"
            f"@github.com/{self.owner}/{self.repo}.git"
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _url(self, path: str) -> str:
        return f"{self.settings.github_api_url.rstrip('/')}/repos/{self.owner}/{self.repo}{path}"

    def _request(self, method: str, path: str, payload: dict | None = None) -> object:
        if not self.configured:
            raise RuntimeError("GUGABOBO_GITHUB_TOKEN is not configured")
        with httpx.Client(timeout=30) as client:
            response = client.request(method, self._url(path), headers=self._headers(), json=payload)
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    def get_default_branch(self) -> str:
        data = self._request("GET", "")
        return str(data.get("default_branch", "main"))

    def get_branch_sha(self, branch: str) -> str:
        data = self._request("GET", f"/git/ref/heads/{branch}")
        return str(data["object"]["sha"])

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

    def get_commit_status(self, ref: str) -> dict:
        result = self._request("GET", f"/commits/{ref}/status")
        return dict(result) if isinstance(result, dict) else {}

    def list_pull_requests(self, state: str = "open") -> list[dict]:
        data = self._request("GET", f"/pulls?state={state}")
        if isinstance(data, list):
            return [dict(item) for item in data]
        return []
