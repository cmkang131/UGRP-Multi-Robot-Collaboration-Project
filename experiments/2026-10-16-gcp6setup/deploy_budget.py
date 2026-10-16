"""Replay the committed gcp4 budget procedure into gcp6 only, preserving originals."""
import json
from pathlib import Path
from ops import ROOT, PROJECT, cloud

reference = ROOT.parent / '2026-10-16-gcp4setup/evidence'
number = json.loads((ROOT/'evidence/project.json').read_text())['projectNumber']
billing = json.loads((ROOT/'evidence/billing.json').read_text())
assert billing['billingEnabled'] and billing['billingAccountName'] == 'billingAccounts/010CD7-4B991B-84AAC7'
assert json.loads((ROOT/'evidence/instances-before.json').read_text()) == []
# Only fresh gcp6 resources are changed; no cross-project API calls are allowed by ops.cloud.
for name in ['enable-services','topic-create','sa-create','stopper-compute-retry','stopper-eventarc',
             'stopper-invoke','build-builder','pubsub-identity','pubsub-token',
             'budget-publisher-corrected','function-deploy','budget-create','test-vm-create']:
    command = json.loads((reference/(name+'-command.json')).read_text())['command']
    args = command[1:command.index('--account')]
    args = [x.replace('ugrp-sim-d-1016', PROJECT).replace('298701037365', number)
            .replace('gcp4', 'gcp6').replace('01C770-8A2F1F-63BA5F', '010CD7-4B991B-84AAC7') for x in args]
    if name == 'function-deploy':
        args = ['--source='+str(ROOT/'function') if x.startswith('--source=') else x for x in args]
    cloud(name, *args)
