"""S4 opt-in v166: real-model GO/ACK over the frozen S3 v165 transport."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from harness import s4_pair_stage as pair
from harness.zone_final_pair_binding import bind
from harness.python_source_closure import source_closure
from scripts import run_s4_live as live

ROOT = live.ROOT
RECORD = 'experiments/2026-10-06-s4-llm/s4live5'
PLAN = RECORD+'/README.md'
RELEASE = ROOT/RECORD/'release.json'
BUNDLE_ID = 'zone-s4-pair-live-v166'
VERSION = '7.59.0'
WORKFLOW = 'configs/simulation_workflows.d/s4_pair_live_v166.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_release(root=ROOT):
    r=json.loads((root/RECORD/'release.json').read_text())
    if (r['s3_source_sha']!='60eaf042bbf95e31fd7bdd50a84c69dcd38112c7'
            or r['execution_bundle_id']!=BUNDLE_ID or r['workflow_version']!=VERSION
            or r['seed']!=601 or r['cap_s']!=90 or r['research_result'] is not False):
        raise ValueError('frozen S4live5 release mismatch')
    for p,h in r['s3_file_sha256'].items():
        if sha(root/p)!=h:raise ValueError('S3 v165 source changed: '+p)
    return r


def bundle(source_sha,condition):
    r=validate_release()
    b=live.bundle(source_sha,condition,90.)
    from harness.zone_s3_synchronized_carry import OPTION,PARAMS
    b.update(schema='ugrp.s4_pair_live.v166',execution_bundle_id=BUNDLE_ID,workflow_version=VERSION,
        case='pair',s3_release=r,pair_mode=pair.hs.MODE,synchronized_carry=dict(option=OPTION,params=PARAMS),
        stage_scope='LLM pair claim-align-grasp-GO-ACK-first carry; lowering observed, excluded from verdict',
        concurrent_limit=4,handshake_deadline_s=pair.hs.HANDSHAKE_S,own_rgb_response_ttl_s=pair.hs.WINDOW_S,
        grip_monitor='LLM own RGB, unvalidated',no_scripted_claims=True)
    paths=set(source_closure(ROOT,['scripts/run_s4_pair_live5.py','sim/s4_pair_live.py']))
    paths.update((PLAN,RECORD+'/release.json',RECORD+'/plan.json',WORKFLOW))
    b['source_sha256'].update({p:sha(ROOT/p) for p in paths})
    return b


def admit(rid,ep,now):
    from harness.zone_s3_alignment_entry import attach_endpoint as entry,OPTION as ENTRY
    from harness.zone_s3_coarse_fine import attach_endpoint,OPTION
    from harness.zone_s3_alignment_ownership import ALL
    from harness.zone_s3_synchronized_carry import attach,OPTION as CARRY,joint_plan
    entry(ep,alignment_entry=ENTRY)
    attach_endpoint(ep,OPTION,refinements=ALL,planner=joint_plan)
    attach(ep,CARRY)
    ctl=ep.controller;report=ep.own.last_report
    ctl.driver.outcome='arrived'
    ctl.claims['at_prestation']=dict(estimate=[report.x_m,report.y_m,report.yaw_rad],
        std_xy_m=report.std_xy_m,looks=0,sim_time=now,
        source='stage-only own RGB estimate; not student arrival')
    ep.controller.set('align_start',now,stage_probe_entry=True)


class Extension:
    def __init__(self,out):
        self.out=Path(out);self.initial={};self.started=time.monotonic()

    def components(self):
        return pair.Link,pair.Host,{'handshake':pair.hs.Handshake()}

    def driver(self,host,runtime):
        return pair.Driver(host,runtime,on_admit=admit)

    def record_states(self,runtime,now):
        robots={}
        for rid in pair.hs.PAIR:
            ep=runtime.pair.producer.actors[rid]._pair
            robots[rid]=None if ep is None else dict(state=ep.controller.state,seg=ep.controller.seg)
        with (self.out/'pair-controller-states.jsonl').open('a') as f:
            f.write(json.dumps(dict(t=now,robots=robots))+'\n')

    def health(self,backend,runtime,host,commands,relative_s,*,result=None):
        # EVALUATION ONLY. No return value, pose/contact is never passed to policy.
        robots={}
        for rid in pair.hs.PAIR:
            base=backend.world.data.body(rid+'__robot').xpos.copy()
            arm=backend.world.data.body(rid+'__gripper').xpos.copy()
            if rid not in self.initial:self.initial[rid]=(base.copy(),arm.copy())
            import numpy as np
            ep=runtime.pair.producer.actors[rid]._pair if runtime is not None else None
            own=[c['action'] for c in commands if c['robot_id']==rid]
            robots[rid]=dict(base_xyz_m=base.tolist(),base_delta_m=float(np.linalg.norm(base-self.initial[rid][0])),
                arm_delta_m=float(np.linalg.norm(arm-self.initial[rid][1])),commands=len(own),
                servo_ids=sorted({a['servo_id'] for a in own if a['kind']=='arm'}),
                translation_commands=sum(a['kind'] in ('drive','mecanum') and bool(a.get('forward',0) or a.get('left',0)) for a in own),
                turn_commands=sum(a['kind'] in ('drive','mecanum') and bool(a.get('turn',0)) for a in own),
                state=ep.controller.state if ep is not None else 'await_claim')
        h=dict(sim_s=relative_s,frames=backend.frame,robots=robots,wall_s=time.monotonic()-self.started,
            model_calls=host.trial.send_ledger.sends() if host is not None else 0,
            phase=host.trial.handshake.record() if host is not None else None,
            status='RUNNING' if result is None else result['status'],error=None if result is None else result.get('failure'),
            controller_feedback=False)
        live.write(self.out.parent/'health.json',h)
        with (self.out.parent/'health-history.jsonl').open('a') as f:f.write(json.dumps(h)+'\n')


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--condition',choices=live.stage.CONDITIONS,required=True)
    p.add_argument('--relay-receipt',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args(argv)
    if not a.execute:
        print(json.dumps(dict(execution_started=False,bundle_id=BUNDLE_ID,condition=a.condition,seed=601,cap_s=90)));return 0
    live.previous.archive_guard(a.expected_source_sha,a.output)
    if os.environ.get('LP_NUM_THREADS')!='4':raise ValueError('LP_NUM_THREADS=4 required')
    live.write(a.output.parent/'driver.json',dict(pid=os.getpid(),pgid=os.getpgid(0),job=a.output.parent.name,source_sha=a.expected_source_sha))
    from sim.s4_pair_live import PhysicsBackend
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:
        r=bind(live.run,PLAN=PLAN)(bundle(a.expected_source_sha,a.condition),a.output,a.relay_receipt,
            pair_extension=Extension(a.output),backend_factory=PhysicsBackend)
        print(json.dumps(r));return int(r['status']=='HOST_ERROR')
    finally:undo()


if __name__=='__main__':raise SystemExit(main())
