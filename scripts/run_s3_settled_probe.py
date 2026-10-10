"""Frozen S3 quantization/settling probe, Oracle x86 only, <=60 SIM seconds."""
import argparse
import dataclasses
import hashlib
import json
from types import SimpleNamespace
from pathlib import Path

from harness.zone_final_pair_binding import bind
from harness.zone_s3_settled_servo import Options, OPTION, attach_endpoint, attach_solo
from scripts import run_s3_x86_probe as stage

BUNDLE_ID = 'zone-s3-settled-servo-probe-v159'
WORKFLOW_VERSION = '7.52.0'
WORKFLOW = 'configs/simulation_workflows.d/s3_settled_servo_probe_v159.json'


def bundle(sha, case, condition, options, cap=60.):
    if cap not in (5., 60.):
        raise ValueError('only pathcheck5 or registered60 allowed')
    b = stage.bundle(sha, case, condition=condition)
    b.update(execution_bundle_id=BUNDLE_ID, workflow_version=WORKFLOW_VERSION,
        schema='ugrp.s3_settled_probe.v159', servo_option=OPTION,
        settled_servo=dataclasses.asdict(options), cap_sim_s=cap,
        concurrent_probe_limit=10, stop_after_close=False,
        stage_scope='align-hover-descent-close-lift-carry',
        qualification='existing calibrated primitives only; rejected v158 model unused')
    from harness.python_source_closure import source_closure
    paths=set(source_closure(stage.ROOT,['scripts/run_s3_settled_probe.py']))
    paths.update((WORKFLOW, 'experiments/2026-10-10-s3-settled-servo/README.md',
                  'experiments/2026-10-10-s3-settled-servo/batch-plan.json'))
    b['source_sha256'].update({p:hashlib.sha256((stage.ROOT/p).read_bytes()).hexdigest() for p in paths})
    return b


def run(b, out):
    options=Options(**b['settled_servo'])
    def enter(rt, now, ignored):
        eps=stage.previous.enter_pair(rt,now,'off')
        for ep in eps.values():
            attach_endpoint(ep,options)
        return eps
    def configure(own, ignored):
        return attach_solo(own,options)
    # stage.run rebinds this function's globals; keep a real FunctionType.
    probe_run=bind(stage.previous.run,CAP=b['cap_sim_s'])
    probe_run.__kwdefaults__={**probe_run.__kwdefaults__, 'solo_configure':configure}
    previous=SimpleNamespace(**{**vars(stage.previous), 'enter_pair':enter, 'run':probe_run})
    result=bind(stage.run,previous=previous)(b,out)
    environment=json.loads((out/'environment.json').read_text())
    environment['concurrent_probe_limit']=10
    stage.previous.write(out/'environment.json',environment)
    stage.previous.artifact_manifest(out)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--condition',type=int,choices=range(6),default=0)
    p.add_argument('--case',choices=('pair','cyan'),default='pair')
    p.add_argument('--path-check',action='store_true')
    for name in dataclasses.asdict(Options()):
        p.add_argument('--'+name.replace('_','-'),action='store_true')
    p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute:
        print(json.dumps(dict(execution_started=False,bundle_id=BUNDLE_ID,host='oracle-x86')))
        return 0
    stage.archive_guard(a.expected_source_sha,a.output)
    options=Options(**{k:getattr(a,k) for k in dataclasses.asdict(Options())})
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:
        r=run(bundle(a.expected_source_sha,a.case,a.condition,options,5. if a.path_check else 60.),a.output)
    finally:
        undo()
    print(json.dumps(r));return int(r['status']=='HOST_ERROR')


if __name__=='__main__':raise SystemExit(main())
