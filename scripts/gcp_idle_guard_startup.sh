#!/bin/bash
# UGRP GCP benchmark VM: idle guard. Powers off after 20 min with no simulation/setup process.
cat > /usr/local/sbin/ugrp-idle-guard <<'G'
#!/bin/bash
state=/run/ugrp-idle-since
now=$(date +%s)
if pgrep -f 'scripts\.sim_cli|gcp_speed_probe|pip install|pip3 install|apt-get|apt install|dpkg|git index-pack|git pack-objects|git reset|pytest|rsync|scp|sshd: ugrp|zstd|tar ' >/dev/null; then
  echo "$now" > "$state"; exit 0
fi
[ -f "$state" ] || echo "$now" > "$state"
since=$(cat "$state")
if [ $((now - since)) -ge 1200 ]; then
  logger -t ugrp-idle-guard "idle 20 min, shutting down"
  shutdown -h now
fi
G
chmod 755 /usr/local/sbin/ugrp-idle-guard
cat > /etc/systemd/system/ugrp-idle-guard.service <<'G'
[Unit]
Description=UGRP idle guard
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/ugrp-idle-guard
G
cat > /etc/systemd/system/ugrp-idle-guard.timer <<'G'
[Unit]
Description=UGRP idle guard timer
[Timer]
OnBootSec=60
OnUnitActiveSec=60
[Install]
WantedBy=timers.target
G
rm -f /run/ugrp-idle-since
systemctl daemon-reload
systemctl enable --now ugrp-idle-guard.timer
