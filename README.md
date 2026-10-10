# ns8-maubot

NethServer 8 module for [maubot](https://github.com/maubot/maubot), a
plugin-based [Matrix](https://matrix.org/) bot system with a web management
UI.

The module runs maubot `v0.6.0` as a rootless container from
`ghcr.io/platypuschan/maubot-runtime`: the official image
(`dock.mau.dev/maubot/maubot`, pinned by digest) with current Alpine and
Python security fixes, see [Runtime image](#runtime-image). It adds:

- a Traefik route for the management UI, its API and the plugin web
  endpoints, with optional Let's Encrypt certificate;
- the maubot admin user `admin` with a generated password, shown on the
  **Settings** page and changeable there;
- a list of Matrix homeservers that the management UI can log bot accounts
  in to (optionally with a registration shared secret);
- NS8 backup and restore of the maubot database, the plugin databases, the
  uploaded plugins and the module settings.

maubot uses its built-in SQLite database; plugin instances get their own
SQLite databases.

## Install

Install a fixed version, so that the Software Center offers later updates:

```
add-module ghcr.io/platypuschan/maubot:0.1.0 1
```

The output of the command returns the instance name, for example `maubot1`.

## Configure

Open the module in cluster-admin and set the host name on the **Settings**
page. The management UI is then at `https://<host>/_matrix/maubot/`; the
Settings page links to it and shows the admin user and password.

The same configuration from the command line:

```
api-cli run module/maubot1/configure-module --data '{"host": "maubot.example.org", "http2https": true, "lets_encrypt": true}'
api-cli run module/maubot1/get-configuration
```

Optional fields of `configure-module` (omitted fields keep their value):

- `homeservers`: list of `{"name": "<server name>", "url": "<client API URL>", "secret": "<registration shared secret or empty>"}`.
  The server name is the part after `:` in Matrix user IDs. Without an entry
  for a homeserver, bots on it can still be added in the management UI with
  an access token.
- `admin_password`: new password for the maubot user `admin`; empty keeps
  the current one.

```
api-cli run module/maubot1/configure-module --data '{"host": "maubot.example.org", "http2https": true, "lets_encrypt": true, "homeservers": [{"name": "example.org", "url": "https://matrix.example.org", "secret": ""}]}'
```

maubot reads its configuration only at start, so `configure-module` restarts
it when the maubot configuration changed (host, homeservers, admin password).
Saving unchanged settings leaves the bots running.

## Use

In the management UI:

1. **Plugins**: upload plugin files (`.mbp`). A list of plugins is at
   [plugins.mau.bot](https://plugins.mau.bot/).
2. **Clients**: add the Matrix account of a bot, by password login on a
   configured homeserver or with an access token.
3. **Instances**: combine a plugin and a client into a running bot and edit
   its plugin configuration.

The `mbc` command-line tool of maubot can log in to
`https://<host>` with the same admin user.

Plugins with web endpoints (webhooks) publish them below
`https://<host>/_matrix/maubot/plugin/<instance id>/`.

## How the module runs maubot

maubot normally writes its `config.yaml` itself on every start. The module
instead keeps its settings in `state/maubot.json` (admin password, the secret
that signs management UI logins, homeservers) and renders the complete maubot
configuration into `state/config/maubot.yaml`. That file is mounted
read-only and maubot runs with `--no-update`, so the configuration only
changes through the module. maubot hashes the admin password in memory.

The image entrypoint is not used; maubot runs as root of the rootless
container, which is the module user on the host. Logs go to the journal (no
log files).

Files:

| Path | Content |
| --- | --- |
| `state/maubot.json` (0600) | module settings and secrets |
| `state/config/maubot.yaml` (0600) | generated maubot configuration |
| volume `maubot-data` | `maubot.db`, `dbs/` (plugin instance databases), `plugins/` (uploaded `.mbp` files), `trash/` |

## Runtime image

The maubot project rebuilds its image only for a new maubot release, so its
Alpine packages (OpenSSL, Python, expat, the image libraries used by Pillow)
and pip-installed HTTP libraries age in between. maubot uses them at runtime:
TLS to homeservers and plugins that fetch feeds, web pages or images.
[`runtime/Containerfile`](runtime/Containerfile) therefore installs the patch
releases on top of the pinned official image (`apk upgrade`, urllib3,
requests, pytest); maubot itself is unchanged.

The image tag is the Git tree hash of `runtime/`
([`.github/scripts/runtime-image`](.github/scripts/runtime-image)). The
`runtime` job of `Publish images` builds and pushes each tag once, and the
module image references it in `org.nethserver.images` (NS8 passes it as
`MAUBOT_RUNTIME_IMAGE`). To pick up newer fixes, change `REFRESHED` in the
Containerfile and raise `CATALOG_VERSION`; a new maubot release means a new
`FROM` line.

## Backup and restore

Before every backup, `module-dump-state` takes consistent copies of
`maubot.db` and `dbs/*.db` with the SQLite backup API into
`maubot-data/.backup-snapshot`; maubot keeps running. Restic saves the
snapshot, `maubot-data/plugins` and `state/maubot.json`. On restore, the
snapshot is moved back into place before maubot starts. The `trash/`
directory (replaced plugin files) is not backed up.

End-to-end encryption keys of bot clients are stored in `maubot.db` and are
part of the backup.

## Uninstall

```
remove-module --no-preserve maubot1
```

## Testing

Unit tests:

```
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

The QEMU tests in `tests/maubot.robot` install the module on Rocky Linux 9
and Debian 13 (`install` scenario) and update it from the last published
release (`update` scenario). They check the Traefik route, admin login,
plugin upload, homeserver settings, password change, backup snapshot and the
module UI. They run in GitHub Actions (`Publish images`); to run them by
hand:

```
./test-module-install.sh <NODE_ADDR> ghcr.io/platypuschan/maubot:latest
./test-module-update.sh <NODE_ADDR> ghcr.io/platypuschan/maubot:latest
```

## Release

`CATALOG_VERSION` is the version published to the module catalog. Raise it
in every change that alters the module image (`imageroot`, `ui`, `runtime`,
`build-images.sh`); the Validate workflow checks this. After a merge to
`main`, `Publish images` builds and tests the image, and
`Publish tested catalog version` tags the tested image with that version.

## Credits

maubot is developed by Tulir Asokan and contributors under the AGPL-3.0.
The module logo is the maubot icon from the maubot repository
(`maubot/management/frontend/public/favicon.png`).
