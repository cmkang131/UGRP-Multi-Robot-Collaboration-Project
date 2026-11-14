#!/bin/bash
# Reduce Wi-Fi sleep latency without reconnecting or restarting time services.
set -euo pipefail
expected=$1
out=$2
test "$EUID" -eq 0
test "$(hostname -s)" = "$expected" || { echo 'Wrong robot'; exit 2; }
python3 - "$out" <<'PY'
import os, pathlib, pwd, sys
base = pathlib.Path(pwd.getpwnam(os.environ['SUDO_USER']).pw_dir).resolve()/'ugrp_clock_logs'
out = pathlib.Path(sys.argv[1]).resolve()
if out.parent != base or not out.name.startswith('run-'): raise SystemExit('Invalid output location')
PY
audit="$out/wifi-latency"
test ! -d "$audit" || { echo 'Existing Wi-Fi audit preserved; refusing overwrite'; exit 2; }
mkdir -p "$audit"
trap 'code=$?; echo "$code" > "$audit/exit_code.txt"; chown -R "$SUDO_UID:$SUDO_GID" "$audit"; exit "$code"' EXIT
exec > >(tee "$audit/prepare.log") 2>&1
profile=$(nmcli -g GENERAL.CONNECTION device show wlan0)
uuid=$(nmcli -g connection.uuid connection show "$profile")
printf '%s\n' "$uuid" > "$audit/connection_uuid.txt"
nmcli -g 802-11-wireless.powersave connection show uuid "$uuid" > "$audit/before_profile_powersave.txt"
/usr/sbin/iw dev wlan0 get power_save > "$audit/before_runtime_powersave.txt"
nmcli connection modify uuid "$uuid" 802-11-wireless.powersave 2
/usr/sbin/iw dev wlan0 set power_save off
nmcli -g 802-11-wireless.powersave connection show uuid "$uuid" > "$audit/after_profile_powersave.txt"
/usr/sbin/iw dev wlan0 get power_save > "$audit/after_runtime_powersave.txt"
cat "$audit/after_runtime_powersave.txt"
grep -F 'Power save: off' "$audit/after_runtime_powersave.txt" >/dev/null
date -u --iso-8601=ns > "$audit/utc.txt"
systemctl show chrony -p ActiveState -p UnitFileState > "$audit/chrony_service.txt"
chronyc -n tracking > "$audit/tracking.txt"
echo 'Wi-Fi sleep disabled; no connection or time service restart issued.'
