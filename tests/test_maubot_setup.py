#
# SPDX-License-Identifier: GPL-3.0-or-later
#

import json
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "imageroot" / "pypkg"))

import maubot_backup  # noqa: E402
import maubot_setup  # noqa: E402


def mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_secrets_are_generated_once_and_private(self):
        first = maubot_setup.ensure_settings(self.state)
        self.assertTrue(first["admin_password"])
        self.assertTrue(first["unshared_secret"])
        self.assertEqual(first["homeservers"], [])
        second = maubot_setup.ensure_settings(self.state)
        self.assertEqual(first, second)
        self.assertEqual(mode(os.path.join(self.state, maubot_setup.SETTINGS)), 0o600)

    def test_request_without_maubot_fields_keeps_settings(self):
        maubot_setup.apply_request({
            "host": "bot.example.org",
            "homeservers": [{"name": "example.org", "url": "https://matrix.example.org/"}],
            "admin_password": "chosen",
        }, self.state)
        # Clone and restore send the host settings only.
        settings = maubot_setup.apply_request({"host": "bot.example.org"}, self.state)
        self.assertEqual(settings["admin_password"], "chosen")
        self.assertEqual(settings["homeservers"], [
            {"name": "example.org", "url": "https://matrix.example.org", "secret": ""},
        ])

    def test_empty_admin_password_keeps_the_current_one(self):
        before = maubot_setup.ensure_settings(self.state)["admin_password"]
        settings = maubot_setup.apply_request({"host": "h.example.org", "admin_password": ""}, self.state)
        self.assertEqual(settings["admin_password"], before)

    def test_homeservers_can_be_cleared(self):
        maubot_setup.apply_request({"homeservers": [{"name": "a.org", "url": "https://a.org"}]}, self.state)
        settings = maubot_setup.apply_request({"homeservers": []}, self.state)
        self.assertEqual(settings["homeservers"], [])

    def test_homeserver_validation(self):
        for item, field, error in [
            ({"name": "bad name", "url": "https://a.org"}, "homeservers.0.name", "invalid_server_name"),
            ({"name": "a.org", "url": "ftp://a.org"}, "homeservers.0.url", "invalid_homeserver_url"),
            ({"name": "a.org", "url": "https://"}, "homeservers.0.url", "invalid_homeserver_url"),
        ]:
            with self.subTest(item=item):
                with self.assertRaises(maubot_setup.SettingsError) as context:
                    maubot_setup.normalize_homeservers([item])
                self.assertEqual(context.exception.field, field)
                self.assertEqual(context.exception.error, error)
        with self.assertRaises(maubot_setup.SettingsError) as context:
            maubot_setup.normalize_homeservers([
                {"name": "a.org", "url": "https://a.org"},
                {"name": "A.org", "url": "https://b.org"},
            ])
        self.assertEqual(context.exception.error, "duplicate_server_name")
        self.assertEqual(
            maubot_setup.normalize_homeservers([
                {"name": "a.org:8448", "url": "http://10.0.0.1:8008", "secret": "s"},
                {"name": "[::1]", "url": "https://matrix.b.org/base/"},
            ]),
            [
                {"name": "a.org:8448", "url": "http://10.0.0.1:8008", "secret": "s"},
                {"name": "[::1]", "url": "https://matrix.b.org/base", "secret": ""},
            ],
        )

    def test_rejected_request_does_not_change_settings(self):
        before = maubot_setup.apply_request({"homeservers": [{"name": "a.org", "url": "https://a.org"}]}, self.state)
        with self.assertRaises(maubot_setup.SettingsError):
            maubot_setup.apply_request({
                "admin_password": "other",
                "homeservers": [{"name": "", "url": "https://a.org"}],
            }, self.state)
        self.assertEqual(maubot_setup.read_settings(self.state), before)


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = self.tmp.name
        self.settings = maubot_setup.apply_request({
            "homeservers": [
                {"name": "example.org", "url": "https://matrix.example.org", "secret": ""},
                {"name": "other.org", "url": "https://other.org", "secret": "reg"},
            ],
            "admin_password": "pw",
        }, self.state)

    def tearDown(self):
        self.tmp.cleanup()

    def test_rendered_config(self):
        self.assertTrue(maubot_setup.write_config(self.settings, "bot.example.org", self.state))
        path = os.path.join(self.state, maubot_setup.CONFIG)
        self.assertEqual(mode(path), 0o600)
        self.assertEqual(mode(os.path.dirname(path)), 0o700)
        with open(path, encoding="utf-8") as stream:
            config = json.load(stream)
        self.assertEqual(config["server"]["public_url"], "https://bot.example.org")
        self.assertEqual(config["server"]["port"], maubot_setup.CONTAINER_PORT)
        self.assertEqual(config["server"]["unshared_secret"], self.settings["unshared_secret"])
        self.assertEqual(config["admins"], {"admin": "pw"})
        self.assertEqual(config["homeservers"], {
            "example.org": {"url": "https://matrix.example.org", "secret": None},
            "other.org": {"url": "https://other.org", "secret": "reg"},
        })
        self.assertEqual(config["database"], "sqlite:/data/maubot.db")
        self.assertEqual(config["plugin_databases"]["sqlite"], "/data/dbs")
        self.assertEqual(config["logging"]["root"]["handlers"], ["console"])

    def test_config_has_every_key_of_the_maubot_example_config(self):
        # maubot loads the file with --no-update, so a key missing here would
        # be missing at runtime. Keys of the example config of maubot v0.6.0
        # (maubot/example-config.yaml) that maubot reads:
        config = maubot_setup.build_config(self.settings, "bot.example.org")
        for key in [
            "database", "database_opts", "crypto_database", "crypto_db_pickle_key",
            "plugin_directories.upload", "plugin_directories.load", "plugin_directories.trash",
            "plugin_databases.sqlite", "plugin_databases.postgres",
            "plugin_databases.postgres_max_conns_per_plugin", "plugin_databases.postgres_opts",
            "server.hostname", "server.port", "server.public_url", "server.ui_base_path",
            "server.plugin_base_path", "server.override_resource_path", "server.unshared_secret",
            "homeservers", "admins", "api_features.login", "api_features.plugin",
            "api_features.plugin_upload", "api_features.instance", "api_features.instance_database",
            "api_features.client", "api_features.client_proxy", "api_features.client_auth",
            "api_features.dev_open", "api_features.log", "logging",
        ]:
            with self.subTest(key=key):
                node = config
                for part in key.split("."):
                    self.assertIn(part, node)
                    node = node[part]

    def test_unchanged_config_is_not_rewritten(self):
        maubot_setup.write_config(self.settings, "bot.example.org", self.state)
        self.assertFalse(maubot_setup.write_config(self.settings, "bot.example.org", self.state))
        self.assertTrue(maubot_setup.write_config(self.settings, "new.example.org", self.state))

    def test_get_configuration_output(self):
        output = maubot_setup.configuration(self.settings, "bot.example.org", True, False)
        self.assertEqual(output["url"], "https://bot.example.org/_matrix/maubot/")
        self.assertEqual(output["admin_user"], "admin")
        self.assertEqual(output["admin_password"], "pw")
        self.assertEqual(output["homeservers"][1]["secret"], "reg")
        empty = maubot_setup.configuration({}, "", False, False)
        self.assertEqual(empty["url"], "")
        self.assertEqual(empty["admin_password"], "")
        self.assertEqual(empty["homeservers"], [])

    def test_output_matches_schema_required_keys(self):
        schema_path = ROOT / "imageroot" / "actions" / "get-configuration" / "validate-output.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        output = maubot_setup.configuration(self.settings, "bot.example.org", True, True)
        self.assertEqual(set(schema["required"]), set(output))


