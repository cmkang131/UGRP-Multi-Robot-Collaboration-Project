#!/bin/bash
# Maintenance-only clock setup; no robot motion commands.
set -euo pipefail
role=$1
expected_host=$2
leader_ip=$3
client_ip=$4
pc_ip=$5
run_dir=$6
code_revision=$7
test "$EUID" -eq 0 || { echo 'sudo is required'; exit 1; }
test "$(hostname -s)" = "$expected_host" || { echo 'Wrong robot hostname; no change'; exit 1; }
case "$role" in leader|follower) ;; *) exit 2 ;; esac
python3 - "$leader_ip" "$client_ip" "$pc_ip" "$run_dir" <<'PY'
import ipaddress, os, pathlib, pwd, sys
for v in sys.argv[1:4]: ipaddress.IPv4Address(v)
user = pwd.getpwnam(os.environ['SUDO_USER'])
out = pathlib.Path(sys.argv[4]).resolve()
base = pathlib.Path(user.pw_dir).resolve() / 'ugrp_clock_logs'
if out.parent != base or not out.name.startswith('run-'):
    raise SystemExit('Output must be a new run under user home/ugrp_clock_logs')
PY
own_ip=$leader_ip
if test "$role" = follower; then own_ip=$client_ip; fi
ip -4 -o addr show | grep -F " $own_ip/" >/dev/null || { echo 'Expected IP does not belong to this robot; no configuration change'; exit 2; }
mkdir -p "$run_dir/backup"
test ! -e "$run_dir/backup/finished" || { echo 'This run was already used'; exit 2; }
exec > >(tee -a "$run_dir/setup.log") 2>&1
fix_owner() { chown -R "$SUDO_UID:$SUDO_GID" "$run_dir"; }
trap 'code=$?; printf "%s\n" "$code" > "$run_dir/setup_exit_code.txt"; fix_owner; exit "$code"' EXIT
printf 'role=%s\nhost=%s\nleader_ip=%s\nclient_ip=%s\ncode_revision=%s\n' "$role" "$expected_host" "$leader_ip" "$client_ip" "$code_revision" > "$run_dir/parameters.txt"
date -u --iso-8601=ns > "$run_dir/before_utc.txt"
uname -a > "$run_dir/environment.txt"
cat /etc/os-release >> "$run_dir/environment.txt"
timedatectl status > "$run_dir/before_status.txt" || true
timedatectl timesync-status >> "$run_dir/before_status.txt" 2>&1 || true
chronyc -n tracking >> "$run_dir/before_status.txt" 2>&1 || true
dpkg-query -W chrony systemd-timesyncd ntp ntpsec > "$run_dir/before_packages.txt" 2>&1 || true
for unit in systemd-timesyncd chrony ntp ntpsec; do
    systemctl show "$unit" -p LoadState -p ActiveState -p UnitFileState > "$run_dir/backup/$unit.state"
done
for original in /etc/chrony/chrony.conf /etc/systemd/timesyncd.conf; do
    if test -f "$original"; then cp --parents "$original" "$run_dir/backup/"; fi
done
for original in /etc/systemd/timesyncd.conf.d/*.conf; do
    if test -f "$original"; then cp --parents "$original" "$run_dir/backup/"; fi
done
touch "$run_dir/backup/finished"
if ! command -v chronyd >/dev/null; then
    apt-get update
    apt-get -s install chrony > "$run_dir/package_plan.txt"
    python3 - "$run_dir/package_plan.txt" <<'PY'
import pathlib, sys
allowed = {'systemd-timesyncd','ntp','ntpsec'}
removed = {line.split()[1].split(':')[0] for line in pathlib.Path(sys.argv[1]).read_text().splitlines() if line.startswith('Remv ')}
if removed - allowed: raise SystemExit('Refusing unrelated package removal: '+str(sorted(removed-allowed)))
PY
    DEBIAN_FRONTEND=noninteractive apt-get -y install chrony
fi
chronyd -v > "$run_dir/chrony_version.txt"
conf="$run_dir/chrony.conf"
cat > "$conf" <<'CONF'
# UGRP shared clock. Only initial startup may step the clock.
driftfile /var/lib/chrony/chrony.drift
makestep 0.1 3
rtcsync
logdir /var/log/chrony
log tracking measurements statistics
bindcmdaddress 127.0.0.1
bindcmdaddress ::1
CONF
if test "$role" = leader; then
    printf 'pool 2.debian.pool.ntp.org iburst maxsources 4 minpoll 6 maxpoll 8\n' >> "$conf"
    printf 'bindaddress %s\nallow %s\nallow %s\n' "$leader_ip" "$client_ip" "$pc_ip" >> "$conf"
else
    printf 'server %s iburst minpoll 2 maxpoll 4\n' "$leader_ip" >> "$conf"
    printf 'port 0\n' >> "$conf"
fi
# Validate syntax without starting a daemon or changing the clock.
chronyd -p -f "$conf" > "$run_dir/validated_config.txt"
for unit in systemd-timesyncd ntp ntpsec; do
    if test "$(systemctl show "$unit" -p LoadState --value)" = loaded; then
        systemctl disable --now "$unit"
    fi
done
install -o root -g root -m 644 "$conf" /etc/chrony/chrony.conf
systemctl enable chrony
systemctl restart chrony
ready=0
chronyc waitsync 20 0.01 0 2 > "$run_dir/waitsync.txt" 2>&1 && ready=1
chronyc -n tracking > "$run_dir/after_tracking.txt"
chronyc -n sources -v > "$run_dir/after_sources.txt"
systemctl show chrony -p ActiveState -p UnitFileState > "$run_dir/after_service.txt"
timedatectl show -p NTPSynchronized -p NTP -p Timezone > "$run_dir/after_status.txt"
date -u --iso-8601=ns > "$run_dir/after_utc.txt"
dpkg-query -W chrony systemd-timesyncd > "$run_dir/after_packages.txt" 2>&1 || true
python3 - "$run_dir" "$role" "$leader_ip" "$ready" "$code_revision" <<'PY'
import datetime, hashlib, json, os, pathlib, socket, sys, time
out = pathlib.Path(sys.argv[1]); role = sys.argv[2]; leader = sys.argv[3]
sources = (out/'after_sources.txt').read_text()
selected = [line.split()[1] for line in sources.splitlines() if line.startswith('^*')]
tracking = (out/'after_tracking.txt').read_text()
normal = any(line.startswith('Leap status') and line.split(':',1)[1].strip() == 'Normal' for line in tracking.splitlines())
source_ok = bool(selected) and (role == 'leader' or leader in selected)
result = {'host':socket.gethostname(),'role':role,'leader_ip':leader,
 'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'monotonic_ns':time.monotonic_ns(),
 'source_revision':sys.argv[5],'configuration_applied':True,
 'ready':sys.argv[4]=='1' and normal and source_ok,'selected_sources':selected,
 'robot_motion_commands':0,'absolute_utc_guaranteed':False,
 'clock_check_scope':'chrony startup check; not a physical simultaneous-action test',
 'files_sha256':{str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file() and p.name != 'setup.log'}}
(out/'setup_result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
if not result['ready']: raise SystemExit('Configured, but not ready: inspect logs and do not schedule cooperative motion yet.')
PY
echo 'CLOCK SETUP READY; services remain enabled for ongoing synchronization.'
