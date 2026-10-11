#!/usr/bin/env bash
# Install after cloud budget/runbook/schedules have been verified, before jobs.
set -euo pipefail
SOURCE=${1:?path to committed source containing scripts/azure_idle_guard.py}
install -m 755 "$SOURCE/scripts/azure_idle_guard.py" /usr/local/bin/ugrp-azure-guard
mkdir -p /var/lib/ugrp-guard /home/ugrp/ugrp-sim/{src,runs,leases}
chown -R ugrp:ugrp /home/ugrp/ugrp-sim
cat > /etc/systemd/system/ugrp-azure-guard.service <<'EOF'
[Unit]
Description=UGRP idle/8-hour Azure deallocation guard
After=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/bin/ugrp-azure-guard
EOF
cat > /etc/systemd/system/ugrp-azure-guard.timer <<'EOF'
[Unit]
Description=Check Azure deallocation every minute
[Timer]
OnBootSec=60
OnUnitActiveSec=60
AccuracySec=5
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now ugrp-azure-guard.timer
systemctl start ugrp-azure-guard.service
# Existing Azure VM had a separate 15-minute guard that ignores batch leases.
# Keep its definition/data, but prevent it from interrupting verified archival.
if systemctl cat ugrp-azure-idle-guard.timer >/dev/null 2>&1; then
  systemctl disable --now ugrp-azure-idle-guard.timer
fi
