"""S3 no-setdown distance diagnostic. Same controls/physics; evaluation is separate."""
import argparse
import copy
import hashlib
import json
import os
import platform
import time
from pathlib import Path
from types import SimpleNamespace

from harness.zone_final_pair_binding import bind
from harness.python_source_closure import source_closure
from harness.zone_s3_route_resume import attach as resume, CANDIDATES
from sim.s3_stage_origin import initialize, OPTION as ORIGIN
from sim.s3_release_epoch import PhysicsBackend as PreviousBackend
from scripts import run_s3_integer_carry as previous

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ID = 'zone-s3-continuous-distance-v186'
WORKFLOW_VERSION = '7.79.0'
PLAN = 'experiments/2026-10-11-s3-continuous-distance/registration.json'
TEMPLATE = 'configs/s3_continuous_carry_template_v1.json'
WORKFLOW = 'configs/simulation_workflows.d/s3_continuous_distance_v186.json'


def bundle(sha, distance, seed):
    plan = json.loads((ROOT/PLAN).read_text())
    if not any(r['distance_m'] == distance and r['seed'] == seed for r in plan['runs']):
        raise ValueError('unregistered distance/seed')
    b = json.loads((ROOT/TEMPLATE).read_text())
    start = plan['route_start']
    route = [start, [start[i]+distance*plan['route_axis'][i] for i in range(2)]]
    b.update(schema='ugrp.s3_continuous_distance.v186', execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION, source_sha=sha, seed=seed,
        provider_seeds={r:seed+i for i,r in enumerate(('r1','r2','r3'))},
        registered_route=route, route_case='continuous-straight', initial_condition=0,
        stage_scope='own-RGB-align-grasp-lift-uninterrupted-carry-final-release',
        host='ugrp-sim-azure', comparison_scope='same Azure OSMesa cohort only',
        cap_sim_s=plan['cap_sim_s'], case_cap_s=plan['cap_sim_s'], wall_cap_s=3600.,
        continuous_distance=dict(target_m=distance, intermediate_release=False,
            fixed_pulses=True, controller_feedback=False),
        checkpoint_correction=dict(candidate='recovery',options=dict(
            release_epoch=True,expanded_backoff=False,visual_checkpoint=False)),
        stage_origin=dict(option=ORIGIN,public_start_xy_m=start,controller_pose_prior=False),
        model_calls=0, research_result=False, confirmation_sample=False)
    paths=set(source_closure(ROOT,['scripts/run_s3_continuous_distance.py',
        'scripts/run_s3_continuous_cohort.py','scripts/evaluate_s3_continuous_distance.py']))
    paths.update((PLAN,TEMPLATE,WORKFLOW,b['calibration'],b['setup_fixture'],
        'configs/s2_v133_full_template.json',
        'experiments/2026-10-09-s3-no-prior/s3fix8/alignment-phase.json'))
    b['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(paths)}
    return b


class PhysicsBackend(PreviousBackend):
    """Pose/contact telemetry never returns data to the runtime."""
    def eval_sample(self):
        super().eval_sample()
        states=self.states_getter() if self.states_getter else {}
        robots={}
        for rid in ('r1','r2'):
            ctl=getattr(self,'controllers',{}).get(rid)
            report=ctl.port.own.last_report if ctl else None
            body=self.world.data.body(rid+'__robot')
            import math
            estimate=[report.x_m,report.y_m] if report else None
            if estimate and not all(math.isfinite(v) for v in estimate):estimate=None
            finite=lambda v:float(v) if v is not None and math.isfinite(v) else None
            robots[rid]=dict(actual_xy_m=body.xpos[:2].tolist(),
                actual_yaw_rad=math.atan2(float(body.xmat[3]),float(body.xmat[0])),
                estimated_xy_m=estimate,
                estimated_yaw_rad=finite(report.yaw_rad) if report else None,
                std_xy_m=finite(report.std_xy_m) if report else None)
        self._append('eval_only/continuous-poses.jsonl',dict(t=self.now,states=states,
            robots=robots,controller_feedback=False))


def run(b,out):
    stage=previous.previous.stage
    def setup(case,condition):
        return initialize(stage.varied_setup(case,condition),case,
            b['registered_route'][0],ORIGIN)
    stage_ns=SimpleNamespace(**{**vars(stage),'run':bind(stage.run,varied_setup=setup)})
    parent=SimpleNamespace(**{**vars(previous.previous),'stage':stage_ns})
    controllers={}
    def configure(ep,*args,**kwargs):
        ep=resume(previous.attach_endpoint(ep,*args,**kwargs),CANDIDATES['combined'])
        controllers[ep.own.robot_id]=ep.controller
        ep.own.job_sim_limit_s=b['cap_sim_s'];ep.controller.job_sim_limit_s=b['cap_sim_s']
        ep.own.job.deadline=ep.own.now+b['cap_sim_s']
        return ep
    def backend(*args,**kwargs):
        host=PhysicsBackend(*args,**kwargs);host.controllers=controllers
        return host
    result=bind(previous.run,previous=parent,PhysicsBackend=backend,
        attach_endpoint=configure)(b,out)
    result.update(host='ugrp-sim-azure',model_calls=0)
    env=json.loads((out/'environment.json').read_text())
    env.update(host='ugrp-sim-azure',source_mode='Azure committed-source runner')
    writer=stage.previous
    writer.write(out/'environment.json',env);writer.write(out/'result.json',result)
    writer.artifact_manifest(out)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--distance',type=float,required=True)
    p.add_argument('--seed',type=int,required=True);p.add_argument('--execute',action='store_true')
    a=p.parse_args()
    if not a.execute:print(BUNDLE_ID);return 0
    # Same immutable archive receipt and Linux/OSMesa guard; no Mac physics.
    previous.previous.stage.archive_guard(a.expected_source_sha,a.output)
    if platform.node()!='ugrp-sim-azure':raise ValueError('registered Azure host required')
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:r=run(bundle(a.expected_source_sha,a.distance,a.seed),a.output)
    finally:undo()
    print(json.dumps(r));return int(r['status'] in ('HOST_ERROR','EARLY_STOP'))


if __name__=='__main__':raise SystemExit(main())
