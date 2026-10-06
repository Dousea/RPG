"""Save and load a GameManager as a JSON file.

A save whose version is not `SCHEMA_VERSION` is discarded and a new game is
started, rather than being loaded half-understood.
"""

import json
import logging
import os
from typing import Any

import config
from adapters.save.codec import SCHEMA_VERSION, from_dict, to_dict
from managers.game import GameManager

logger = logging.getLogger(__name__)

GAME_DATA_DIR = config.persistence.game_data_dir
SAVE_FILE = os.path.join(GAME_DATA_DIR, config.persistence.save_file_name)


def save(manager: GameManager, path: str | None = None) -> None:
    # Resolved at call time, not bound as a default, so SAVE_FILE stays
    # overridable (tests, alternate save slots).
    path = path or SAVE_FILE
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    # Write to a temp file then replace, so a crash mid-write cannot leave a
    # truncated save behind.
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(to_dict(manager), handle, indent=2)
    os.replace(temp_path, path)


def from_saved_data(data: dict[str, Any]) -> GameManager | None:
    """Validate parsed save JSON and build a GameManager from it, or None.

    Shared by `load` (reads the autosave off disk) and the `/save/import`
    route (reads a file the player uploaded) -- both need the same schema
    check and the same "don't half-load a corrupt save" guard.
    """
    # AttributeError is caught with the rest because a hand-edited field of
    # the wrong type (`None.strip()`) raises it.
    try:
        version = data.get("version")
        if version != SCHEMA_VERSION:
            logger.warning(f"Save schema v{version} != v{SCHEMA_VERSION}; rejecting.")
            return None
        return from_dict(data)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        logger.warning(f"Corrupt save: {exc}.")
        return None


def load(path: str | None = None) -> GameManager | None:
    """Load a saved game, or return None if there is no usable save."""
    path = path or SAVE_FILE
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"Could not read save at {path}: {exc}")
        return None

    return from_saved_data(data)


def delete(path: str | None = None) -> None:
    path = path or SAVE_FILE
    if os.path.exists(path):
        os.remove(path)
