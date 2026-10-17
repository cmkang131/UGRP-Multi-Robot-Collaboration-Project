"""Finite native evaluation-interface probe; repeats one already-issued hold.

No policy inference/training or task-success claim. The extra GT file must not
change the public observation whitelist or expose a training lane.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from act16w_runtime import require_gcp2, frozen_source
from act16w_eval_rpc import EvaluationClient

B = Path('/home/ugrp/ugrp-sim')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--enabled', action='store_true')
    p.add_argument('--seed', type=int, default=86827)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if not args.enabled or not 86820 <= args.seed <= 86864:
        p.error('explicit single TRAIN-state interface probe only')
    host = require_gcp2(training=True)
    source = frozen_source(Path(__file__).resolve().parents[1])
    refs = B/'runs/act16w-resume2-record-references'
    plans = json.loads((refs/'plans.json').read_text())['episodes']
    index = next(i for i, plan in enumerate(plans) if plan['seed'] == args.seed)
    compiled = json.loads((refs/'inventory.json').read_text())[index]
    receipt = json.loads((B/'runs/act16w-capacity-receipt.json').read_text())
    now = datetime.now(timezone.utc)
    if datetime.fromisoformat(receipt['valid_until_utc']) < now:
        raise ValueError('fresh cross-host capacity receipt required')
    count = int(receipt['foreign_cpu_worlds'])
    count += sum(int(json.loads(path.read_text()).get('concurrency', 0))
                 for path in (B/'leases').glob('*.json'))
    if count + 1 > 40:
        raise ValueError('global40-world cap')
    lease = B/'leases/act16w-instance-probe.json'
    with lease.open('x') as stream:
        json.dump(dict(task='act16w-instance-probe', pid=os.getpid(), start=now.isoformat(),
                       expected_end=(now+timedelta(minutes=2)).isoformat(), concurrency=1), stream)
    client = None
    report = dict(status='running', source_sha=source, host=host, seed=args.seed,
                  policy_inference=False, research_optimizer_steps=0, task_success_claim=False)
    try:
        client = EvaluationClient(python=B/'runs/simalt3/warp-env/bin/python',
            qualified_source=B/'src/f0db6b1abb842ea65b71c433738210254f300a7c',
            teacher_source=B/'src/warp1-teacher-snapshot-6f057f7e',
            qualification=B/'runs/warp3/teacher-gate-qualification-r1.json',
            references=refs/'per-world-references.json', compiled_reference=compiled['actuator'],
            compiled_geometry=compiled['geometry'], out=args.out, nworld=1, enabled=True)
        client.reset([plans[index]])
        sys.path.insert(0, str(B/'src/3f99d58c5ada0862e669ef4065c0ba957f1b4547'))
        from harness.grasp_act_contract import FIELDS, validate_observation
        observation, _ = client.read_actor(0)
        validate_observation(observation)
        if set(observation) != FIELDS:
            raise ValueError('public observation changed')
        try:
            client.read_training(0)
        except RuntimeError:
            pass
        else:
            raise ValueError('privileged lane exposed')
        command = deepcopy(observation['issued'][-1])
        command['t'] = observation['t']
        client.step([dict(command=command, done=False)])
        updated, _ = client.read_actor(0)
        validate_observation(updated)
        if set(updated) != FIELDS or updated['issued'][-1] != command:
            raise ValueError('own issued history/whitelist changed')
        report.update(status='complete', completed_interface_checks=True, elapsed_SIM_s=.1,
                      repeated_initial_hold_commands=1, privileged_actor_inputs=0)
    except BaseException as error:
        report.update(status='HOST_ERROR', error=repr(error))
        raise
    finally:
        try:
            if client is not None:
                client.close('interface_probe_end')
            if args.out.exists():
                for name in ('initial-same-kind-visibility.json', 'same-kind-evaluation-audit.json'):
                    path = args.out/'owner'/name
                    if path.exists():
                        report[name] = json.loads(path.read_text())
                (args.out/'interface-probe-summary.json').write_text(json.dumps(report, indent=2)+'\n')
        finally:
            if lease.exists() and json.loads(lease.read_text()).get('pid') == os.getpid():
                lease.unlink()
    print(json.dumps(report))


if __name__ == '__main__':
    main()
