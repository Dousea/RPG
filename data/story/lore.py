"""Where the lorebook lives and how big its parts may be (world-lore)."""

from pathlib import Path

LOREBOOK_PATH = Path(__file__).with_name("lorebook.json")  # world-lore
WORLD_MAX_CHARS = 1800  # world-lore: characters of [WORLD] lines, about 500 tokens
SYSTEM_MAX_CHARS = 1200  # world-lore: characters, total content of the system entries
ENTRY_MAX_CHARS = 300  # world-lore: characters per entry's content
STICKY_MAX_TURNS = 10  # world-lore: turns, the largest sticky
LORE_SEMANTIC_MAX = 2  # world-lore: entries a turn's semantic retrieval may add
LORE_SEMANTIC_MIN_SCORE = 0.35  # world-lore: cosine similarity, tuned in playtest
