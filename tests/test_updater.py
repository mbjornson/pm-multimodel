import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

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


class CheckTest(unittest.TestCase):
    def _root_with_version(self, directory: str, version: str) -> Path:
        root = Path(directory)
        meta = root / ".claude-plugin"
        meta.mkdir(exist_ok=True)
        meta.joinpath("plugin.json").write_text(json.dumps({"version": version}))
        return root

    def test_reports_upgrade_when_behind(self):
        with TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            home.mkdir()
            root = self._root_with_version(directory, "0.1.0")
            with mock.patch.object(updater, "git_fetch", return_value=True), \
                 mock.patch.object(updater, "commits_behind", return_value=3), \
                 mock.patch.object(updater, "remote_version", return_value="0.2.0"):
                line = updater.check(root=root, home=home, now=1000.0)
            self.assertEqual("UPGRADE_AVAILABLE 0.1.0 0.2.0", line)

    def test_silent_when_up_to_date(self):
        with TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            home.mkdir()
            root = self._root_with_version(directory, "0.1.0")
            with mock.patch.object(updater, "git_fetch", return_value=True), \
                 mock.patch.object(updater, "commits_behind", return_value=0):
                self.assertEqual("", updater.check(root=root, home=home, now=1000.0))

    def test_silent_when_offline(self):
        with TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            home.mkdir()
            root = self._root_with_version(directory, "0.1.0")
            with mock.patch.object(updater, "git_fetch", return_value=False):
                self.assertEqual("", updater.check(root=root, home=home, now=1000.0))
            self.assertFalse((home / "last-update-check").is_file())

    def test_remote_version_falls_back_on_bad_json(self):
        with TemporaryDirectory() as directory:
            root = self._root_with_version(directory, "0.1.0")
            # Mock _git to return malformed JSON
            mock_result = mock.MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "not json{"
            with mock.patch.object(updater, "_git", return_value=mock_result):
                self.assertEqual("0.1.0", updater.remote_version(root))

    def test_suppressed_when_update_check_disabled(self):
        with TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            home.mkdir()
            root = self._root_with_version(directory, "0.1.0")
            updater.config_set(home, "update_check", "false")
            with mock.patch.object(updater, "git_fetch") as fetch:
                self.assertEqual("", updater.check(root=root, home=home, now=1000.0))
                fetch.assert_not_called()

    def test_cache_gates_network_but_force_bypasses(self):
        with TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            home.mkdir()
            root = self._root_with_version(directory, "0.1.0")
            updater.touch_check(home, now=1000.0)
            with mock.patch.object(updater, "git_fetch") as fetch:
                self.assertEqual("", updater.check(root=root, home=home, now=1001.0))
                fetch.assert_not_called()
            with mock.patch.object(updater, "git_fetch", return_value=True), \
                 mock.patch.object(updater, "commits_behind", return_value=1), \
                 mock.patch.object(updater, "remote_version", return_value="0.2.0"):
                line = updater.check(root=root, home=home, force=True, now=1001.0)
            self.assertEqual("UPGRADE_AVAILABLE 0.1.0 0.2.0", line)

    def test_active_snooze_suppresses_but_force_overrides(self):
        with TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            home.mkdir()
            root = self._root_with_version(directory, "0.1.0")
            updater.snooze(home, "0.2.0", now=0.0)  # 24h window
            with mock.patch.object(updater, "git_fetch", return_value=True), \
                 mock.patch.object(updater, "commits_behind", return_value=1), \
                 mock.patch.object(updater, "remote_version", return_value="0.2.0"):
                self.assertEqual("", updater.check(root=root, home=home, now=100.0))
                forced = updater.check(root=root, home=home, force=True, now=100.0)
            self.assertEqual("UPGRADE_AVAILABLE 0.1.0 0.2.0", forced)

    def test_just_upgraded_marker_emitted_then_cleared(self):
        with TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            home.mkdir()
            root = self._root_with_version(directory, "0.2.0")
            (home / "just-upgraded-from").write_text("0.1.0\n")
            self.assertEqual(
                "JUST_UPGRADED 0.1.0 0.2.0", updater.check(root=root, home=home, now=1.0)
            )
            self.assertFalse((home / "just-upgraded-from").is_file())
            with mock.patch.object(updater, "git_fetch", return_value=True), \
                 mock.patch.object(updater, "commits_behind", return_value=0):
                self.assertEqual("", updater.check(root=root, home=home, now=2.0))


class UpgradeTest(unittest.TestCase):
    def _root_with_version(self, directory: str, version: str) -> Path:
        root = Path(directory)
        meta = root / ".claude-plugin"
        meta.mkdir(exist_ok=True)
        meta.joinpath("plugin.json").write_text(json.dumps({"version": version}))
        return root

    def test_successful_upgrade_writes_marker_and_clears_caches(self):
        with TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            home.mkdir()
            root = self._root_with_version(directory, "0.1.0")
            (home / "last-update-check").write_text("123\n")
            (home / "update-snoozed").write_text("0.2.0 1 0\n")

            fake_engine = mock.Mock()
            fake_engine.sync_global.return_value = mock.Mock(conflicts=[])
            fake_engine.registered_repos.return_value = []

            with mock.patch.object(updater, "_git") as git, \
                 mock.patch.object(updater, "git_fetch", return_value=True), \
                 mock.patch.object(updater, "read_version", side_effect=["0.1.0", "0.2.0"]), \
                 mock.patch.object(updater, "SyncEngine", return_value=fake_engine), \
                 mock.patch("pm_multimodels.updater.shutil.which", return_value=None):
                git.return_value = mock.Mock(returncode=0, stdout="")
                code, message = updater.upgrade(root=root, home=home, now=999.0)

            self.assertEqual(0, code)
            self.assertEqual("0.1.0", (home / "just-upgraded-from").read_text().strip())
            self.assertFalse((home / "last-update-check").is_file())
            self.assertFalse((home / "update-snoozed").is_file())
            self.assertIn("0.2.0", message)

    def test_failed_fetch_restores_and_does_not_mark(self):
        with TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            home.mkdir()
            root = self._root_with_version(directory, "0.1.0")
            with mock.patch.object(updater, "_git") as git, \
                 mock.patch.object(updater, "git_fetch", return_value=False):
                git.return_value = mock.Mock(returncode=0, stdout="")
                code, message = updater.upgrade(root=root, home=home, now=999.0)
            self.assertEqual(1, code)
            self.assertFalse((home / "just-upgraded-from").is_file())
            self.assertIn("restored", message.lower())


if __name__ == "__main__":
    unittest.main()