class BackupTest(unittest.TestCase):
    """Run the snapshot scripts with the local Python on a fake data volume."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        (self.data / "dbs").mkdir()
        (self.data / "plugins").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, script):
        subprocess.run([sys.executable, "-c", script, str(self.data)], check=True,
                       stderr=subprocess.DEVNULL)

    def make_db(self, path, value):
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
        connection.execute("DELETE FROM t")
        connection.execute("INSERT INTO t VALUES (?)", (value,))
        connection.commit()
        return connection

    def read_db(self, path):
        connection = sqlite3.connect(path)
        try:
            return connection.execute("SELECT v FROM t").fetchone()[0]
        finally:
            connection.close()

    def test_snapshot_and_restore(self):
        # Keep the connections open, so the data is still in the WAL files.
        main = self.make_db(self.data / "maubot.db", "main")
        plugin = self.make_db(self.data / "dbs" / "instance.db", "plugin")
        self.run_script(maubot_backup.SNAPSHOT_SCRIPT)
        snapshot = self.data / maubot_backup.SNAPSHOT
        self.assertEqual(self.read_db(snapshot / "maubot.db"), "main")
        self.assertEqual(self.read_db(snapshot / "dbs" / "instance.db"), "plugin")
        self.assertFalse((snapshot / "maubot.db-wal").exists())
        self.assertFalse((self.data / (maubot_backup.SNAPSHOT + ".tmp")).exists())

        # Changes after the backup are replaced by the snapshot on restore,
        # including what is only in the WAL file.
        self.make_db(self.data / "maubot.db", "changed").close()
        main.close()
        plugin.close()
        later = sqlite3.connect(self.data / "maubot.db")
        later.execute("PRAGMA wal_autocheckpoint=0")
        later.execute("UPDATE t SET v = 'in-wal'")
        later.commit()
        self.run_script(maubot_backup.RESTORE_SCRIPT)
        later.close()
        self.assertFalse(snapshot.exists())
        self.assertEqual(self.read_db(self.data / "maubot.db"), "main")
        self.assertEqual(self.read_db(self.data / "dbs" / "instance.db"), "plugin")
        self.assertTrue((self.data / "trash").is_dir())

    def test_snapshot_of_empty_volume(self):
        self.run_script(maubot_backup.SNAPSHOT_SCRIPT)
        self.assertTrue((self.data / maubot_backup.SNAPSHOT / "dbs").is_dir())
        self.run_script(maubot_backup.RESTORE_SCRIPT)
        self.assertFalse((self.data / "maubot.db").exists())

    def test_restore_without_snapshot_fails(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_script(maubot_backup.RESTORE_SCRIPT)

    def test_cleanup(self):
        self.run_script(maubot_backup.SNAPSHOT_SCRIPT)
        self.run_script(maubot_backup.CLEANUP_SCRIPT)
        self.assertFalse((self.data / maubot_backup.SNAPSHOT).exists())

    def test_podman_command(self):
        calls = []
        maubot_backup.make_snapshot(image="img:tag", runner=lambda args, check: calls.append(args))
        args = calls[0]
        self.assertEqual(args[:4], ("podman", "run", "--rm", "--network=none"))
        # A private SELinux label would lock the running maubot out
        self.assertIn("maubot-data:/data:z", args)
        self.assertEqual(args[-4:], ("img:tag", "-c", maubot_backup.SNAPSHOT_SCRIPT, "/data"))


class UnitFileTest(unittest.TestCase):
    def test_service_uses_rendered_config(self):
        unit = (ROOT / "imageroot" / "systemd" / "user" / "maubot.service").read_text(encoding="utf-8")
        self.assertIn("--volume %E/state/config:/etc/maubot:ro,Z", unit)
        self.assertIn("--volume maubot-data:/data:z", unit)
        self.assertIn(f"127.0.0.1:${{TCP_PORT}}:{maubot_setup.CONTAINER_PORT}", unit)
        self.assertIn("-c /etc/maubot/" + os.path.basename(maubot_setup.CONFIG) + " --no-update", unit)


if __name__ == "__main__":
    unittest.main()
