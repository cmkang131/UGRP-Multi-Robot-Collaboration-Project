#!/usr/bin/env bash
# Root installer. Requires the VM's archive-only SSH identity to be authorized on ARM.
set -euo pipefail
SOURCE=${1:?committed source directory}
install -d /usr/local/lib/ugrp-storage/scripts
for module in __init__ storage_common storage_budget compress_json_traces worktree_guard; do
  install -m 644 "$SOURCE/scripts/$module.py" "/usr/local/lib/ugrp-storage/scripts/$module.py"
done
install -m 755 "$SOURCE/scripts/ugrp_auto_archive.sh" /usr/local/bin/ugrp-auto-archive
cat > '/etc/systemd/system/home-ugrp-ugrp\x2dsim-arm.mount' <<'EOF'
[Unit]
Description=UGRP ARM archive (SFTP only)
After=network-online.target
Wants=network-online.target
[Mount]
What=ugrparch@161.33.46.134:/runs
Where=/home/ugrp/ugrp-sim/arm
Type=fuse.sshfs
Options=_netdev,BatchMode=yes,IdentityFile=/home/ugrp/.ssh/id_ed25519_arm_archive,UserKnownHostsFile=/home/ugrp/.ssh/known_hosts,StrictHostKeyChecking=yes,allow_other,default_permissions,uid=1000,gid=1000,reconnect,ServerAliveInterval=15,ServerAliveCountMax=3
TimeoutSec=30
[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/ugrp-auto-archive.service <<'EOF'
[Unit]
Requires=home-ugrp-ugrp\x2dsim-arm.mount
After=home-ugrp-ugrp\x2dsim-arm.mount
[Service]
Type=oneshot
User=ugrp
Environment=UGRP_RUNS=/home/ugrp/ugrp-sim/runs
Environment=UGRP_ARCHIVE=/home/ugrp/ugrp-sim/arm
ExecStart=/usr/local/bin/ugrp-auto-archive
EOF
cat > /etc/systemd/system/ugrp-auto-archive.timer <<'EOF'
[Timer]
OnBootSec=5min
OnUnitActiveSec=10min
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable 'home-ugrp-ugrp\x2dsim-arm.mount'
systemctl enable --now ugrp-auto-archive.timer
