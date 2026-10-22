#!/usr/bin/env python3
"""
Build a single-file portable EXE from ``launcher.py`` plus the ``app/`` folder.

Usage:
    APP_NAME=my-app python build.py

Produces ``dist/<APP_NAME>-portable.exe`` on Windows (and a native binary on
other platforms, which is only useful for smoke-testing).

Notes:
    * ``--onefile`` bundles everything into one executable.
    * ``--add-data`` needs the platform separator: ``;`` on Windows, ``:``
      elsewhere.  We detect it from ``os.name``.
    * The ``app`` folder is bundled under the name ``app`` so that
      ``sys._MEIPASS/app`` resolves at runtime.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# PyInstaller --add-data uses ';' on Windows and ':' on POSIX.
DATA_SEP = ";" if os.name == "nt" else ":"


def main() -> int:
    app_name = (os.environ.get("APP_NAME") or "app").strip() or "app"
    app_dir = os.path.join(HERE, "app")

    if not os.path.isdir(app_dir):
        sys.exit("[build] ERROR: 'app/' folder not found at {}".format(app_dir))

    name = "{}-portable".format(app_name)
    dist = os.path.join(HERE, "dist")
    work = os.path.join(HERE, "build")
    spec = os.path.join(HERE, "spec")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        name,
        "--distpath",
        dist,
        "--workpath",
        work,
        "--specpath",
        spec,
        "--add-data",
        "{}{}app".format(app_dir, DATA_SEP),
        os.path.join(HERE, "launcher.py"),
    ]

    print("[build] command:", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=HERE)

    exe = os.path.join(dist, name + (".exe" if os.name == "nt" else ""))
    if not os.path.exists(exe):
        sys.exit("[build] ERROR: expected output not found: {}".format(exe))

    print("[build] OK -> {} ({} bytes)".format(exe, os.path.getsize(exe)), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
