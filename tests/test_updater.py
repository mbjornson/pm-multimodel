import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pm_multimodels import updater


class ConfigTest(unittest.TestCase):
    def test_config_defaults_when_unset(self):
        with TemporaryDirectory() as directory:
            home = Path(directory)
            self.assertEqual("true", updater.config_get(home, "update_check"))
            self.assertEqual("false", updater.config_get(home, "auto_upgrade"))
            self.assertFalse(updater.config_true(home, "auto_upgrade"))

    def test_config_set_then_get_roundtrip(self):
        with TemporaryDirectory() as directory:
            home = Path(directory)
            updater.config_set(home, "auto_upgrade", "true")
            self.assertEqual("true", updater.config_get(home, "auto_upgrade"))
            self.assertTrue(updater.config_true(home, "auto_upgrade"))
            # second key does not clobber the first
            updater.config_set(home, "update_check", "false")
            self.assertEqual("true", updater.config_get(home, "auto_upgrade"))
            self.assertEqual("false", updater.config_get(home, "update_check"))

    def test_read_version_parses_plugin_json(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            meta = root / ".claude-plugin"
            meta.mkdir()
            meta.joinpath("plugin.json").write_text(json.dumps({"version": "1.2.3"}))
            self.assertEqual("1.2.3", updater.read_version(root))

    def test_plugin_root_prefers_env(self):
        with TemporaryDirectory() as directory:
            os.environ["CLAUDE_PLUGIN_ROOT"] = directory
            try:
                self.assertEqual(Path(directory).resolve(), updater.plugin_root())
            finally:
                del os.environ["CLAUDE_PLUGIN_ROOT"]


if __name__ == "__main__":
    unittest.main()
