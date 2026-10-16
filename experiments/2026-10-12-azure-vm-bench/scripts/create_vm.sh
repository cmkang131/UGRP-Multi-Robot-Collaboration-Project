#!/bin/bash
# usage: create_vm.sh <short> <size> <scsi|nvme>
set -euo pipefail
S=88b7ee7f-f2f3-4a0d-a0ce-cf7306943676; RG=UGRP-SIM-RG; L=koreacentral
N=ugrp-vmbench-$1; SIZE=$2; CTRL=$3
SNAP=/subscriptions/$S/resourceGroups/UGRP-SIM-RG/providers/Microsoft.Compute/snapshots/ugrp-sim-azure2-source-20261012
SUBNET=/subscriptions/$S/resourceGroups/ugrp-sim-rg/providers/Microsoft.Network/virtualNetworks/ugrp-sim-vnet/subnets/worker
TAGS="owner=claude purpose=vm-bench-20261012 temporary=true"
az network nsg show -g $RG -n ugrp-vmbench-nsg --subscription $S -o none 2>/dev/null || {
  az network nsg create -g $RG -n ugrp-vmbench-nsg -l $L --tags $TAGS --subscription $S -o none
  az network nsg rule create -g $RG --nsg-name ugrp-vmbench-nsg -n allow-ssh-from-oracle --priority 1000 \
    --source-address-prefixes 161.33.46.134/32 --destination-port-ranges 22 --protocol Tcp --access Allow --direction Inbound --subscription $S -o none; }
az disk create -g $RG -n $N-os -l $L --source $SNAP --sku StandardSSD_LRS --hyper-v-generation V2 --os-type Linux --tags $TAGS --subscription $S -o none
az disk show -g $RG -n $N-os --subscription $S --query supportedCapabilities -o json
az network public-ip create -g $RG -n $N-ip -l $L --sku Standard --allocation-method Static --tags $TAGS --subscription $S -o none
az network nic create -g $RG -n $N-nic -l $L --subnet $SUBNET --network-security-group ugrp-vmbench-nsg --public-ip-address $N-ip --accelerated-networking true --tags $TAGS --subscription $S -o none
EXTRA=(); [ "$CTRL" = nvme ] && EXTRA=(--disk-controller-type NVMe)
az vm create -g $RG -n $N -l $L --size $SIZE --attach-os-disk $N-os --os-type linux --nics $N-nic \
  --security-type Standard --os-disk-delete-option Delete --nic-delete-option Delete --tags $TAGS "${EXTRA[@]}" --subscription $S -o json \
  --query "{power:powerState,ip:publicIpAddress,priv:privateIpAddress}"
az vm boot-diagnostics enable -g $RG -n $N --subscription $S -o none || true
az vm show -g $RG -n $N --subscription $S --query "{size:hardwareProfile.vmSize,identity:identity,ctrl:storageProfile.diskControllerType,sec:securityProfile}" -o json
