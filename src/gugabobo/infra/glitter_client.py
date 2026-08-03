from __future__ import annotations

import subprocess
import sys
from pathlib import Path


class GlitterClient:
    def __init__(self, send_root: Path, timeout_seconds: int) -> None:
        self.send_root = send_root.resolve()
        self.timeout_seconds = timeout_seconds

    def send(self, peer: str, requested_path: str) -> str:
        target_peer = peer.strip()
        if not target_peer:
            raise ValueError("Glitter 接收端不能为空")
        path = (self.send_root / requested_path).resolve()
        if not path.is_relative_to(self.send_root):
            raise ValueError("文件路径必须位于 Glitter 发送目录内")
        if not path.exists():
            raise FileNotFoundError(f"找不到待发送文件：{requested_path}")
        result = subprocess.run(
            [sys.executable, "-m", "glitter", "send", "--quiet", target_peer, str(path)],
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        output = (result.stdout or result.stderr).strip()
        if result.returncode != 0:
            raise RuntimeError(output or f"Glitter 退出码为 {result.returncode}")
        return output or f"已通过 Glitter 将 {path.name} 发送给 {target_peer}。"
