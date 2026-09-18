"""Test suite for the RPG engine.

Run from the project root:

    .venv\\Scripts\\python -m unittest discover -s tests -v

Everything here is offline and fast: the LLM and the embedding model are stubbed
out. The one test that exercises real FAISS is skipped unless you opt in with
RPG_TEST_EMBEDDINGS=1, because it downloads a sentence-transformer model.
"""

import sys
from pathlib import Path

# Allow `python -m unittest discover -s tests` from the project root without
# requiring the package to be installed.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
