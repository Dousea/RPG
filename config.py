"""Loads config.yml once and exposes it as a nested, attribute-accessible object.

Every value has a hardcoded fallback here, so a missing file or a missing key
degrades to the old built-in defaults rather than crashing.
"""

import logging
import os
from typing import Any

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yml")

_DEFAULTS: dict[str, Any] = {
    "llm": {
        "base_url": "http://localhost:1234/v1/chat/completions",
        "model_name": "local-model",
        "request_timeout": 300,
        # Low temperature: the parser proposes actions, not prose, so it
        # should be as consistent/predictable as the local model allows.
        "parser_temperature": 0.2,
        "narrator_temperature": 0.7,
        "summarizer_temperature": 0.5,
        "context_tokens": 8192,
        "narrator_max_tokens": 800,
        "parser_max_tokens": 400,
        "summarizer_max_tokens": 300,
    },
    "memory": {
        "embedding_model_name": "all-MiniLM-L6-v2",
        "embedding_dimension": 384,
        "default_recall": 2,
    },
    "factcheck": {
        "enabled": True,
        "model_name": "togethercomputer_tev1-4b-experimental",
        "conflict_threshold": 0.9,
        "request_timeout": 30,
    },
    "game": {
        "max_recent_events": 5,
        "summary_threshold": 10,
    },
    "persistence": {
        "game_data_dir": "gamedata",
        "save_file_name": "engine_state.json",
    },
    "server": {
        "host": "127.0.0.1",
        "port": 5000,
        "debug": True,
    },
}


class ConfigSection:
    """Read-only attribute access over a dict of config values."""

    def __init__(self, values: dict[str, Any]):
        self._values = values

    def __getattr__(self, name: str) -> Any:
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(name) from None


def _merge(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load() -> dict[str, Any]:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning(f"Could not read {CONFIG_PATH}: {exc}. Using defaults.")
        data = {}
    return _merge(_DEFAULTS, data)


_raw = _load()

llm = ConfigSection(_raw["llm"])
memory = ConfigSection(_raw["memory"])
factcheck = ConfigSection(_raw["factcheck"])
game = ConfigSection(_raw["game"])
persistence = ConfigSection(_raw["persistence"])
server = ConfigSection(_raw["server"])
