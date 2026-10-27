#!/bin/sh
# Spark-side setup for omega-bridge-kit. Idempotent: every step checks its pinned sha256 first and
# only rebuilds what is missing or wrong. Installs nothing system-wide; everything lives under
# $OMB_HOME (default ~/.local/share/omega-bridge-kit). Requires Linux AArch64, git, sha256sum.
# Usage (normally via `omb setup` on the Mac, which copies PINS + remote/ here first):
#   sh remote/setup.sh            exit 0 ready, 1 a pin or build failed, 3 not AArch64 Linux
set -eu
KIT=$(cd "$(dirname "$0")/.." && pwd)
R=${OMB_HOME:-$HOME/.local/share/omega-bridge-kit}
[ "$(uname -s)/$(uname -m)" = Linux/aarch64 ] || { echo "setup: needs Linux AArch64, got $(uname -sm)" >&2; exit 3; }
# shellcheck disable=SC1090
. "$KIT/PINS"
NICE="nice -n 19"
command -v taskset >/dev/null 2>&1 && NICE="nice -n 19 taskset -c 8-9"
mkdir -p "$R/bin" "$R/src"
say() { printf 'setup: %s\n' "$*" >&2; }
sha() { sha256sum < "$1" | cut -d' ' -f1; }
ok() { [ -f "$1" ] && [ "$(sha "$1")" = "$2" ]; }
need() { ok "$1" "$2" || { say "FAIL $1 sha256 $( [ -f "$1" ] && sha "$1" || echo missing ), pinned $2"; exit 1; }; }
# fetch DIR REPO COMMIT: shallow fetch of one exact commit, checked out detached.
fetch() {
    if [ -d "$1/.git" ] && [ "$(git -C "$1" rev-parse HEAD 2>/dev/null)" = "$3" ]; then return 0; fi
    say "fetch $2 @ $3 -> $1"
    rm -rf "$1"; git init -q "$1"
    git -C "$1" fetch -q --depth=1 "$2" "$3"
    git -C "$1" -c advice.detachedHead=false checkout -q FETCH_HEAD
    [ "$(git -C "$1" rev-parse HEAD)" = "$3" ] || { say "FAIL $1 is not at $3"; exit 1; }
}

# 1. omega-bridge toc: source-only bootstrap of the seed, then the bridge compiler.
B=$R/src/omega-bridge
if ok "$B/build/bridge" "$BRIDGE_BIN_SHA256" && ok "$B/build/bootstrap/omc" "$BOOT_OMC_SHA256" \
   && [ "$(git -C "$B" rev-parse HEAD)" = "$BRIDGE_SHA" ]; then
    say "ok omega-bridge $BRIDGE_SHA (bridge $BRIDGE_BIN_SHA256)"
else
    fetch "$B" "$BRIDGE_REPO" "$BRIDGE_SHA"
    need "$B/src/toc.om" "$TOC_OM_SHA256"
    (cd "$B" && $NICE sh tools/bootstrap.sh >&2 && $NICE sh tools/build.sh >&2)
    need "$B/build/bootstrap/omc" "$BOOT_OMC_SHA256"
    need "$B/build/bridge" "$BRIDGE_BIN_SHA256"
fi

# 2. omc 734f0a39 (function mode, for native.om) from aien-spark/omega.
if ! ok "$R/bin/omc734" "$OMC734_SHA256"; then
    fetch "$R/src/omega" "$OMC734_REPO" "$OMC734_COMMIT"
    git -C "$R/src/omega" show "$OMC734_COMMIT:seed/out/omc" > "$R/bin/omc734.tmp"
    chmod +x "$R/bin/omc734.tmp"; mv "$R/bin/omc734.tmp" "$R/bin/omc734"
fi
need "$R/bin/omc734" "$OMC734_SHA256"; say "ok omc734 $OMC734_SHA256"

# 3. native.om at the native pin, compiled by omc734.
N=$R/src/omega-bridge-native
fetch "$N" "$BRIDGE_REPO" "$NATIVE_SHA"
need "$N/src/native.om" "$NATIVE_OM_SHA256"
want_native=$($NICE "$R/bin/omc734" < "$N/src/native.om" | sha256sum | cut -d' ' -f1)
if ! ok "$R/bin/native" "$want_native"; then
    $NICE "$R/bin/omc734" < "$N/src/native.om" > "$R/bin/native.tmp"
    chmod +x "$R/bin/native.tmp"; mv "$R/bin/native.tmp" "$R/bin/native"
fi
printf '%s\n' "$want_native" > "$R/bin/native.sha256"; say "ok native.om $NATIVE_OM_SHA256 -> native $want_native"

# 4. omega-mv omc (IR mode) and irwasm.
if ! ok "$R/bin/mvomc" "$MV_OMC_SHA256" || ! ok "$R/bin/irwasm" "$IRWASM_SHA256"; then
    fetch "$R/src/omega-mv" "$MV_REPO" "$MV_SHA"
    git -C "$R/src/omega-mv" show "$MV_SHA:seed/out/omc" > "$R/bin/mvomc"; chmod +x "$R/bin/mvomc"
    need "$R/bin/mvomc" "$MV_OMC_SHA256"
    need "$R/src/omega-mv/seed/wasm/irwasm.om" "$IRWASM_OM_SHA256"
    $NICE "$R/bin/mvomc" < "$R/src/omega-mv/seed/wasm/irwasm.om" > "$R/bin/irwasm.tmp"
    chmod +x "$R/bin/irwasm.tmp"; mv "$R/bin/irwasm.tmp" "$R/bin/irwasm"
fi
need "$R/bin/mvomc" "$MV_OMC_SHA256"; need "$R/bin/irwasm" "$IRWASM_SHA256"
say "ok omega-mv $MV_SHA omc $MV_OMC_SHA256 irwasm $IRWASM_SHA256"

# 5. omega-lift (Spark-side lifter, used for cross-checking the Mac lifter).
L=$R/src/omega-lift
if [ "$LIFT_SHA" = PENDING ]; then
    say "NOT_RUN omega-lift: LIFT_SHA is PENDING in PINS"
else
    fetch "$L" "$LIFT_REPO" "$LIFT_SHA"
    need "$L/src/lift.om" "$LIFT_OM_SHA256"
    if [ -f "$L/tools/build.sh" ]; then (cd "$L" && OMEGA_SEED="$B/build/bootstrap/omc" $NICE sh tools/build.sh >&2); fi
    say "ok omega-lift $LIFT_SHA"
fi
say "ready $R"
