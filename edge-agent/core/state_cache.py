import json
import os
from pathlib import Path


class StateCache:
    def __init__(self, cache_file="cache.json"):
        self.cache_file = Path(cache_file)

    def save(self, data):
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with self.cache_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load(self):
        try:
            if not self.cache_file.exists():
                return []
            with self.cache_file.open("r", encoding="utf-8") as f:
                return json.load(f) or []
        except Exception:
            return []

    def save_stream_state(self, streams_state):
        try:
            state_file = self.cache_file.parent / "streams_state.json"
            with state_file.open("w", encoding="utf-8") as f:
                json.dump(streams_state, f, ensure_ascii=False)
        except Exception:
            pass

    def load_stream_state(self):
        try:
            state_file = self.cache_file.parent / "streams_state.json"
            if not state_file.exists():
                return {}
            with state_file.open("r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}
