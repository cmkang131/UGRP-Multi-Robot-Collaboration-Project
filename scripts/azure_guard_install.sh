#!/usr/bin/env bash
# Install after cloud budget/runbook/schedules have been verified, before jobs.
set -euo pipefail
SOURCE=${1:?path to committed source containing scripts/azure_idle_guard.py}
install -m 755 "$SOURCE/scripts/azure_idle_guard.py" /usr/local/bin/ugrp-azure-guard
install -d /usr/local/lib/ugrp-storage/scripts
install -m 644 "$SOURCE/scripts/__init__.py" /usr/local/lib/ugrp-storage/scripts/__init__.py
install -m 644 "$SOURCE/scripts/azure_shutdown.py" /usr/local/lib/ugrp-storage/scripts/azure_shutdown.py
install -m 644 "$SOURCE/scripts/azure_archive_native.py" /usr/local/lib/ugrp-storage/scripts/azure_archive_native.py
install -m 644 "$SOURCE/scripts/remote_run_finish.py" /usr/local/lib/ugrp-storage/scripts/remote_run_finish.py
mkdir -p /var/lib/ugrp-guard /home/ugrp/ugrp-sim/{src,runs,leases}
chown -R ugrp:ugrp /var/lib/ugrp-guard
chown -R ugrp:ugrp /home/ugrp/ugrp-sim
cat > /etc/systemd/system/ugrp-azure-guard.service <<'EOF'
[Unit]
Description=UGRP idle/8-hour Azure deallocation guard
After=network-online.target
[Service]
Type=oneshot
User=ugrp
TimeoutStartSec=720
EnvironmentFile=-/etc/ugrp/archive-native.env
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
cat > /etc/systemd/system/ugrp-azure-recover.service <<'EOF'
[Unit]
Description=Retry unarchived Azure evidence after boot
After=network-online.target home-ugrp-ugrp\x2dsim-arm.mount
Wants=network-online.target home-ugrp-ugrp\x2dsim-arm.mount
[Service]
Type=oneshot
User=ugrp
TimeoutStartSec=660
EnvironmentFile=-/etc/ugrp/archive-native.env
ExecStart=/usr/bin/python3 /usr/local/lib/ugrp-storage/scripts/azure_shutdown.py recover --reason boot_recovery
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable ugrp-azure-recover.service
systemctl enable --now ugrp-azure-guard.timer
systemctl start ugrp-azure-guard.service
# Existing Azure VM had a separate 15-minute guard that ignores batch leases.
# Keep its definition/data, but prevent it from interrupting verified archival.
if systemctl cat ugrp-azure-idle-guard.timer >/dev/null 2>&1; then
  systemctl disable --now ugrp-azure-idle-guard.timer
fi
# This VM also retained the retired always-restarting GPU worker supervisor.
# CPU jobs run from committed source via sim_cli; keep its files, stop its unit.
if systemctl cat ugrp-sim-worker.service >/dev/null 2>&1; then
  systemctl disable --now ugrp-sim-worker.service
fi
