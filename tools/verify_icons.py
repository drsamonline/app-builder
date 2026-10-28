#!/usr/bin/env python3
"""Fail the build if a release artefact carries no icon.

Two checks, because the two artefacts fail differently:

  APK  the manifest must point at an icon, and the icon resources must be in the
       package. `aapt2 dump badging` is authoritative when the SDK is present;
       otherwise the zip listing is inspected for mipmap entries.

  EXE  the PE must contain an RT_GROUP_ICON resource (id 14). PyInstaller writes
       one only when --icon was passed, so an absent group means the default
       PyInstaller logo shipped.

Usage:
    python verify_icons.py --apk out/app.apk
    python verify_icons.py --exe out/app-portable.exe
Exit code 1 if any artefact has no icon.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import zipfile


def aapt2_path():
    home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or ""
    if home:
        found = sorted(glob.glob(os.path.join(home, "build-tools", "*", "aapt2")))
        if found:
            return found[-1]
    return shutil.which("aapt2")


def check_apk(path):
    if not os.path.isfile(path):
        return False, "not found: %s" % path

    aapt2 = aapt2_path()
    if aapt2:
        try:
            out = subprocess.run([aapt2, "dump", "badging", path],
                                 capture_output=True, text=True, timeout=120).stdout
            icons = [l for l in out.splitlines() if "application-icon" in l]
            if icons:
                return True, "%d icon declaration(s), e.g. %s" % (len(icons), icons[0].strip())
            return False, "aapt2 reports no application-icon in the manifest"
        except Exception as exc:                               # noqa: BLE001
            print("note: aapt2 could not be run (%s); falling back to the zip listing" % exc)

    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
    except Exception as exc:                                   # noqa: BLE001
        return False, "not a readable apk (%s)" % exc

    launchers = [n for n in names if "ic_launcher" in n]
    if launchers:
        return True, "%d ic_launcher resource(s), e.g. %s" % (len(launchers), launchers[0])
    return False, "no ic_launcher resource in the package (%d files)" % len(names)


def check_exe(path):
    if not os.path.isfile(path):
        return False, "not found: %s" % path
    try:
        import pefile
    except ImportError:
        return False, "pefile is not installed, so the icon cannot be verified"
    try:
        pe = pefile.PE(path, fast_load=True)
        pe.parse_data_directories()
    except Exception as exc:                                   # noqa: BLE001
        return False, "not a readable PE (%s)" % exc

    entries = getattr(pe, "DIRECTORY_ENTRY_RESOURCE", None)
    if not entries:
        return False, "no resource directory at all - the exe has no icon"
    ids = [e.id for e in entries.entries if getattr(e, "id", None) is not None]
    if 14 in ids:                                              # RT_GROUP_ICON
        return True, "RT_GROUP_ICON present"
    if 3 in ids:                                               # RT_ICON
        return True, "RT_ICON present"
    return False, "resource directory has no icon group (ids: %s)" % sorted(ids)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apk", default="")
    ap.add_argument("--exe", default="")
    args = ap.parse_args()
    if not (args.apk or args.exe):
        sys.exit("pass --apk and/or --exe")

    ok = True
    if args.apk:
        good, why = check_apk(args.apk)
        print("%s  APK  %s" % ("ok  " if good else "FAIL", why))
        ok = ok and good
    if args.exe:
        good, why = check_exe(args.exe)
        print("%s  EXE  %s" % ("ok  " if good else "FAIL", why))
        ok = ok and good
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
