#
# SPDX-License-Identifier: GPL-3.0-or-later
#

"""Consistent SQLite snapshots of the maubot data for the NS8 module backup.

maubot keeps its own database and one SQLite database per plugin instance
in WAL mode. Copying those files while maubot writes can give a broken
copy, so module-dump-state takes an online backup with the SQLite backup API
into /data/.backup-snapshot, which Restic then uploads. maubot keeps running.

The scripts run in a short-lived container of the maubot image on the data
volume: it has Python with sqlite3, and it sees the volume with the same
owners as maubot itself, whether maubot is running or not. Both containers
mount the volume with the shared SELinux label (:z); a private label (:Z)
from this container would lock the running maubot out of its data.
"""

import os
import subprocess

DATA_VOLUME = "maubot-data"
SNAPSHOT = ".backup-snapshot"

SNAPSHOT_SCRIPT = r"""
import os, shutil, sqlite3, sys

data = sys.argv[1]
snapshot = os.path.join(data, ".backup-snapshot")
staging = snapshot + ".tmp"
shutil.rmtree(staging, ignore_errors=True)
os.makedirs(os.path.join(staging, "dbs"))

def copy(source, target):
    # Open the source read-only; a missing file must not be created.
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    with dst:
        src.backup(dst)
    dst.close()
    src.close()

count = 0
if os.path.exists(os.path.join(data, "maubot.db")):
    copy(os.path.join(data, "maubot.db"), os.path.join(staging, "maubot.db"))
    count += 1
dbs = os.path.join(data, "dbs")
if os.path.isdir(dbs):
    for name in sorted(os.listdir(dbs)):
        if name.endswith(".db"):
            copy(os.path.join(dbs, name), os.path.join(staging, "dbs", name))
            count += 1
shutil.rmtree(snapshot, ignore_errors=True)
os.rename(staging, snapshot)
print(f"maubot backup snapshot: {count} SQLite databases", file=sys.stderr)
"""

RESTORE_SCRIPT = r"""
import os, shutil, sys

data = sys.argv[1]
snapshot = os.path.join(data, ".backup-snapshot")
if not os.path.isdir(snapshot):
    print("The backup has no maubot data snapshot", file=sys.stderr)
    sys.exit(1)

def place(source, target):
    # Stale WAL or shared-memory files would be replayed onto the restored
    # database, so remove them together with the old file.
    for suffix in ("", "-wal", "-shm", "-journal"):
        try:
            os.remove(target + suffix)
        except FileNotFoundError:
            pass
    shutil.move(source, target)

if os.path.exists(os.path.join(snapshot, "maubot.db")):
    place(os.path.join(snapshot, "maubot.db"), os.path.join(data, "maubot.db"))
os.makedirs(os.path.join(data, "dbs"), exist_ok=True)
for name in sorted(os.listdir(os.path.join(snapshot, "dbs"))):
    place(os.path.join(snapshot, "dbs", name), os.path.join(data, "dbs", name))
for name in ("plugins", "trash"):
    os.makedirs(os.path.join(data, name), exist_ok=True)
shutil.rmtree(snapshot)
"""

CLEANUP_SCRIPT = r"""
import os, shutil, sys
data = sys.argv[1]
shutil.rmtree(os.path.join(data, ".backup-snapshot"), ignore_errors=True)
shutil.rmtree(os.path.join(data, ".backup-snapshot.tmp"), ignore_errors=True)
"""


def run_in_volume(script, image=None, runner=subprocess.run):
    """Run a Python script in a throw-away maubot container on the volume."""
    image = image or os.environ["MAUBOT_RUNTIME_IMAGE"]
    runner(
        (
            "podman", "run", "--rm", "--network=none",
            "--volume", f"{DATA_VOLUME}:/data:z",
            "--entrypoint", "python3",
            image, "-c", script, "/data",
        ),
        check=True,
    )


def make_snapshot(**kwargs):
    run_in_volume(SNAPSHOT_SCRIPT, **kwargs)


def restore_snapshot(**kwargs):
    run_in_volume(RESTORE_SCRIPT, **kwargs)


def cleanup_snapshot(**kwargs):
    run_in_volume(CLEANUP_SCRIPT, **kwargs)
