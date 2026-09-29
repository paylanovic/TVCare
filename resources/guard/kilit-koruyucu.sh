#!/system/bin/sh
# TVCare Guard 1.1. Only the profiled TCL/Realtek CI CAM shutdown fault.
# Overrides are for the host-side simulation tests; Android uses these defaults.
DIR=${TVCARE_GUARD_DIR:-/data/local/tmp}
PROC=${TVCARE_PROC_DIR:-/proc}
SCRIPT=${TVCARE_GUARD_SCRIPT:-/data/local/tmp/kilit-koruyucu.sh}
LOG=$DIR/kilit-koruyucu.log
PIDF=$DIR/kilit-koruyucu.pid
LOCK=$DIR/kilit-koruyucu.lock
DISABLED=$DIR/kilit-koruyucu.disabled
THRESHOLD=500 # monotonic hundredths of a second
COOLDOWN=6000
umask 077

owned_pid() {
    case "$1" in ''|*[!0-9]*) return 1;; esac
    [ -r "$PROC/$1/cmdline" ] || return 1
    tr '\000' '\n' < "$PROC/$1/cmdline" 2>/dev/null | grep -Fxq "$SCRIPT"
}
status() {
    p=$(cat "$PIDF" 2>/dev/null)
    if owned_pid "$p" && [ "$(cat "$LOCK/pid" 2>/dev/null)" != "$p" ]; then
        echo LEGACY; return
    fi
    if [ -e "$DISABLED" ]; then
        if owned_pid "$p"; then echo "STOPPING:$p"; else echo DISABLED; fi
        return
    fi
    if owned_pid "$p"; then echo "RUNNING:$p"; else echo STOPPED; fi
}
case "${1:-}" in
    --status) status; exit 0;;
    --stop) : > "$DISABLED" || exit 1; echo DISABLED; exit 0;;
    --enable) rm -f "$DISABLED" || exit 1; exit 0;;
    '') ;;
    *) echo 'Usage: kilit-koruyucu.sh [--status|--stop|--enable]' >&2; exit 2;;
esac
[ -e "$DISABLED" ] && exit 0
mkdir -p "$DIR" || exit 1
# Kernel lock serializes start and stale directory reclamation, including concurrent starters.
# Android 11 toybox supplies flock. Fail closed if vendor omitted it.
command -v flock >/dev/null 2>&1 || { echo 'flock unavailable' >&2; exit 1; }
exec 9> "$DIR/kilit-koruyucu.flock" || exit 1
flock -n 9 || exit 0
# An older script may still run without our kernel/directory lock. Never duplicate it.
previous=$(cat "$PIDF" 2>/dev/null)
owned_pid "$previous" && exit 0
# mkdir is atomic. Give a newly created owner time to write its PID before reclaiming.
if ! mkdir "$LOCK" 2>/dev/null; then
    tries=0
    while [ "$tries" -lt 3 ]; do
        old=$(cat "$LOCK/pid" 2>/dev/null)
        owned_pid "$old" && exit 0
        sleep 1
        tries=$((tries + 1))
    done
    old=$(cat "$LOCK/pid" 2>/dev/null)
    owned_pid "$old" && exit 0
    # Remove just the known PID and empty directory, never recursive user data.
    rm -f "$LOCK/pid"
    rmdir "$LOCK" 2>/dev/null || exit 1
    mkdir "$LOCK" 2>/dev/null || exit 0
fi
printf '%s\n' "$$" > "$LOCK/pid" || exit 1
printf '%s\n' "$$" > "$PIDF" || exit 1
cleanup() {
    if [ "$(cat "$LOCK/pid" 2>/dev/null)" = "$$" ]; then
        rm -f "$PIDF" "$LOCK/pid"
        rmdir "$LOCK" 2>/dev/null
    fi
}
trap cleanup EXIT
trap 'exit 0' INT TERM HUP
log() {
    size=$(wc -c < "$LOG" 2>/dev/null || echo 0)
    if [ "${size:-0}" -ge 65536 ]; then mv -f "$LOG" "$LOG.1"; fi
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"
}
uptime_ticks() {
    read -r raw ignored < "$PROC/uptime" || return 1
    up=${raw%%.*}
    fraction=${raw#*.}
    case "$up:$fraction" in *[!0-9:]*|:*|*:) return 1;; esac
    fraction=$(printf '%.2s' "${fraction}00")
    # Prefix avoids interpreting fractional values like 08 as octal.
    echo $((up * 100 + 1$fraction - 100))
}
fault_present() {
    [ ! -e "$DISABLED" ] &&
    [ "$(getprop rtk.hal.cam_suspend)" = start ] &&
    [ "$(getprop sys.tcl.powerstatus)" = suspend ] &&
    [ "$(getprop rtk.hal.CICam_State)" != true ]
}
# Diagnostics are intentionally just bounded log lines: no dumpsys/sync can delay shutdown.
log "TVCare guard 1.1 started pid=$$"
since=''
retry_at=0
while [ ! -e "$DISABLED" ]; do
    now=$(uptime_ticks) || { sleep 1; continue; }
    if fault_present; then
        [ -n "$since" ] || since=$now
        if [ "$now" -lt "$since" ]; then since=$now; fi
        if [ $((now - since)) -ge "$THRESHOLD" ] && [ "$now" -ge "$retry_at" ]; then
            if fault_present; then
                log "CI CAM shutdown stall elapsed=$(((now - since) / 100))s; requesting poweroff"
                # timeout is provided by Android 11 toybox. Never issue an unbounded command.
                if command -v timeout >/dev/null 2>&1; then
                    timeout 3 reboot -p >/dev/null 2>&1
                    sleep 2
                    if fault_present; then timeout 3 svc power shutdown >/dev/null 2>&1; fi
                else
                    log 'timeout unavailable: no shutdown command issued'
                fi
                now=$(uptime_ticks) || now=$retry_at
                retry_at=$((now + COOLDOWN))
                log 'poweroff request returned; retry cooldown 60s'
            fi
        fi
    else
        since=''
    fi
    sleep 1
done
log 'guard disabled; exiting'
