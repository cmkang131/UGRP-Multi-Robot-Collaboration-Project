"""ARM client: explicit subscription; credentials remain in process memory."""
import json
import subprocess
import urllib.error
import urllib.request

SUB = '88b7ee7f-f2f3-4a0d-a0ce-cf7306943676'
SUBS = [SUB, 'c02f839a-2a6b-49d8-9c9a-f3d9f09aa5ea']
RG = 'UGRP-SIM-RG'
VM = 'ugrp-sim-azure'
BASE = f'/subscriptions/{SUB}/resourceGroups/{RG}'
VM_ID = BASE + f'/providers/Microsoft.Compute/virtualMachines/{VM}'
ACCOUNT = BASE + '/providers/Microsoft.Automation/automationAccounts/ugrp-cost-guard'


class Arm:
    def __init__(self):
        result = subprocess.run(['az', 'account', 'get-access-token', '--subscription', SUB,
                                 '--resource', 'https://management.azure.com/', '-o', 'json'],
                                capture_output=True, text=True, check=True)
        self._token = json.loads(result.stdout)['accessToken']

    def request(self, method, path, body=None, *, raw=False):
        url = path if path.startswith('https://') else 'https://management.azure.com' + path
        if not url.startswith('https://management.azure.com/'):
            raise ValueError('Only ARM URLs are allowed')
        payload = body.encode() if raw else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(url, data=payload, method=method,
            headers={'Authorization': 'Bearer ' + self._token,
                     'Content-Type': 'text/powershell' if raw else 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                self.last_headers = dict(response.headers)
                content = response.read().decode()
                if not content:
                    return {}
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return content
        except urllib.error.HTTPError as exc:
            # Do not include request payloads, which can contain webhook secrets.
            content = exc.read().decode()
            try:
                error = json.loads(content).get('error', {})
                code = error.get('code', 'Unknown')
                message = error.get('message', '')[:350] if not raw else ''
            except ValueError:
                code, message = 'Unknown', ''
            raise RuntimeError(f'ARM HTTP {exc.code}: {code} {message}') from None

    def cost_usd(self, sub):
        data = self.request('POST', f'/subscriptions/{sub}/providers/Microsoft.CostManagement/query?api-version=2025-03-01',
            {'type': 'ActualCost', 'timeframe': 'Custom',
             'timePeriod': {'from': '2026-10-01T00:00:00Z', 'to': '2026-11-19T00:00:00Z'},
             'dataset': {'granularity': 'None', 'aggregation': {'usd': {'name': 'CostUSD', 'function': 'Sum'}}}})['properties']
        names = [c['name'] for c in data['columns']]
        if data.get('nextLink') or 'CostUSD' not in names:
            raise RuntimeError('Incomplete cost response')
        return sum(float(r[names.index('CostUSD')]) for r in data['rows'])
