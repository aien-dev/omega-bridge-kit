#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Negative tests for GET /api/file in ui/server.py (host infrastructure, like the server it tests).

Runs the server from a scratch copy of the kit that also holds an outside marker file reached by
a symlinked sample and by a symlinked picks/ directory. Every request that tries to leave samples/ or
picks/ must get 404 and must not return the marker; a real sample must still come back (positive
control). Usage: python3 ui/test_file_containment.py   (exit 0 = all cases pass; needs no Spark)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

KIT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
MARKER = "omb-containment-marker-7f3a"


def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=10) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def main():
    tmp = tempfile.mkdtemp(prefix="omb-ui-test-")
    kit = os.path.join(tmp, "kit")
    shutil.copytree(KIT, kit, ignore=shutil.ignore_patterns(".git", ".omb", "picks"))
    outside = os.path.join(tmp, "outside")
    os.makedirs(outside)
    with open(os.path.join(outside, "outside.c"), "w") as fh:
        fh.write("/* %s */\n" % MARKER)
    os.symlink(os.path.join(outside, "outside.c"), os.path.join(kit, "samples", "escape.c"))
    os.symlink("gcd.c", os.path.join(kit, "samples", "alias.c"))           # inside: still served
    os.symlink(outside, os.path.join(kit, "picks"))                          # whole directory outside
    srv = subprocess.Popen([sys.executable, os.path.join(kit, "ui", "server.py"), "0"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                           env=dict(os.environ, OMB_WORK=os.path.join(tmp, "work")))
    fails = 0
    try:
        base = srv.stdout.readline().strip().rstrip("/")

        def case(name, ok):
            nonlocal fails
            print(("ok    " if ok else "FAIL  ") + name)
            fails += not ok

        code, body = get(base, "/api/file?path=samples/gcd.c")
        case("positive control: samples/gcd.c served", code == 200 and json.loads(body)["path"] == "samples/gcd.c")
        code, body = get(base, "/api/file?path=samples/alias.c")
        case("symlink that stays inside samples/ served", code == 200 and "gcd" in json.loads(body)["src"])
        for rel in ("../README.md", "samples/../README.md", "samples/../../outside/outside.c",
                    "%2e%2e/README.md", "samples%2f..%2f..%2foutside%2foutside.c", "/etc/passwd",
                    os.path.join(outside, "outside.c"), "samples/escape.c", "picks/outside.c"):
            code, body = get(base, "/api/file?path=" + rel)
            case("refused %-40s -> %d" % (rel, code), code == 404 and MARKER not in body)
        code, body = get(base, "/api/info")
        files = [f["path"] for f in json.loads(body)["files"]] if code == 200 else []
        case("listing offers no escaping symlink", code == 200 and "samples/gcd.c" in files
             and "samples/escape.c" not in files and not any(f.startswith("picks/") for f in files))
    finally:
        srv.terminate()
        srv.wait()
        shutil.rmtree(tmp)
    print("%s: %d failed" % ("PASS" if fails == 0 else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
