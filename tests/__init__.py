"""Test suite for the RPG engine.

Run from the project root:

    .venv\\Scripts\\python -m unittest discover -s tests -v

Everything here is offline and fast: the LLM and the embedding model are stubbed
out. The one test that exercises real FAISS is skipped unless you opt in with
RPG_TEST_EMBEDDINGS=1, because it downloads a sentence-transformer model.
"""

import os
import sys
from pathlib import Path

# config.yml may hold machine-specific settings (a LAN server, a bigger reply
# cap, the factcheck off); the tests assert the shipped defaults instead.
os.environ["RPG_CONFIG"] = os.devnull

# Allow `python -m unittest discover -s tests` from the project root without
# requiring the package to be installed.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# A fresh world draws a random seed, and the seed drives the weather; one fixed
# seed keeps every test's weather the same from run to run.
import managers.game  # noqa: E402

managers.game.new_world_seed = lambda: 1
