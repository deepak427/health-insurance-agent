"""
Thin read/write layer for dynamic agent data stored as JSON files.
All tools read from here so updates via the /data API are reflected immediately.
"""
import json
import os
from typing import Any

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))

FILES = {
    "faqs": os.path.join(DATA_DIR, "faqs.json"),
    "claims": os.path.join(DATA_DIR, "claims.json"),
    "premium_config": os.path.join(DATA_DIR, "premium_config.json"),
    "response_prompt": os.path.join(DATA_DIR, "response_prompt.json"),
    "addons": os.path.join(DATA_DIR, "addons.json"),
    "vas": os.path.join(DATA_DIR, "vas.json"),
}


def load(key: str) -> Any:
    path = FILES[key]
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save(key: str, data: Any) -> None:
    path = FILES[key]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
