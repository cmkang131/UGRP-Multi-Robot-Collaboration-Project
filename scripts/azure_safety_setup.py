"""Deploy authorized UGRP cost safety resources in subscription 88b7ee7f only.

Webhook capability URLs are generated and passed through memory, never files.
Re-running intentionally rotates the action-group webhook; schedules use fixed IDs.
"""
import datetime as dt
import argparse
import json
from pathlib import Path
import uuid
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.azure_api import ACCOUNT, BASE, RG, SUB, SUBS, VM_ID, Arm

API = '?api-version=2024-10-23'
RUNBOOK = ACCOUNT + '/runbooks/Stop-UgrpVMs'
GROUP = BASE + '/providers/Microsoft.Insights/actionGroups/ugrp-credit-stop'
ROLE_ID = '7b327b09-c7ad-5fea-a260-6a079521da91'
BILLING = '/providers/Microsoft.Billing/billingAccounts/ac7160ea-2fe4-5090-e725-a1cb7cf051e4:0cb190e6-7889-4867-b734-53aa504234b7_2019-05-31/billingProfiles/MINB-TPIA-BG7-PGB'


def runbook_content():
    folder = Path(__file__).parent
    source = (folder / 'azure_shutdown.py').read_text().replace('sys.exit(main())',
        "sys.argv += ['--grace-seconds', '540']; sys.exit(main())")
    return (folder / 'azure_stop_vms.ps1').read_text().replace('__UGRP_SHUTDOWN_SOURCE__', source)


def publish_runbook(arm):
    # Updates only existing runbook content, preserving webhook, RBAC and schedules.
    arm.request('PUT', RUNBOOK + '/draft/content' + API, runbook_content(), raw=True)
    arm.request('POST', RUNBOOK + '/publish' + API)
    actual = arm.request('GET', RUNBOOK + '/content' + API)
    state = arm.request('GET', RUNBOOK + API)['properties']['state']
    if actual != runbook_content() or state != 'Published':
        raise RuntimeError('Published runbook readback mismatch')


def command_permissions(arm, principal):
    # Both identities receive only managed Run Command on this one VM.
    # Existing cross-subscription cost/deallocation roles are untouched.
    vm_principal = arm.request('GET', VM_ID + '?api-version=2024-11-01')['identity']['principalId']
    role = f'/subscriptions/{SUB}/providers/Microsoft.Authorization/roleDefinitions/{uuid.uuid5(uuid.NAMESPACE_URL, ACCOUNT + "/graceful-command-role")}'
    arm.request('PUT', role + '?api-version=2022-04-01', {'properties': {
        'roleName': 'UGRP Graceful VM Stop Command',
        'description': 'Managed run command read/write on the UGRP VM only.',
        'type': 'CustomRole', 'assignableScopes': [BASE],
        'permissions': [{'actions': ['Microsoft.Compute/virtualMachines/runCommands/write',
            'Microsoft.Compute/virtualMachines/runCommands/read'], 'notActions': []}]}})
    for who in (principal, vm_principal):
        name = uuid.uuid5(uuid.NAMESPACE_URL, VM_ID + who + role)
        arm.request('PUT', VM_ID + f'/providers/Microsoft.Authorization/roleAssignments/{name}?api-version=2022-04-01',
            {'properties': {'roleDefinitionId': role, 'principalId': who, 'principalType': 'ServicePrincipal'}})


