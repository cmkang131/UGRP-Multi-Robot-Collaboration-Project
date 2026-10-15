"""Prepare carry6 plan and a fresh disabled GCP queue, never submit."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
from scripts.make_solo_carry_plan import prepare, queue, ROOT

PLAN = 'experiments/2026-10-15-map-carry-zone/diagnostic-plan-v6.json'


def prepare6():
    old = json.loads((ROOT/'experiments/2026-10-15-map-carry-zone/diagnostic-plan-v5.json').read_text())
    first = copy.deepcopy(old['episodes'][0])
    fresh = prepare(carry5=True, seed0=93260, count=7, kind_offset=1)['episodes']
    calibration = json.loads((ROOT/'experiments/2026-10-15-map-carry-zone/carry6-trim-calibration.json').read_text())
    for i, e in enumerate([first, *fresh]):
        e.update(batch='solo-carry-zone-v6', carry5_rank_aware_views_v1=True,
                 carry5_trim_yaw_calibration_v1=False, trim_calibration=calibration,
                 carry6_role='reproduction' if i == 0 else 'fresh_seed',
                 merge_with_previous_results=False)
    result = copy.deepcopy(old)
    result.update(schema='ugrp.solo_carry_plan.v6', episodes=[first, *fresh],
                  previous_results_combinable=False, calibration_enabled_in_queue=False,
                  seed_policy='93240 reproduction + 93260-93266 fresh; no previous results pooled')
    return result


def queue6(plan, sha):
    # Reuse current queue schema/command layout, not the old queue's approvals.
    bridge = {**plan, 'schema': 'ugrp.solo_carry_plan.v5'}
    value = queue(bridge, sha, 505, plan_path=PLAN)
    value.update(schema='ugrp.solo_carry_queue.v6', enabled=False, approved=False,
                 ready=False, stage_ready=False, status='prepared_not_submitted',
                 supersedes_blocked_queue='20261015-solo-carry-c6d2f5a4.json',
                 carry5_rank_aware_views_v1=True, carry5_trim_yaw_calibration_v1=False,
                 previous_results_combinable=False,
                 seed_reservation=dict(split='solo_carry_diagnostic_v1', reproduction=[93240],
                                       fresh=[93260,93266], remote_unused_verified=False))
    value['preconditions'] += [
        'C1 offline robust margin/rank gate is infeasible at saved93240 belief; exploratory body views only, no fix claim.',
        'C2 remains disabled: separate-run retrospective validation residual yaw9.13deg; approve separately before enabling.',
        'Source uses01703ed2 drive model; PR510 contact-loss7b223e30 is NOT integrated. Calibration hash forbids reuse after a drive change.']
    for obj in [value['coordinator_approval'], *value['runs'], *value['execution_stages']]:
        obj.update(approved=False, enabled=False, ready=False, stage_ready=False)
    return value


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');p.add_argument('--queue-out',type=Path)
    a=p.parse_args()
    if a.plan:
        with (ROOT/PLAN).open('x') as f:
            json.dump(prepare6(),f,separators=(',',':'));f.write('\n')
    if a.queue_out:
        sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        value=queue6(json.loads((ROOT/PLAN).read_text()),sha)
        with a.queue_out.open('x') as f:
            json.dump(value,f,indent=2);f.write('\n')
        print(json.dumps(dict(path=str(a.queue_out),sha=sha,sha256=hashlib.sha256(a.queue_out.read_bytes()).hexdigest())))

if __name__ == '__main__':
    main()
