"""Stop every Compute Engine VM in the project once net cost (after credits) reaches the budget.

Budget: billing-account budget scoped to this project, credits included, so costAmount is the
amount actually charged beyond credits. Pattern from Google Cloud docs
"Examples of automated cost control responses" (cap / stop resources on budget notification).
"""
import base64
import json
import os

import functions_framework
from google.cloud import compute_v1

PROJECT = os.environ["TARGET_PROJECT"]


@functions_framework.cloud_event
def stop_on_budget(event):
    data = json.loads(base64.b64decode(event.data["message"]["data"]).decode())
    cost, budget = float(data["costAmount"]), float(data["budgetAmount"])
    print(json.dumps({"costAmount": cost, "budgetAmount": budget, "currency": data.get("currencyCode")}))
    if cost < budget:
        return
    client = compute_v1.InstancesClient()
    stopped = []
    for zone, scoped in client.aggregated_list(project=PROJECT):
        for inst in scoped.instances or []:
            if inst.status in ("RUNNING", "PROVISIONING", "STAGING"):
                client.stop(project=PROJECT, zone=zone.split("/")[-1], instance=inst.name)
                stopped.append(inst.name)
    print(json.dumps({"action": "stop_all", "stopped": stopped}))
