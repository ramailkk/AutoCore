import os

import yaml

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
_cache: dict | None = None


def load_config() -> dict:
    global _cache
    if _cache is None:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            _cache = yaml.safe_load(f)
    return _cache
