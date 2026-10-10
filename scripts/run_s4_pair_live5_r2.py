"""v167 stage admission restores the same own-only phase history as S3 v165."""
import argparse
import json
import os
from pathlib import Path
from scripts import run_s4_pair_live5 as old
from harness.zone_final_pair_binding import bind
from harness.python_source_closure import source_closure

ROOT=old.ROOT
RECORD=old.RECORD
PLAN=RECORD+'/README.md'
BUNDLE_ID='zone-s4-pair-live-v167'
VERSION='7.60.0'
WORKFLOW='configs/simulation_workflows.d/s4_pair_live_v167.json'


def admit(rid,ep,now):
    from scripts import run_s3_alignment_probe as stage
    history=json.loads((ROOT/stage.PHASE).read_text())
    if history['source_t']!=stage.STAGE_T:raise ValueError('saved own phase mismatch')
    # Same upstream stage receipt/history, never a truth pose or old success.
    ep.controller.driver.outcome='arrived'
    stage.resume_alignment_phase(ep,now,history['robots'][rid],stage.STAGE_T)
    old.admit(rid,ep,now)


class Extension(old.Extension):
    def driver(self,host,runtime):
        return old.pair.Driver(host,runtime,on_admit=admit)


def bundle(source_sha,condition):
    b=old.bundle(source_sha,condition)
    r=json.loads((ROOT/RECORD/'release-r2.json').read_text())
    assert r['execution_bundle_id']==BUNDLE_ID and r['workflow_version']==VERSION
    for p,h in r['s3_file_sha256'].items():
        if old.sha(ROOT/p)!=h:raise ValueError('S3 v165 phase/source changed: '+p)
    b.update(schema='ugrp.s4_pair_live.v167',execution_bundle_id=BUNDLE_ID,workflow_version=VERSION,s3_release=r,
        phase_history='same saved own RGB/issued-command stage history as S3 v165; not navigation/grasp truth')
    paths=set(source_closure(ROOT,['scripts/run_s4_pair_live5_r2.py','sim/s4_pair_live.py']))
    paths.update((PLAN,RECORD+'/release-r2.json',RECORD+'/plan-r2.json',WORKFLOW))
    b['source_sha256'].update({p:old.sha(ROOT/p) for p in paths})
    return b


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--condition',choices=old.live.stage.CONDITIONS,required=True);p.add_argument('--relay-receipt',type=Path,required=True)
    p.add_argument('--execute',action='store_true');a=p.parse_args(argv)
    if not a.execute:
        print(json.dumps(dict(execution_started=False,bundle_id=BUNDLE_ID,condition=a.condition,seed=601,cap_s=90)));return 0
    old.live.previous.archive_guard(a.expected_source_sha,a.output)
    if os.environ.get('LP_NUM_THREADS')!='4':raise ValueError('LP_NUM_THREADS=4 required')
    old.live.write(a.output.parent/'driver.json',dict(pid=os.getpid(),pgid=os.getpgid(0),job=a.output.parent.name,source_sha=a.expected_source_sha))
    from sim.s4_pair_live import PhysicsBackend
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:
        r=bind(old.live.run,PLAN=PLAN)(bundle(a.expected_source_sha,a.condition),a.output,a.relay_receipt,
            pair_extension=Extension(a.output),backend_factory=PhysicsBackend)
        print(json.dumps(r));return int(r['status']=='HOST_ERROR')
    finally:undo()


if __name__=='__main__':raise SystemExit(main())
