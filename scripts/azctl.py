"""Explicit-subscription lifecycle wrapper; start fails closed on safety/cost checks."""
import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path
import sys
import time

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.azure_api import ACCOUNT, AZURE_HOSTS, BASE, RG, SUB, SUBS, VM, Arm, vm_target

EXPIRY = dt.datetime(2026, 11, 18, 15, tzinfo=dt.timezone.utc)


def guest(action, host='azure'):
    return subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', host,
        'python3 /usr/local/lib/ugrp-storage/scripts/azure_shutdown.py ' + action],
        capture_output=True, text=True, timeout=660)


def recover(host='azure'):
    for attempt in range(12):
        ready = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', host, 'true'], capture_output=True)
        if ready.returncode == 0:
            break
        time.sleep(5)
    else:
        raise RuntimeError('SSH unavailable; boot recovery will retry, admission refused')
    result = guest('recover --reason start_recovery', host)
    if result.returncode:
        raise RuntimeError('Recovery helper failed; new execution refused')
    from scripts.remote_run import fetch_lifecycle
    fetch_lifecycle(host)


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
    parser.add_argument('--vm', choices=AZURE_HOSTS.values())
    parser.add_argument('--host', choices=AZURE_HOSTS)
    args = parser.parse_args()
    vm, host = vm_target(args.vm, args.host)
    if args.action == 'status':
        az('vm', 'get-instance-view', '-g', RG, '-n', vm, '--query',
           '{size:hardwareProfile.vmSize,status:instanceView.statuses}', '-o', 'json')
    elif args.action == 'stop':
        # Refuse to kill another job; VM-local guards still enforce the hard cap.
        arm = Arm()
        view = arm.request('GET', BASE + f'/providers/Microsoft.Compute/virtualMachines/{vm}/instanceView?api-version=2024-11-01')
        if any(s['code'] == 'PowerState/deallocated' for s in view['statuses']):
            print('Already deallocated')
            return
        running = guest('status', host)
        from scripts.remote_run import fetch_lifecycle
        fetch_lifecycle(host)
        if running.returncode == 75:
            print('Unarchived runs/leases; deallocation deferred: ' + running.stdout.strip())
            return
        if running.returncode:
            raise RuntimeError('Cannot verify remote jobs; stop refused (cloud and VM guards remain active)')
        az('vm', 'deallocate', '-g', RG, '-n', vm)
    elif args.action == 'resize':
        arm = Arm()
        data = arm.request('GET', BASE + f'/providers/Microsoft.Compute/virtualMachines/{vm}/instanceView?api-version=2024-11-01')
        if not any(s['code'] == 'PowerState/deallocated' for s in data['statuses']):
            raise RuntimeError('Resize requires deallocated VM')
        az('vm', 'resize', '-g', RG, '-n', vm, '--size', args.size)
    else:
        if dt.datetime.now(dt.timezone.utc) >= EXPIRY:
            raise RuntimeError('Credit expired; start refused')
        total = safety(Arm())
        print(f'Safety resources enabled; cumulative CostUSD={total:.4f}', flush=True)
        az('vm', 'start', '-g', RG, '-n', vm)
        recover(host)


if __name__ == '__main__':
    main()