def daily_schedule(arm):
    start = (dt.datetime.now(dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=9)))
             .replace(hour=0, minute=0, second=0, microsecond=0) + dt.timedelta(days=1)).isoformat()
    arm.request('PUT', ACCOUNT + '/schedules/daily-backup-kst' + API, {'properties': {
        'startTime': start, 'frequency': 'Day', 'interval': 1, 'timeZone': 'Asia/Seoul', 'isEnabled': True}})
    job = uuid.uuid5(uuid.NAMESPACE_URL, ACCOUNT + 'daily-backup-kst')
    arm.request('PUT', ACCOUNT + f'/jobSchedules/{job}' + API,
        {'properties': {'schedule': {'name': 'daily-backup-kst'}, 'runbook': {'name': 'Stop-UgrpVMs'},
                        'parameters': {'Mode': 'Daily'}}})
    arm.request('PUT', BASE + '/providers/Microsoft.DevTestLab/schedules/shutdown-computevm-ugrp-sim-azure?api-version=2018-09-15',
        {'location': 'koreacentral', 'properties': {'status': 'Disabled', 'taskType': 'ComputeVmShutdownTask',
            'dailyRecurrence': {'time': '0000'}, 'timeZoneId': 'Korea Standard Time', 'targetResourceId': VM_ID,
            'notificationSettings': {'status': 'Disabled', 'timeInMinutes': 30}}})
    print('Lease-aware midnight backup linked; unconditional DevTest shutdown disabled', flush=True)


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--runbook-only', action='store_true')
    mode.add_argument('--lifecycle-only', action='store_true',
                      help='existing VM command permissions/runbook/daily schedule; no webhook rotation or VM start')
    args = parser.parse_args()
    arm = Arm()
    if args.runbook_only:
        publish_runbook(arm)
        print('Existing runbook content updated; no VM/RBAC/schedule changes', flush=True)
        return
    if args.lifecycle_only:
        principal = arm.request('GET', ACCOUNT + API)['identity']['principalId']
        command_permissions(arm, principal)
        publish_runbook(arm)
        daily_schedule(arm)
        return
    for sub in SUBS:
        vms = arm.request('GET', f'/subscriptions/{sub}/providers/Microsoft.Compute/virtualMachines?api-version=2024-11-01')['value']
        for vm in vms:
            view = arm.request('GET', vm['id'] + '/instanceView?api-version=2024-11-01')
            if not any(s['code'] == 'PowerState/deallocated' for s in view['statuses']):
                raise RuntimeError('Safety deployment requires all VMs deallocated; webhook rotation would leave a gap')
    account = arm.request('PUT', ACCOUNT + API, {'location': 'koreacentral',
        'identity': {'type': 'SystemAssigned'}, 'properties': {'sku': {'name': 'Basic'}}})
    principal = account['identity']['principalId']
    print('Automation account identity:', principal, flush=True)
    role = f'/subscriptions/{SUB}/providers/Microsoft.Authorization/roleDefinitions/{ROLE_ID}'
    arm.request('PUT', role + '?api-version=2022-04-01', {'properties': {
        'roleName': 'UGRP VM Deallocator', 'description': 'Read and deallocate VMs only; no create, start, resize or delete.',
        'type': 'CustomRole', 'assignableScopes': [f'/subscriptions/{s}' for s in SUBS],
        'permissions': [{'actions': ['Microsoft.Compute/virtualMachines/read',
            'Microsoft.Compute/virtualMachines/instanceView/read',
            'Microsoft.Compute/virtualMachines/deallocate/action'], 'notActions': []}]}})
    command_permissions(arm, principal)
    cost_role = f'/subscriptions/{SUB}/providers/Microsoft.Authorization/roleDefinitions/72fafb9e-0641-4937-9268-a91bfd8191a3'
    for scope, who, role_ref in [(f'/subscriptions/{s}', principal, r) for s in SUBS for r in (role, cost_role)] + [
        (VM_ID, '201eb390-599d-4c95-9e66-78874e25f04e', role)]:
        name = uuid.uuid5(uuid.NAMESPACE_URL, scope + who + role_ref)
        arm.request('PUT', scope + f'/providers/Microsoft.Authorization/roleAssignments/{name}?api-version=2022-04-01',
            {'properties': {'roleDefinitionId': role_ref, 'principalId': who, 'principalType': 'ServicePrincipal'}})
    print('Minimum deallocate permissions + cost reader assigned', flush=True)
    arm.request('PUT', RUNBOOK + API, {'location': 'koreacentral', 'properties': {
        'runbookType': 'PowerShell', 'logProgress': False, 'logVerbose': False, 'draft': {}}})
    publish_runbook(arm)
    print('Runbook published', flush=True)
    hook = ACCOUNT + '/webhooks/credit-stop'
    try:
        arm.request('DELETE', hook + API)
    except RuntimeError as exc:
        if 'HTTP 404' not in str(exc):
            raise
    uri = arm.request('POST', ACCOUNT + '/webhooks/generateUri' + API)
    arm.request('PUT', hook + API, {'properties': {'isEnabled': True, 'expiryTime': '2026-11-19T15:00:00Z',
        'uri': uri, 'runbook': {'name': 'Stop-UgrpVMs'}, 'parameters': {'Mode': 'Force'}}})
    arm.request('PUT', GROUP + '?api-version=2021-09-01', {'location': 'global', 'properties': {
        'enabled': True, 'groupShortName': 'UGRP-stop',
        'emailReceivers': [{'name': 'owner', 'emailAddress': 'kcm0127@gmail.com', 'useCommonAlertSchema': False}],
        'automationRunbookReceivers': [{'name': 'stop-all', 'automationAccountId': ACCOUNT,
            'runbookName': 'Stop-UgrpVMs', 'webhookResourceId': hook, 'isGlobalRunbook': False,
            'serviceUri': uri, 'useCommonAlertSchema': False}]}})
    del uri
    # The billing profile is KRW. Observed Azure Cost / CostUSD was 1364.75.
    # Use 1360 conservatively for native budget emails; hourly checks use CostUSD.
    for scope, name in [(f'/subscriptions/{SUB}', 'ugrp-credit-20261011'), (BILLING, 'ugrp-shared-credit-20261011')]:
        notices = {}
        for dollars in (50, 100, 150, 160):
            notice = {'enabled': True, 'operator': 'GreaterThanOrEqualTo', 'thresholdType': 'Actual',
                'threshold': dollars / 160 * 100, 'contactEmails': ['kcm0127@gmail.com']}
            if scope.startswith('/subscriptions/') and dollars >= 150:
                notice['contactGroups'] = [GROUP]
            notices[f'USD{dollars}-approx-KRW'] = notice
        arm.request('PUT', scope + f'/providers/Microsoft.CostManagement/budgets/{name}?api-version=2025-03-01',
            {'properties': {'category': 'Cost', 'amount': 217600, 'timeGrain': 'Quarterly',
                'timePeriod': {'startDate': '2026-10-01T00:00:00Z', 'endDate': '2027-01-01T00:00:00Z'},
                'notifications': notices}})
        print('Budget created:', name, flush=True)
    first = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)).isoformat()
    for name, props, mode in [
        ('credit-expiry-kst', {'startTime': '2026-11-18T15:00:00Z', 'frequency': 'OneTime', 'timeZone': 'Asia/Seoul'}, 'Force'),
        ('hourly-credit-check', {'startTime': first, 'expiryTime': '2026-11-18T15:00:00Z', 'frequency': 'Hour', 'interval': 1, 'timeZone': 'UTC'}, 'Cost')]:
        arm.request('PUT', ACCOUNT + f'/schedules/{name}' + API, {'properties': props})
        job = uuid.uuid5(uuid.NAMESPACE_URL, ACCOUNT + name)
        arm.request('PUT', ACCOUNT + f'/jobSchedules/{job}' + API,
            {'properties': {'schedule': {'name': name}, 'runbook': {'name': 'Stop-UgrpVMs'}, 'parameters': {'Mode': mode}}})
        print('Schedule linked:', name, flush=True)
    daily_schedule(arm)


if __name__ == '__main__':
    main()
