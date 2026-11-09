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
    ]

    # The icon the release ships with. tools/make_icons.py writes it; without one
    # PyInstaller embeds its own default logo, which reads as an unfinished build
    # to anyone downloading the exe.
    icon = os.environ.get("ICON_PATH", "")
    if icon and os.path.exists(icon):
        print("[build] icon:", icon, flush=True)
        cmd += ["--icon", icon]
    else:
        print("[build] WARNING: no ICON_PATH - the exe will carry the default icon",
              flush=True)

    # ---- size ------------------------------------------------------------
    # The launcher serves a folder over http and opens a browser. It does not
    # do TLS, it does not hash, and it does not decompress anything, so the
    # modules that drag in libcrypto (2.3 MB), libssl, libbz2, liblzma and
    # libzstd are dead weight in every app built with this kit.
    #
    # Measured on Kitbox (493 tools, 1.1 MB of HTML) with Python 3.12 on Linux:
    #   default                     8,269,680 bytes
    #   without these modules       5,745,328 bytes  (-30%)
    #   plus --strip (POSIX only)   included above
    # and the binary still serves the app: HTTP 200, correct title, full size.
    #
    # unicodedata is NOT in this list on purpose. Excluding it builds fine and
    # then dies at runtime in socket.getfqdn() -> encodings.idna, which needs
    # unicodedata — the app never starts and the log says "unknown encoding:
    # idna" three frames away from the cause.
    for module in (
        "ssl", "_ssl", "hashlib", "_hashlib", "_blake2",
        "bz2", "_bz2", "lzma", "_lzma", "_zstd", "readline",
    ):
        cmd += ["--exclude-module", module]

    # Symbol tables are dead weight in a shipped binary. PyInstaller documents
    # --strip as not recommended on Windows, so it is POSIX-only — which is
    # also where it matters most, because the Linux build bundles the
    # interpreter's own libpython3.12.so (29.9 MB unstripped in the CI image,
    # which is why that artifact is the largest of the three).
    if os.name != "nt":
        cmd += ["-s"]

    cmd += [
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
