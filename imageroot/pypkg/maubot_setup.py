#
# SPDX-License-Identifier: GPL-3.0-or-later
#

"""Settings, secrets and the generated configuration of the maubot module.

maubot rewrites its config.yaml on every start (it hashes plain admin
passwords and fills in generated secrets). The module instead keeps its own
settings in state/maubot.json and renders the complete maubot configuration
from them into state/config/maubot.yaml. That file is mounted read-only and
maubot runs with --no-update, so it never changes behind the module's back.
JSON is valid YAML, so no YAML library is needed.
"""

import contextlib
import fcntl
import json
import os
import re
import secrets

# Files below the module state directory, the working directory of actions
# and of maubot.service.
SETTINGS = "maubot.json"
CONFIG_DIR = "config"
CONFIG = os.path.join(CONFIG_DIR, "maubot.yaml")

ADMIN_USER = "admin"
# maubot listens on this port inside the container; Podman publishes it on
# 127.0.0.1:${TCP_PORT} for Traefik.
CONTAINER_PORT = 29316
UI_BASE_PATH = "/_matrix/maubot"
DATA = "/data"

# Matrix server names: a host name or IP literal with an optional port.
SERVER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9.-]+(:[0-9]{1,5})?$|^\[[0-9A-Fa-f:.]+\](:[0-9]{1,5})?$")
URL_PATTERN = re.compile(r"^https?://[^\s/?#]+(/[^\s?#]*)?$")


class SettingsError(Exception):
    def __init__(self, field, value, error):
        super().__init__(f"{field}: {error}")
        self.field = field
        self.value = value
        self.error = error


def new_secret():
    # URL-safe characters only, so the password can be typed and pasted
    # without quoting.
    return secrets.token_urlsafe(24)


def write_private_json(path, data):
    """Atomically write a JSON file readable by the module user only."""
    temporary = path + ".tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


@contextlib.contextmanager
def settings_lock(state_dir="."):
    """Serialize settings changes between concurrent tasks."""
    path = os.path.join(state_dir, SETTINGS + ".lock")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def read_settings(state_dir="."):
    try:
        with open(os.path.join(state_dir, SETTINGS), "r", encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError:
        return {}


def ensure_settings(state_dir="."):
    """Return the settings; create the admin password and the token secret
    once and keep them, also across restores and updates."""
    settings = read_settings(state_dir)
    changed = False
    if not settings.get("admin_password"):
        settings["admin_password"] = new_secret()
        changed = True
    if not settings.get("unshared_secret"):
        # Signs the login tokens of the maubot management UI and API.
        settings["unshared_secret"] = secrets.token_urlsafe(48)
        changed = True
    if not isinstance(settings.get("homeservers"), list):
        settings["homeservers"] = []
        changed = True
    path = os.path.join(state_dir, SETTINGS)
    if changed:
        write_private_json(path, settings)
    else:
        os.chmod(path, 0o600)
    return settings


def normalize_homeservers(homeservers):
    """Validate the homeserver list of a configure-module request."""
    result = []
    seen = set()
    for index, item in enumerate(homeservers):
        name = (item.get("name") or "").strip().lower()
        url = (item.get("url") or "").strip().rstrip("/")
        secret = item.get("secret") or ""
        field = f"homeservers.{index}"
        if not SERVER_NAME_PATTERN.fullmatch(name):
            raise SettingsError(f"{field}.name", name, "invalid_server_name")
        if name in seen:
            raise SettingsError(f"{field}.name", name, "duplicate_server_name")
        if not URL_PATTERN.fullmatch(url):
            raise SettingsError(f"{field}.url", url, "invalid_homeserver_url")
        seen.add(name)
        result.append({"name": name, "url": url, "secret": secret})
    return result


def apply_request(data, state_dir="."):
    """Store the maubot settings of a configure-module request.

    Fields missing from the request keep their value: clone and restore send
    the host settings only.
    """
    settings = ensure_settings(state_dir)
    if "homeservers" in data:
        settings["homeservers"] = normalize_homeservers(data["homeservers"])
    if data.get("admin_password"):
        settings["admin_password"] = data["admin_password"]
    write_private_json(os.path.join(state_dir, SETTINGS), settings)
    return settings


def public_url(host):
    return f"https://{host}" if host else ""


def ui_url(host):
    return f"https://{host}{UI_BASE_PATH}/" if host else ""


def build_config(settings, host):
    """Return the complete maubot configuration for the given settings."""
    return {
        "database": f"sqlite:{DATA}/maubot.db",
        "database_opts": {"min_size": 1, "max_size": 10},
        "crypto_database": "default",
        "crypto_db_pickle_key": "mau.crypto",
        "plugin_directories": {
            "upload": f"{DATA}/plugins",
            "load": [f"{DATA}/plugins"],
            "trash": f"{DATA}/trash",
        },
        "plugin_databases": {
            "sqlite": f"{DATA}/dbs",
            "postgres": None,
            "postgres_max_conns_per_plugin": 3,
            "postgres_opts": {},
        },
        "server": {
            "hostname": "0.0.0.0",
            "port": CONTAINER_PORT,
            # Base of the webhook URLs that plugins publish.
            "public_url": public_url(host) or "https://localhost",
            "ui_base_path": UI_BASE_PATH,
            "plugin_base_path": UI_BASE_PATH + "/plugin/",
            # The image keeps the built management UI here (docker/run.sh
            # sets the same value).
            "override_resource_path": "/opt/maubot/frontend",
            "unshared_secret": settings["unshared_secret"],
        },
        # Homeservers that the UI can log in to (and register bots on, if a
        # registration shared secret is given).
        "homeservers": {
            item["name"]: {"url": item["url"], "secret": item.get("secret") or None}
            for item in settings["homeservers"]
        },
        # maubot hashes a plain password in memory when it loads the file.
        "admins": {ADMIN_USER: settings["admin_password"]},
        "api_features": {
            "login": True,
            "plugin": True,
            "plugin_upload": True,
            "instance": True,
            "instance_database": True,
            "client": True,
            "client_proxy": True,
            "client_auth": True,
            "dev_open": True,
            "log": True,
        },
        # Log to stderr only; systemd sends it to the journal.
        "logging": {
            "version": 1,
            "formatters": {
                "normal": {"format": "[%(levelname)s@%(name)s] %(message)s"},
            },
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "normal"},
            },
            "loggers": {
                "maubot": {"level": "INFO"},
                "mau": {"level": "INFO"},
                "aiohttp": {"level": "INFO"},
            },
            "root": {"level": "INFO", "handlers": ["console"]},
        },
    }


def write_config(settings, host, state_dir="."):
    """Render the maubot configuration; return True if it changed."""
    directory = os.path.join(state_dir, CONFIG_DIR)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)
    path = os.path.join(state_dir, CONFIG)
    content = json.dumps(build_config(settings, host), indent=2) + "\n"
    try:
        with open(path, "r", encoding="utf-8") as stream:
            if stream.read() == content:
                os.chmod(path, 0o600)
                return False
    except FileNotFoundError:
        pass
    temporary = path + ".tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    return True


def configuration(settings, host, http2https, lets_encrypt):
    """Output of get-configuration."""
    return {
        "host": host,
        "http2https": http2https,
        "lets_encrypt": lets_encrypt,
        "url": ui_url(host),
        "admin_user": ADMIN_USER,
        "admin_password": settings.get("admin_password", ""),
        "homeservers": [
            {"name": item["name"], "url": item["url"], "secret": item.get("secret") or ""}
            for item in settings.get("homeservers", [])
        ],
    }
