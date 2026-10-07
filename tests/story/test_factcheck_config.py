"""The factcheck config defaults (llm-contract: The fact check)."""

import os
import subprocess
import unittest

import yaml

import config


def committed_config() -> dict:
    """config.yml as committed at HEAD; a local edit to the file doesn't count."""
    try:
        text = subprocess.run(
            ["git", "show", "HEAD:config.yml"],
            cwd=os.path.dirname(config.__file__),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise unittest.SkipTest(f"no committed config.yml to read: {exc}") from exc
    return yaml.safe_load(text) or {}


class FactcheckConfigTests(unittest.TestCase):
    """llm-contract: The fact check."""

    def test_the_defaults(self):
        self.assertEqual(
            config._DEFAULTS["factcheck"],
            {
                "enabled": True,
                "model_name": "togethercomputer_tev1-4b-experimental",
                "conflict_threshold": 0.9,
                "request_timeout": 30,
            },
        )

    def test_config_yml_agrees_with_the_defaults(self):
        committed = committed_config().get("factcheck", {})
        for key, value in config._DEFAULTS["factcheck"].items():
            self.assertEqual(committed.get(key), value, key)


if __name__ == "__main__":
    unittest.main()
