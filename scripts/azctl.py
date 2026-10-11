"""Explicit-subscription lifecycle wrapper; start fails closed on safety/cost checks."""
import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.azure_api import ACCOUNT, BASE, RG, SUB, SUBS, VM, Arm

EXPIRY = dt.datetime(2026, 11, 18, 15, tzinfo=dt.timezone.utc)


def az(*args):
    return subprocess.run(['az', *args, '--subscription', SUB, '--only-show-errors'], check=True)


def safety(arm):
    api = '?api-version=2024-10-23'
    runbook = arm.request('GET', ACCOUNT + '/runbooks/Stop-UgrpVMs' + api)['properties']
    if runbook['state'] != 'Published':
        raise RuntimeError('Stop runbook is not published')
    group = arm.request('GET', BASE + '/providers/Microsoft.Insights/actionGroups/ugrp-credit-stop?api-version=2021-09-01')['properties']
    if not group['enabled'] or not group.get('automationRunbookReceivers'):
        raise RuntimeError('Budget action is not enabled')
    for schedule in ('credit-expiry-kst', 'hourly-credit-check'):
        data = arm.request('GET', ACCOUNT + f'/schedules/{schedule}' + api)['properties']
        if not data['isEnabled']:
            raise RuntimeError('Safety schedule disabled: ' + schedule)
    budget = arm.request('GET', f'/subscriptions/{SUB}/providers/Microsoft.CostManagement/budgets/ugrp-credit-20261011?api-version=2025-03-01')['properties']
    if not any(n.get('enabled') and n.get('contactGroups') for n in budget['notifications'].values()):
        raise RuntimeError('Budget does not trigger automation')
    total = sum(arm.cost_usd(sub) for sub in SUBS)
    if total >= 150:
        raise RuntimeError(f'Cumulative cost ${total:.2f} reached early stop threshold')
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['status', 'start', 'stop', 'resize'])
    parser.add_argument('--size', default='Standard_D16as_v5')
    args = parser.parse_args()
    if args.action == 'status':
        az('vm', 'get-instance-view', '-g', RG, '-n', VM, '--query',
           '{size:hardwareProfile.vmSize,status:instanceView.statuses}', '-o', 'json')
    elif args.action == 'stop':
        # Refuse to kill another job; VM-local guards still enforce the hard cap.
        arm = Arm()
        view = arm.request('GET', BASE + f'/providers/Microsoft.Compute/virtualMachines/{VM}/instanceView?api-version=2024-11-01')
        if any(s['code'] == 'PowerState/deallocated' for s in view['statuses']):
            print('Already deallocated')
            return
        running = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            'azure', "find ~/ugrp-sim/runs -mindepth 1 -maxdepth 1 -type d -exec sh -c 'test -f \"$1/EXIT\" || echo \"$1\"' sh {} \\; ; find ~/ugrp-sim/leases -type f -mmin -2 -print"],
            capture_output=True, text=True)
        if running.returncode:
            raise RuntimeError('Cannot verify remote jobs; stop refused (cloud and VM guards remain active)')
        if running.stdout.strip():
            print('Other unfinished runs/leases; deallocation deferred: ' + running.stdout.strip())
            return
        az('vm', 'deallocate', '-g', RG, '-n', VM)
    elif args.action == 'resize':
        arm = Arm()
        data = arm.request('GET', BASE + f'/providers/Microsoft.Compute/virtualMachines/{VM}/instanceView?api-version=2024-11-01')
        if not any(s['code'] == 'PowerState/deallocated' for s in data['statuses']):
            raise RuntimeError('Resize requires deallocated VM')
        az('vm', 'resize', '-g', RG, '-n', VM, '--size', args.size)
    else:
        if dt.datetime.now(dt.timezone.utc) >= EXPIRY:
            raise RuntimeError('Credit expired; start refused')
        total = safety(Arm())
        print(f'Safety resources enabled; cumulative CostUSD={total:.4f}', flush=True)
        az('vm', 'start', '-g', RG, '-n', VM)


if __name__ == '__main__':
    main()
