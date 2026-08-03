from pathlib import Path
from types import SimpleNamespace

import pytest

from gugabobo.infra.glitter_client import GlitterClient


def test_glitter_sends_only_from_configured_root(tmp_path, monkeypatch):
    root = tmp_path / "send"
    root.mkdir()
    (root / "report.txt").write_text("hello", encoding="utf-8")
    captured = {}

    def run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="transfer complete", stderr="")

    monkeypatch.setattr("gugabobo.infra.glitter_client.subprocess.run", run)

    result = GlitterClient(root, 15).send("laptop", "report.txt")

    assert result == "transfer complete"
    assert captured["command"][1:5] == ["-m", "glitter", "send", "--quiet"]
    assert captured["command"][-2] == "laptop"
    assert Path(captured["command"][-1]) == (root / "report.txt").resolve()
    assert captured["timeout"] == 15


def test_glitter_rejects_path_outside_configured_root(tmp_path):
    root = tmp_path / "send"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(ValueError, match="发送目录"):
        GlitterClient(root, 15).send("laptop", "../secret.txt")
