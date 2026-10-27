# omega-bridge-kit

See the Omega bridge convert both ways on a Mac. One function goes C or Python → Omega (`.om`) →
C, Python, native AArch64 code and WebAssembly → back to `.om`. Every form runs on the same inputs
and is compared against the original.

## Start here

1. On an Apple Silicon Mac that can `ssh spark` (key login), run
   `git clone https://github.com/aien-dev/omega-bridge-kit && cd omega-bridge-kit`.
2. Run `./omb setup`. It copies `PINS` and `remote/` to the Spark and builds the pinned compilers there
   from source, checking every sha256 in `PINS`. It installs nothing on the Mac.
3. Run `./omb verify`. You get a ✓/✗ table per function and per form (at least 500 seeded inputs each,
   timings in ms) and a negative control that must say "caught". Exit 0 means everything that ran agreed.
4. Run `./start`. It opens the UI at `http://127.0.0.1:8765/`, local only. Pick a file, press
   **Run all** (⌘⏎), and read the command log; every ssh command is shown.
5. Read `WHATS-REAL.md` (the same card is in the UI). It says where each step ran and what was written by an agent.

Other commands: `./omb convert c|py|om om|c|py|native|wasm FILE`, `./omb run FILE [--fn NAME] ARGS…`,
`./omb roundtrip FILE`, `./omb verify --quick` (64 inputs). Add `--json` to any of them for JSONL output,
and `--fresh` to skip the conversion cache.

## What runs where

- **SPARK via ssh**: every compiler step. That covers `toc` (.om → C/Python), `native.om` with its
  seeded omc (.om → AArch64 code bytes in a C binding), omc IR mode plus `irwasm` (.om → wasm), and a
  copy of the lifter for cross-checking. The commands are in `remote/omb-remote.sh`.
- **MAC**: the lifter (`gen/lift.c` built with clang, plus `gen/lift.py`), Apple clang for every C
  form, `/usr/bin/python3` for every Python form, and JavaScriptCore `jsc` for wasm. Timing runs take
  `~/omega-work/.mac.lock`, the same lock `/usr/bin/lockf -k` uses.
- **BROWSER**: the UI also instantiates the wasm module itself and shows that result as its own column.
- `omb`, `ui/` and `remote/` are host infrastructure (CLI, UI, test harness) written in Python and sh.
  They convert nothing.

## What is not claimed

- This is not universal conversion. Only the bounded scalar subset in omega-bridge
  `docs/CAPABILITIES.md` converts: at most 32 functions and 4 parameters, integer scalars, and no
  floats, text, heap, break or continue.
- Anything else is refused or skipped with the tool's exact reason. Recursive functions show
  "REFUSED by compiler". That is neither a pass nor a fail.
- Compilers run on the Spark, not on the Mac. NOT_RUN is never counted as a pass.
- Results here are host runs (MAC, SPARK, BROWSER). They are not hardware qualification.

Connected repos: [aien-dev/omega-bridge](https://github.com/aien-dev/omega-bridge) (toc, native ABI) ·
[aien-dev/omega-lift](https://github.com/aien-dev/omega-lift) (C/Python → .om) ·
[aien-dev/omega-mv](https://github.com/aien-dev/omega-mv) (IR → wasm). Exact commits are in `PINS`.

License: Apache-2.0 WITH LLVM-exception (`LICENSE`, `NOTICE`). The picks in `picks/` keep their own
MIT licenses; see `picks/PICK.md`.
