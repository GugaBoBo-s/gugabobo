from __future__ import annotations

import tempfile
from pathlib import Path

from gugabobo.config import Settings
from gugabobo.infra.logs import get_logger
from gugabobo.infra.redaction import redact_sensitive


class VexorMemorySearch:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return self.settings.vexor_memory_enabled and bool(self.settings.vexor_api_key)

    def search(
        self,
        query: str,
        memories: list[dict[str, object]],
        limit: int,
    ) -> list[dict[str, object]]:
        if not self.configured or not query.strip() or not memories or limit <= 0:
            return memories[:limit]
        by_name = {f"memory-{item['id']}.txt": item for item in memories}
        try:
            with tempfile.TemporaryDirectory(prefix="gugabobo-vexor-") as directory:
                root = Path(directory)
                for name, item in by_name.items():
                    (root / name).write_text(str(item["content"]), encoding="utf-8")
                from vexor import VexorClient

                client = VexorClient(data_dir=root / "data", use_config=False)
                client.set_config_json(
                    {
                        "provider": self.settings.vexor_provider,
                        "model": self.settings.vexor_model,
                        "api_key": self.settings.vexor_api_key,
                        "base_url": self.settings.vexor_base_url,
                        "rerank": "hybrid",
                    }
                )
                response = client.search(
                    query,
                    path=root,
                    mode="full",
                    top=limit,
                    no_cache=True,
                    extensions=[".txt"],
                )
                ranked = [by_name[Path(hit.path).name] for hit in response.results]
                return ranked or memories[:limit]
        except Exception as error:
            safe_error = redact_sensitive(error, (self.settings.vexor_api_key,))
            get_logger().warning("Vexor memory search failed: %s", safe_error)
            return memories[:limit]
