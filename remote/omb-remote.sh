#!/bin/sh
# Spark-side converter entry for omega-bridge-kit. One op per call.
#   sh omb-remote.sh OP [PINS_SHA256]   stdin = input, stdout = output, stderr = diagnostics
# OPs:
#   pins      print PINS and the sha256 of every installed tool
#   check     validate an .om unit with the bootstrap seed (omc 191b776e); no stdout
#   toc-c     .om -> C        (omega-bridge tools/bridge c)
#   toc-py    .om -> Python   (omega-bridge tools/bridge python)
#   native-c  one or more .om function units -> one C binding (omc 734f0a39 + native.om).
#             Units are separated by a line `#omb-unit`; each unit's LAST function is exported.
#   wasm      .om function unit -> wasm (omega-mv omc in IR mode + irwasm)
#   lift-c    C source -> .om       (omega-lift tools/lift c)
#   lift-py   Python source -> .om  (omega-lift tools/lift python)
# Exit status: the converter's own status is passed through (omc refusals use the error number,
# native.om refusal 110). 64 usage, 65 a pinned tool is missing or differs (run `omb setup`),
# 66 the caller's PINS differ from the PINS installed here.
set -u
KIT=$(cd "$(dirname "$0")/.." && pwd)
R=${OMB_HOME:-$HOME/.local/share/omega-bridge-kit}
# shellcheck disable=SC1090
. "$KIT/PINS"
op=${1-}
if [ -n "${2-}" ] && [ "$2" != "$(sha256sum < "$KIT/PINS" | cut -d' ' -f1)" ]; then
    echo "omb-remote: PINS on the Spark differ from the caller's PINS; run: omb setup" >&2; exit 66
fi
NICE="nice -n 19"
command -v taskset >/dev/null 2>&1 && NICE="nice -n 19 taskset -c 8-9"
sha() { sha256sum < "$1" | cut -d' ' -f1; }
need() { [ -f "$1" ] && [ "$(sha "$1")" = "$2" ] || { echo "omb-remote: $1 missing or not sha256 $2; run: omb setup" >&2; exit 65; }; }
B=$R/src/omega-bridge
L=$R/src/omega-lift
tmp=$(mktemp -d "${TMPDIR:-/tmp}/omb-remote.XXXXXX") || exit 65
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
cat > "$tmp/in"
case $op in
pins)
    cat "$KIT/PINS"
    echo "# installed on $(hostname) $(uname -sm)"
    for f in "$B/build/bootstrap/omc" "$B/build/bridge" "$R/bin/omc734" "$R/bin/native" "$R/bin/mvomc" "$R/bin/irwasm"; do
        if [ -f "$f" ]; then echo "# $(sha "$f")  $f"; else echo "# missing  $f"; fi
    done
    for d in "$B" "$R/src/omega-bridge-native" "$R/src/omega-mv" "$L"; do
        [ -d "$d/.git" ] && echo "# $(git -C "$d" rev-parse HEAD)  $d"
    done
    exit 0 ;;
check)
    need "$B/build/bootstrap/omc" "$BOOT_OMC_SHA256"
    $NICE "$B/build/bootstrap/omc" < "$tmp/in" > "$tmp/out"; exit $? ;;
toc-c|toc-py)
    need "$B/build/bootstrap/omc" "$BOOT_OMC_SHA256"; need "$B/build/bridge" "$BRIDGE_BIN_SHA256"
    mode=c; [ "$op" = toc-py ] && mode=python
    $NICE sh "$B/tools/bridge" "$mode" "$tmp/in"; exit $? ;;
native-c)
    need "$R/bin/omc734" "$OMC734_SHA256"; need "$R/bin/native" "$(cat "$R/bin/native.sha256" 2>/dev/null)"
    awk -v d="$tmp" 'BEGIN{n=1} /^#omb-unit/{if(seen){n++}; seen=0; next} {print > (d "/u" n ".om"); seen=1} END{print n > (d "/count")}' "$tmp/in"
    n=$(cat "$tmp/count"); : > "$tmp/frames"; i=1
    while [ "$i" -le "$n" ]; do
        u=$tmp/u$i.om
        [ -s "$u" ] || { echo "omb-remote: unit $i: empty" >&2; exit 64; }
        rc=0; $NICE "$R/bin/omc734" < "$u" > "$tmp/u$i.bin" 2> "$tmp/u$i.err" || rc=$?
        if [ "$rc" -ne 0 ]; then
            sed "s/^/omb-remote: unit $i: /" "$tmp/u$i.err" >&2; exit $rc
        fi
        { cat "$u"; printf '\0'; printf '%08d' "$(wc -c < "$tmp/u$i.bin")"; cat "$tmp/u$i.bin"; } > "$tmp/f$i"
        cat "$tmp/f$i" >> "$tmp/frames"; i=$((i + 1))
    done
    rc=0; $NICE "$R/bin/native" < "$tmp/frames" > "$tmp/out" || rc=$?
    if [ "$rc" -eq 0 ]; then cat "$tmp/out"; exit 0; fi
    i=1
    # Attribute the refusal: native.om refuses everything if any unit is outside its signature set.
    while [ "$i" -le "$n" ]; do
        "$R/bin/native" < "$tmp/f$i" > /dev/null 2>&1 || echo "omb-remote: unit $i: native.om refused (exit $?)" >&2
        i=$((i + 1))
    done
    exit $rc ;;
wasm)
    need "$R/bin/mvomc" "$MV_OMC_SHA256"; need "$R/bin/irwasm" "$IRWASM_SHA256"
    { printf 'ir\n'; cat "$tmp/in"; } > "$tmp/ir.in"
    $NICE "$R/bin/mvomc" < "$tmp/ir.in" > "$tmp/ir" || exit $?
    $NICE "$R/bin/irwasm" < "$tmp/ir" > "$tmp/out" || exit $?
    cat "$tmp/out"; exit 0 ;;
lift-c|lift-py)
    [ "$LIFT_SHA" != PENDING ] && [ -x "$L/tools/lift" ] || { echo "omb-remote: omega-lift not installed (LIFT_SHA=$LIFT_SHA)" >&2; exit 65; }
    mode=c; [ "$op" = lift-py ] && mode=python
    $NICE "$L/tools/lift" "$mode" "$tmp/in"; exit $? ;;
*)
    echo "usage: omb-remote.sh pins|check|toc-c|toc-py|native-c|wasm|lift-c|lift-py [PINS_SHA256]" >&2; exit 64 ;;
esac
