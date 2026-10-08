"""Limits on how much of the past the prompts carry."""

LAST_SCENE_MAX_CHARS = 1600  # about 400 tokens of the 8192-token context
LAST_SCENE_MAX_LINES = 8  # the newest spoken lines the narrator is reminded of
LAST_STORY_MAX_LENGTH = 8000  # a stored story longer than this is cut on load
DEFAULT_CHARS_PER_TOKEN = 3.5  # until a reply reports its real prompt size
BUDGET_MARGIN_TOKENS = 200  # headroom for the chat template and a miscounted ratio
