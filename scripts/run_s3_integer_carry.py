"""v167: frozen full ten-condition A+integer pulse on/off comparison on Oracle."""
import argparse,copy,hashlib,json,math
from pathlib import Path
from harness.python_source_closure import source_closure
from harness.zone_final_pair_binding import bind
from harness.zone_s3_integer_carry import OPTION,attach
from harness.zone_s3_coarse_fine import OPTION as SERVO,attach_endpoint,attach_solo
from harness.zone_s3_synchronized_carry import attach as attach_carry,joint_plan,OPTION as CARRY
from harness.zone_s3_alignment_ownership import ALL
from harness.zone_s3_setdown import attach as attach_setdown
from scripts import run_s3_setdown as previous
from sim.s3_setdown import PhysicsBackend as PreviousBackend

BUNDLE_ID='zone-s3-integer-carry-v167'
WORKFLOW_VERSION='7.60.0'
WORKFLOW='configs/simulation_workflows.d/s3_integer_carry_v167.json'
PLAN='experiments/2026-10-10-s3-integer-carry/summary.json'


def bundle(sha,case,condition,option='off',route_case='single'):
    if option not in ('off',OPTION):raise ValueError('unregistered integer carry option')
    if route_case not in ('single','multi-left','multi-right','multi-three'):raise ValueError('unregistered route')
    if route_case!='single' and (case!='pair' or option!=OPTION):raise ValueError('multi route requires coupled integer candidate')
    b=previous.bundle(sha,case,condition,'canonical_floor_v1')
    b.update(execution_bundle_id=BUNDLE_ID,workflow_version=WORKFLOW_VERSION,schema='ugrp.s3_integer_carry.v167',
        integer_carry=dict(option=option,clock_hz=20,runtime_gt=False),concurrent_probe_limit=20,route_case=route_case)
    if route_case!='single':
        entry=next(c for c in json.loads((previous.stage.ROOT/PLAN).read_text())['next_stage_preregistration']['cases'] if c['name'].startswith('s3fix19-'+route_case+'-'))
        if condition!=entry['condition']:raise ValueError('unregistered multi-route condition')
        b['registered_route']=entry['route'];b['stage_scope']='joint straight-corner-crab-next-leg-final-setdown'
    paths=set(source_closure(previous.stage.ROOT,['scripts/run_s3_integer_carry.py','scripts/run_s3_integer_carry_cohort.py','scripts/evaluate_s3_integer_carry.py']))|{WORKFLOW,PLAN}
    b['source_sha256'].update({p:hashlib.sha256((previous.stage.ROOT/p).read_bytes()).hexdigest() for p in paths})
    return b


class PhysicsBackend(PreviousBackend):
    def progress(self):
        super().progress()
        if self.bundle['case']=='cyan' and self.now>=getattr(self,'next_cyan_progress',0.):
            self.next_cyan_progress=self.now+1.
            import json
            row=dict(t=self.now,frame_count=self.frame,
                states=self.states_getter(),robots={'r3':dict(base_xyz_m=self.world.data.body('r3__robot').xpos.tolist(),
                finger_xyz_m=self.world.data.geom('r3__left_finger').xpos.tolist(),issued=dict(self.commands.get('r3',{})))})
            with (self.out/'cyan-progress.jsonl').open('a') as stream:stream.write(json.dumps(row,allow_nan=False)+'\n')


def route_plan(plan,static,route):
    from harness import pair_passage_plan as passage
    from harness.zone_final_pair_skill import ENVELOPE
    from harness.map_goto import authored_obstacles,interior_bounds
    if any(abs(a[0]-b[0])>1e-8 and abs(a[1]-b[1])>1e-8 for a,b in zip(route,route[1:])):raise ValueError('cardinal static route required')
    why,blocker=passage._sweep_blocker(route,ENVELOPE,authored_obstacles(static),interior_bounds(static),passage.ROUTE_MARGIN_M)
    if why:raise ValueError('registered route static sweep: '+str((why,blocker)))
    out=copy.deepcopy(plan);out['route']=copy.deepcopy(route);out['checkpoint_segments']={'before_destination':len(route)-2}
    out['registered_route_source']='s3fix19 pre-execution public route; no cargo/robot truth';return out


def run(b,out):
    # Rebind only this runner's dependency, leaving all registered older paths.
    old_attach=previous.attach_carry
    def configure(ep,option):
        old_attach(ep,option);return attach(ep,b['integer_carry']['option'])
    # previous.run refers to stage via globals, with a function rebinding;
    # cyan state receipts are read-only and are obtained from own localizer.
    eps={};runtime={}
    def backend(*args,**kwargs):
        host=PhysicsBackend(*args,**kwargs)
        host.states_getter=lambda:({r:ep.controller.state for r,ep in eps.items()} if b['case']=='pair' else {'r3':runtime['own'].state} if 'own' in runtime else {})
        return host
    stage=previous.stage
    def enter(rt,now,ignored):
        if 'registered_route' in b:
            from types import MethodType
            team=rt.pair.producer.team;start=team.start.__func__;planner=start.__globals__['make_plan']
            def registered_planner(static,*args,**kwargs):
                return route_plan(planner(static,*args,**kwargs),static,b['registered_route'])
            team.start=MethodType(bind(start,make_plan=registered_planner),team)
        eps.update(stage.previous.enter_pair(rt,now,'off'))
        for ep in eps.values():
            attach_endpoint(ep,SERVO,refinements=ALL,planner=joint_plan)
            configure(ep,CARRY);attach_setdown(ep,b['setdown']['option'])
            ctl=ep.controller;old=ctl._cp_open
            def cp_open(now,idle,ctl=ctl,old=old):
                value=old(now,idle)
                if idle and not ctl.failure and ctl._issued().get(1)==2000:ctl.s3_first_release_complete=True
                return value
            ctl._cp_open=cp_open
        return eps
    def solo(own,_):runtime['own']=own;return attach_solo(own,SERVO,refinements=ALL)
    def stop():return bool(eps) and all(getattr(e.controller,'s3_first_release_complete',False) for e in eps.values())
    from types import SimpleNamespace
    probe=bind(stage.previous.run,CAP=b['cap_sim_s'])
    probe.__kwdefaults__={**probe.__kwdefaults__,'solo_configure':solo,'stop_when':stop}
    ns=SimpleNamespace(**{**vars(stage.previous),'enter_pair':enter,'run':probe})
    result=bind(stage.run,previous=ns,StageBackend=backend)(b,out)
    if 'DEV_INITIAL_CHECK_STOP' in result.get('failure',''):result['status']='EARLY_STOP'
    stage.previous.write(out/'result.json',result);stage.previous.artifact_manifest(out)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--case',choices=('pair','cyan'),default='pair');p.add_argument('--condition',type=int,choices=range(6),default=0)
    p.add_argument('--integer-carry',choices=('off',OPTION),default='off');p.add_argument('--route-case',choices=('single','multi-left','multi-right','multi-three'),default='single');p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute:print(BUNDLE_ID);return 0
    previous.stage.archive_guard(a.expected_source_sha,a.output)
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:r=run(bundle(a.expected_source_sha,a.case,a.condition,a.integer_carry,a.route_case),a.output)
    finally:undo()
    print(r);return int(r['status'] in ('HOST_ERROR','EARLY_STOP'))
if __name__=='__main__':raise SystemExit(main())
