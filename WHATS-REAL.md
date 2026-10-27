# What's real / what's not

Every step the kit shows, where it runs, and who did the work. **TOOL** means a program did the
conversion. **AGENT** means an AI agent wrote or ported it by hand, so a tool did not produce it.
Status words: EXERCISED = run by `./omb verify` with a differential against a reference;
NOT_RUN = not run yet (never counted as a pass); REFUSED = the compiler said no, with its exact error.
The UI shows this same table (its "What's real / what's not" card reads this file).

| Step | Where it runs | TOOL or AGENT | Status |
|---|---|---|---|
| C / Python → .om (the lifter, `src/lift.om` in aien-dev/omega-lift) | MAC: clang-built `gen/lift.c`, cross-checked by python3 `gen/lift.py` and by the Spark build | TOOL (the lifter is Omega written by an agent; each lift is done by the tool) | NOT_RUN until the lifter is pinned in `PINS` |
| .om → C, .om → Python (`toc`, aien-dev/omega-bridge) | SPARK via ssh (`remote/omb-remote.sh toc-c` / `toc-py`) | TOOL | EXERCISED on the samples |
| .om → native AArch64 code inside a C binding (`src/native.om` + seeded omc 734f0a39) | SPARK via ssh (`native-c`); the binding C is then compiled by clang on the MAC | TOOL | Linux AArch64 EXERCISED; macOS needs the native-darwin pin (NOT_RUN until then) |
| .om → WebAssembly (omega-mv omc IR mode + `irwasm`) | SPARK via ssh (`wasm`) | TOOL | EXERCISED where the unit fits IR mode |
| Running the WebAssembly | MAC (`jsc`, JavaScriptCore) and BROWSER (WebAssembly in the page) | TOOL | EXERCISED on the Mac |
| Running toc C and native C | MAC (Apple clang) | TOOL | EXERCISED |
| Running toc Python | MAC (`/usr/bin/python3`) | TOOL | EXERCISED |
| Running the original C / Python | MAC (clang with UBSan / python3) | TOOL | EXERCISED once a C/Python original is lifted |
| Round trip `bridge (lift (bridge X)) == bridge X`, byte for byte | lift on the MAC, bridge on the SPARK via ssh | TOOL | NOT_RUN until the lifter is pinned |
| Negative control (one mutated operator must be caught) | mutation by `omb` on the MAC, toc on the SPARK, run on the MAC | TOOL | EXERCISED (must say "caught") |
| `samples/gcd.om`, `samples/power.om`, `samples/gcd.c`, `samples/gcd.py` | — | AGENT: written by hand as inputs, not converted | input only |
| `omb`, `ui/server.py`, `ui/index.html`, `remote/*.sh`, test drivers | MAC / SPARK | AGENT: host infrastructure (CLI, UI, harness). None of it converts anything | — |
| Recursive functions (e.g. `fpow`) | SPARK compilers | — | REFUSED by compiler (toc library mode and omc function mode: error 9; IR mode: error 3). Neither pass nor fail |

Not claimed: this is not a universal C/Python ↔ Omega converter. Only the bounded scalar subset in
omega-bridge `docs/CAPABILITIES.md` converts; everything else is refused or skipped with a reason.
Every compiler step runs on the Spark over ssh; the Mac runs and compares the results.
