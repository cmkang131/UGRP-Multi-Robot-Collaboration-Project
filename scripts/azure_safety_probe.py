"""Inspect safety jobs or trigger the authorized Action Group deallocation test."""
import argparse
import json
from pathlib import Path
import uuid
from urllib.parse import urlsplit

from azure_api import ACCOUNT, BASE, SUBS, Arm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('jobs', 'test-action', 'test-cost', 'job', 'test-status'))
    parser.add_argument('--id')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    arm = Arm()
    api = '?api-version=2024-10-23'
    if args.action == 'test-action':
        group = BASE + '/providers/Microsoft.Insights/actionGroups/ugrp-credit-stop'
        data = arm.request('GET', group + '?api-version=2021-09-01')['properties']
        # serviceUri is a secret; it stays in memory and must not be printed.
        result = arm.request('POST', group + '/createNotifications?api-version=2021-09-01',
            {'alertType': 'actualcostbudget', 'automationRunbookReceivers': data['automationRunbookReceivers'],
             'emailReceivers': data['emailReceivers']})
        location = arm.last_headers.get('Location', arm.last_headers.get('location'))
        result = {'accepted': True, 'status_path': urlsplit(location).path + '?api-version=2021-09-01'}
    elif args.action == 'test-cost':
        job = str(uuid.uuid4())
        arm.request('PUT', ACCOUNT + f'/jobs/{job}' + api,
            {'properties': {'runbook': {'name': 'Stop-UgrpVMs'}, 'parameters': {'Mode': 'Cost'}}})
        result = {'job_id': job}
    elif args.action == 'job':
        status = arm.request('GET', ACCOUNT + f'/jobs/{args.id}' + api)['properties']
        output = arm.request('GET', ACCOUNT + f'/jobs/{args.id}/output' + api)
        result = {'status': status['status'], 'exception': status.get('exception'), 'output': output}
    elif args.action == 'test-status':
        result = arm.request('GET', args.id)
    else:
        data = arm.request('GET', ACCOUNT + '/jobs' + api)['value']
        result = [{'id': j['name'], 'status': j['properties']['status'],
                   'start': j['properties'].get('startTime')} for j in data]
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(rendered + '\n')
    print(rendered)


if __name__ == '__main__':
    main()
