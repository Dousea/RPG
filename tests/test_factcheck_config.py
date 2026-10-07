"""The factcheck config defaults (Spec 10, The fact check)."""

import unittest

import config


class FactcheckConfigTests(unittest.TestCase):
    """Spec 10, The fact check."""

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
        for key, value in config._DEFAULTS["factcheck"].items():
            self.assertEqual(getattr(config.factcheck, key), value)


if __name__ == "__main__":
    unittest.main()
