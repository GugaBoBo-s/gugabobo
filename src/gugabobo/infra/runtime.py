from gugabobo.config import get_settings
from gugabobo.core.agent import CoreAgent
from gugabobo.memory.store import MemoryStore


def build_agent() -> CoreAgent:
    settings = get_settings()
    store = MemoryStore(settings.db_path)
    return CoreAgent(store)

