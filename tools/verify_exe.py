#!/usr/bin/env python3
"""Verify the portable EXE we ship — nothing inspected it before.

    python tools/verify_exe.py dist/my-app-portable.exe [--max-mb 60]

The app pipeline builds and publishes a portable Windows EXE, and nothing
checked what was inside it. A build that silently bundles the wrong interpreter,
or a stray dev dependency, would ship unnoticed — and a user's antivirus would
notice it for us, which is the wrong way to find out. This reads the PE and
asserts it is what we meant to ship.

Assertions (a failure prints the problem and exits 1):
  * the file is a valid PE (pefile can parse it)
  * it is an EXECUTABLE, not a DLL
  * its size is within a budget (default 60 MB; --max-mb or MAX_EXE_MB)
  * REQUIRED_IMPORTS (comma-separated substrings) — at least one must be imported
  * FORBIDDEN_IMPORTS (comma-separated substrings) — none may be imported
  * SIGNED_REQUIRED=1 — the file must carry an Authenticode signature

It always prints a summary — machine, subsystem, size, imports, signed — so the
build log, and the run log, record what actually shipped.

Zero dependencies beyond pefile (MIT). Run it on the built artefact, never on a
guess.
"""
from __future__ import annotations

import argparse
import os
import sys


def _fail(msg: str) -> int:
    print("[verify-exe] FAIL: " + msg)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify a portable Windows EXE.")
    ap.add_argument("exe", help="path to the built .exe")
    ap.add_argument("--max-mb", type=float,
                    default=float(os.environ.get("MAX_EXE_MB", "60")),
                    help="size budget in MB (default 60)")
    args = ap.parse_args()

    try:
        import pefile
    except ImportError:
        return _fail("pefile is not installed (pip install pefile)")

    path = args.exe
    if not os.path.isfile(path):
        return _fail("not a file: %s" % path)

    size = os.path.getsize(path)
    try:
        pe = pefile.PE(path)
    except Exception as exc:  # noqa: BLE001 - any parse error means "not a PE"
        return _fail("not a valid PE: %s" % exc)

    problems: list[str] = []

    # 1. an executable, not a DLL
    IMAGE_FILE_DLL = 0x2000
    if pe.FILE_HEADER.Characteristics & IMAGE_FILE_DLL:
        problems.append("the file is a DLL, not an executable")

    # 2. size budget
    if size > args.max_mb * 1024 * 1024:
        problems.append("size %.1f MB exceeds the %.0f MB budget"
                        % (size / 1048576.0, args.max_mb))

    # 3. imported DLLs (the PE import table)
    imports: set[str] = set()
    for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []) or []:
        imports.add(entry.dll.decode("ascii", "replace").lower())

    required = [x.strip().lower() for x in os.environ.get("REQUIRED_IMPORTS", "").split(",") if x.strip()]
    forbidden = [x.strip().lower() for x in os.environ.get("FORBIDDEN_IMPORTS", "").split(",") if x.strip()]
    if required and not any(any(r in i for i in imports) for r in required):
        problems.append("none of the required imports is present: %s" % ", ".join(required))
    for f in forbidden:
        hit = sorted(i for i in imports if f in i)
        if hit:
            problems.append("forbidden import present (%s): %s" % (f, ", ".join(hit)))

    # 4. signature (only asserted when asked)
    signed = hasattr(pe, "DIRECTORY_ENTRY_SECURITY")
    if os.environ.get("SIGNED_REQUIRED") == "1" and not signed:
        problems.append("the file is not signed")

    machine = {0x8664: "x64", 0x14C: "x86", 0xAA64: "arm64"}.get(
        pe.FILE_HEADER.Machine, hex(pe.FILE_HEADER.Machine))
    subsystem = {2: "GUI", 3: "console"}.get(
        pe.OPTIONAL_HEADER.Subsystem, str(pe.OPTIONAL_HEADER.Subsystem))

    print("[verify-exe] %s" % os.path.basename(path))
    print("   size    : %.2f MB (%d bytes)" % (size / 1048576.0, size))
    print("   machine : %s | subsystem: %s" % (machine, subsystem))
    print("   signed  : %s" % ("yes" if signed else "no"))
    print("   imports : %d dll(s)" % len(imports))
    for i in sorted(imports):
        print("      -", i)

    if problems:
        print("[verify-exe] FAIL:")
        for p in problems:
            print("   -", p)
        return 1
    print("[verify-exe] OK — valid PE, executable, within budget, no forbidden imports")
    return 0


if __name__ == "__main__":
    sys.exit(main())
