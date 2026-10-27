#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
"""Local UI server for omega-bridge-kit. Host infrastructure (UI glue), never a converter.

Binds 127.0.0.1 only. Every conversion goes through ../omb, so the UI shows exactly the
commands omb runs: local ones (clang, python3, jsc, the lifter) and the ssh hop to the Spark.
Usage: python3 ui/server.py [PORT]   (PORT 0 = pick a free one; prints the URL on stdout)
"""
import base64
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import sys
import time
import urllib.parse
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer

KIT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
_loader = importlib.machinery.SourceFileLoader("omb", os.path.join(KIT, "omb"))
_spec = importlib.util.spec_from_loader("omb", _loader)
omb = importlib.util.module_from_spec(_spec)
_loader.exec_module(omb)

LANG_EXT = {"c": ".c", "py": ".py", "om": ".om"}


def source_files():
    out = []
    for d in ("samples", "picks"):
        p = os.path.join(KIT, d)
        if os.path.isdir(p):
            for f in sorted(os.listdir(p)):
                ext = os.path.splitext(f)[1]
                if ext in (".c", ".py", ".om"):
                    out.append({"path": d + "/" + f, "lang": ext[1:]})
    return out


def stash(lang, src):
    """Pasted or edited source -> a file under WORK (the original runners need a path)."""
    d = os.path.join(omb.WORK, "ui")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "src-%s%s" % (hashlib.sha256(src).hexdigest()[:16], LANG_EXT[lang]))
    with open(p, "wb") as fh:
        fh.write(src)
    return p


def text(b):
    return b.decode(errors="replace") if isinstance(b, bytes) else b


def refusals(r):
    return {n: {"tool": x["tool"], "msg": x["msg"], "expected": x["expected"]} for n, x in r["refused"].items()}


def api_lift(q):
    src = q["src"].encode()
    res = {}
    for impl in ("c", "py"):
        rc, out, err, ms, where = omb.lift(q["lang"], src, impl)
        skips, fatal, other = omb.parse_lift_err(err)
        res[impl] = {"rc": rc, "om": text(out), "skips": skips, "fatal": fatal, "other": other, "ms": round(ms, 1), "where": where}
    a = res["c"]
    names = []
    if a["rc"] == 0:
        _, fns, orig = omb.parse_unit(a["om"])
        names = [{"name": f.name, "orig": orig.get(f.name, f.name), "sig": f.sig()} for f in fns]
    return {"rc": a["rc"], "om": a["om"], "skips": a["skips"], "fatal": a["fatal"], "other": a["other"], "lifted": names,
            "ms": a["ms"], "where": a["where"] + " (clang-built lift.c)",
            "py_agrees": res["py"]["rc"] == a["rc"] and res["py"]["om"] == a["om"], "py_ms": res["py"]["ms"]}


def api_convert(q):
    om = q["om"].encode()
    to = q["to"]
    if to in ("c", "py"):
        r = omb.toc(om, to)
        return {"rc": r["rc"], "out": text(r["out"]), "refused": refusals(r), "exported": r["exported"], "ms": round(r["ms"], 1),
                "where": "SPARK via ssh", "err": r["err"]}
    if to == "native":
        r = omb.native(om)
        return {"rc": r["rc"], "out": text(r["out"]), "refused": refusals(r), "exported": r["exported"], "hex": r["hex"],
                "ms": round(r["ms"], 1), "where": "SPARK via ssh"}
    if to == "wasm":
        r = omb.wasm(om)
        return {"rc": r["rc"], "b64": base64.b64encode(r["out"]).decode(), "size": len(r["out"]), "hex": r["out"].hex(),
                "refused": refusals(r), "exported": r["exported"], "ms": round(r["ms"], 1), "where": "SPARK via ssh",
                "sigs": {f.name: {"params": [t for _, t in f.params], "ret": f.ret} for f in omb.parse_unit(q["om"])[1]}}
    raise omb.OmbError("unknown target %s" % to, 64)


def api_runall(q):
    lang = q.get("lang", "om")
    src = (q.get("src") if lang != "om" else q.get("om")) or ""
    path = stash(lang, src.encode())
    P = omb.prepare(path, need_rt=True)
    if P["om"] is None:
        raise omb.OmbError("lifter refused the source (see the lift result)", 1)
    with omb.mac_lock():
        f, vals, recs = omb.run_one(P, q.get("fn") or None, q.get("args", []))
    return {"fn": f.name, "sig": f.sig(), "args": [str(v) for v in vals], "results": recs,
            "fns": [x.name for x in P["fns"] if x.scalar], "om": text(P["om"]),
            "skips": (P["lift"] or {}).get("skips", []),
            "lift_agrees": (P["lift"] or {}).get("py_agrees"),
            "roundtrip": {k: v["identical"] for k, v in (P.get("rt") or {}).items()}}


def whats_real():
    """Rows of the table in WHATS-REAL.md (single source for the repo file and the UI card)."""
    rows = []
    with open(os.path.join(KIT, "WHATS-REAL.md"), encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("|") and not set(line.strip()) <= set("|-: "):
                rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return {"head": rows[0] if rows else [], "rows": rows[1:]}


class H(BaseHTTPRequestHandler):
    server_version = "omb-ui"

    def log_message(self, fmt, *a):
        sys.stderr.write("[ui] %s\n" % (fmt % a))

    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def json(self, code, obj):
        self.send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(KIT, "ui", "index.html"), "rb") as fh:
                return self.send(200, fh.read(), "text/html; charset=utf-8")
        if self.path == "/favicon.ico":
            return self.send(204, b"", "image/x-icon")
        if self.path == "/api/info":
            pick = os.path.join(KIT, "picks", "PICK.md")
            return self.json(200, {"spark": omb.SPARK, "here": omb.HERE, "pins_sha": omb.PINS_SHA, "pins": omb.PINS,
                                   "lifter": omb.lifter_status() or "ok", "files": source_files(), "forms": omb.FORMS,
                                   "whats_real": whats_real(),
                                   "pick_md": open(pick, encoding="utf-8").read() if os.path.exists(pick) else ""})
        if self.path.startswith("/api/file?path="):
            rel = urllib.parse.unquote(self.path.split("=", 1)[1])
            allowed = {f["path"] for f in source_files()}
            if rel not in allowed:
                return self.json(404, {"error": "not a kit source file"})
            with open(os.path.join(KIT, rel), "rb") as fh:
                return self.json(200, {"path": rel, "lang": os.path.splitext(rel)[1][1:], "src": text(fh.read())})
        return self.json(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            q = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self.json(400, {"error": "bad json"})
        handler = {"/api/lift": api_lift, "/api/convert": api_convert, "/api/runall": api_runall}.get(self.path)
        if not handler:
            return self.json(404, {"error": "not found"})
        omb.FRESH = bool(q.get("fresh"))
        mark = len(omb.EVENTS)
        t = time.time()
        try:
            res = handler(q)
            code = 200
        except omb.OmbError as e:
            res, code = {"error": str(e), "exit": e.code}, 200
        except Exception as e:   # surface, never hide
            traceback.print_exc()
            res, code = {"error": "%s: %s" % (type(e).__name__, e)}, 500
        res["log"] = omb.EVENTS[mark:]
        res["wall_ms"] = round((time.time() - t) * 1000, 1)
        self.json(code, res)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    try:
        srv = HTTPServer(("127.0.0.1", port), H)
    except OSError:
        srv = HTTPServer(("127.0.0.1", 0), H)
    print("http://127.0.0.1:%d/" % srv.server_address[1], flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
