"""A tiny on-disk JSON cache for provider responses."""

import hashlib
import json
from pathlib import Path


class JsonCache:
    """Successful responses only. Keys are hashed, so queries can contain anything."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def get(self, key: str) -> object | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def set(self, key: str, value: object) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False), encoding="utf-8"
        )
        temporary.replace(path)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return self.directory / f"{digest}.json"
