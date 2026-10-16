"""Replay the committed gcp3 budget procedure into gcp5 only, preserving originals."""
import json
from pathlib import Path
from ops import ROOT, PROJECT, cloud

reference = ROOT.parent / '2026-10-16-gcp3setup/evidence'
number = json.loads((ROOT/'evidence/project.json').read_text())['projectNumber']
billing = json.loads((ROOT/'evidence/billing.json').read_text())
assert billing['billingEnabled'] and billing['billingAccountName'] == 'billingAccounts/01C770-8A2F1F-63BA5F'
assert json.loads((ROOT/'evidence/instances-before.json').read_text()) == []
# Only fresh gcp5 resources are changed; no cross-project API calls are allowed by ops.cloud.
for name in ['enable-services','topic-create','sa-create','stopper-compute-retry','stopper-eventarc',
             'stopper-invoke','build-builder','pubsub-identity','pubsub-token',
             'budget-publisher-corrected','function-deploy','budget-create','test-vm-create']:
    command = json.loads((reference/(name+'-command.json')).read_text())['command']
    args = command[1:command.index('--account')]
    args = [x.replace('ugrp-sim-c-1016', PROJECT).replace('443356522325', number)
            .replace('gcp3', 'gcp5') for x in args]
    if name == 'function-deploy':
        args = ['--source='+str(ROOT/'function') if x.startswith('--source=') else x for x in args]
    cloud(name, *args)
