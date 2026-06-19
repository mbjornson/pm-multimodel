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


class SnoozeTest(unittest.TestCase):
    def test_snooze_escalates_and_caps(self):
        with TemporaryDirectory() as directory:
            home = Path(directory)
            self.assertEqual("24h", updater.snooze(home, "1.0.0", now=1000.0))
            self.assertEqual("48h", updater.snooze(home, "1.0.0", now=2000.0))
            self.assertEqual("1 week", updater.snooze(home, "1.0.0", now=3000.0))
            self.assertEqual("1 week", updater.snooze(home, "1.0.0", now=4000.0))

    def test_new_version_resets_snooze_level(self):
        with TemporaryDirectory() as directory:
            home = Path(directory)
            updater.snooze(home, "1.0.0", now=1000.0)  # level 1
            self.assertEqual("24h", updater.snooze(home, "2.0.0", now=1000.0))

    def test_snooze_active_within_window_only(self):
        with TemporaryDirectory() as directory:
            home = Path(directory)
            updater.snooze(home, "1.0.0", now=0.0)  # 24h = 86400s
            self.assertTrue(updater.snooze_active(home, "1.0.0", now=80000.0))
            self.assertFalse(updater.snooze_active(home, "1.0.0", now=90000.0))
            # snooze for a different remote version never applies
            self.assertFalse(updater.snooze_active(home, "2.0.0", now=80000.0))

    def test_snooze_degradation_on_malformed_file(self):
        with TemporaryDirectory() as directory:
            home = Path(directory)
            # Write a file with only two fields instead of three
            (home / "update-snoozed").write_text("1.0.0 1\n")
            # snooze_active should return False (not crash)
            self.assertFalse(updater.snooze_active(home, "1.0.0", now=1000.0))


class CacheTest(unittest.TestCase):
    def test_cache_freshness(self):
        with TemporaryDirectory() as directory:
            home = Path(directory)
            self.assertFalse(updater.cache_fresh(home, now=0.0))
            updater.touch_check(home, now=1000.0)
            self.assertTrue(updater.cache_fresh(home, now=1000.0 + 10))
            self.assertFalse(updater.cache_fresh(home, now=1000.0 + updater.CHECK_TTL + 1))

    def test_cache_degradation_on_unparseable_file(self):
        with TemporaryDirectory() as directory:
            home = Path(directory)
            # Write garbage content that can't be parsed as float
            (home / "last-update-check").write_text("not-a-number\n")
            # cache_fresh should return False (not crash)
            self.assertFalse(updater.cache_fresh(home, now=1000.0))


if __name__ == "__main__":
    unittest.main()
