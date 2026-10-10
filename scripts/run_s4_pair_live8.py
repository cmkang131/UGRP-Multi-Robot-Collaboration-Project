"""v173: real LLM handshake over unchanged S3 lower A, integer pulses and stage origin."""
import argparse
import copy
import json
import os
from pathlib import Path
from harness import s4_pair_handshake as hs
from harness.python_source_closure import source_closure
from harness.zone_final_pair_binding import bind
from scripts import run_s4_live as live, run_s4_pair_live5_r2 as admission
from scripts.run_s4_pair_live7 import Extension as PreviousExtension, persistent_output
from scripts import run_s3_stage_origin as upstream

ROOT = live.ROOT
RECORD = 'experiments/2026-10-06-s4-llm/s4live8'
PLAN = RECORD+'/README.md'
BUNDLE_ID = 'zone-s4-pair-live-v173'
VERSION = '7.66.0'
WORKFLOW = 'configs/simulation_workflows.d/s4_pair_live_v173.json'
RENEWAL_MODE = hs.ACTIVE_PHASE_HEARTBEAT
PLAN_FILE = 'plan.json'
RELEASE_FILE = 'release.json'


def configure(rid, ep, now):
    # Reuse the original S3 own-command/RGB entrance and unmodified adapters.
    admission.admit(rid, ep, now)
    from harness.zone_s3_setdown import attach as lower
    from harness.zone_s3_integer_carry import attach as integer
    lower(ep, 'canonical_floor_v1')
    integer(ep, 'integer_ticks_v1')


def bundle(sha, condition, seed=601, renewal='off'):
    if renewal not in ('off', RENEWAL_MODE):
        raise ValueError('unregistered heartbeat')
    release = json.loads((ROOT/RECORD/RELEASE_FILE).read_text())
    for p,h in release['s3_file_sha256'].items():
        if admission.old.sha(ROOT/p) != h:
            raise ValueError('frozen upstream S3 changed: '+p)
    b = live.bundle(sha, condition, 120., seed=seed)
    from harness.zone_s3_synchronized_carry import OPTION, PARAMS
    from harness.zone_s3_setdown import PARAMS as LOWER_PARAMS
    from sim.s3_setdown import LIMITS
    b.update(schema='ugrp.s4_pair_live.v173',execution_bundle_id=BUNDLE_ID,workflow_version=VERSION,
        case='pair',s3_release=release,pair_mode=hs.MODE,synchronized_carry=dict(option=OPTION,params=copy.deepcopy(PARAMS)),
        carry_lease_renewal=renewal,pair_drop_guard='contact_com_v1',concurrent_limit=8,
        setdown=dict(option='canonical_floor_v1',params=copy.deepcopy(LOWER_PARAMS),eval_supervisor='supported_lower_v1',eval_limits=LIMITS),
        integer_carry=dict(option='integer_ticks_v1',clock_hz=20,runtime_gt=False),
        stage_origin=dict(option='public_stage_origin_v1',public_start_xy_m=upstream.public_start(b),runtime_truth_feedback=False),
        stage_scope='claim-GO/ACK-carry-lower-reobserve-regrasp-fresh-GO/ACK-additional carry DEV',
        calls_per_actor=60,calls_total=180,token_cap=4000000,utterances_per_actor=24,utterances_total=48,
        no_scripted_claims=True,grip_monitor='LLM own RGB, unvalidated',handshake_deadline_s=hs.HANDSHAKE_S,own_rgb_response_ttl_s=hs.WINDOW_S)
    paths=set(source_closure(ROOT,['scripts/run_s4_pair_live8.py','sim/s4_pair_live8.py','scripts/submit_s4_live8.py','scripts/evaluate_s4_live8.py']))
    paths.update((WORKFLOW,PLAN,RECORD+'/'+RELEASE_FILE,RECORD+'/'+PLAN_FILE))
    b['source_sha256'].update({p:admission.old.sha(ROOT/p) for p in paths})
    return b


class Extension(PreviousExtension):
    def driver(self, host, runtime):
        self.pair_driver = admission.old.pair.Driver(host, runtime, on_admit=configure)
        return self.pair_driver

    def record_states(self, runtime, now):
        super().record_states(runtime, now)
        with (self.out/'pair-grip-epochs.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(t=now,robots={r:dict(state=e.controller.state,
                seg=e.controller.seg,grip_epoch=getattr(e.controller,'grip_epoch',0))
                for r,e in self.pair_driver.endpoints.items()}))+'\n')


def run(b, out, receipt):
    extension=Extension(out,b['carry_lease_renewal'])
    from sim.s4_pair_live8 import PhysicsBackend
    def backend(*args,**kwargs):
        value=PhysicsBackend(*args,**kwargs)
        value.states_getter=lambda:{r:e.controller.state for r,e in
            getattr(getattr(extension,'pair_driver',None),'endpoints',{}).items()}
        return value
    def setup(scenario):
        from sim.s3_stage_origin import initialize
        return initialize(live.setup_record(scenario),'pair',b['stage_origin']['public_start_xy_m'],b['stage_origin']['option'])
    return bind(live.run,PLAN=PLAN,setup_record=setup)(b,out,receipt,pair_extension=extension,backend_factory=backend)


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--condition',choices=live.stage.CONDITIONS,required=True)
    p.add_argument('--seed',type=int,choices=(601,602),default=601)
    p.add_argument('--carry-lease-renewal',choices=('off',RENEWAL_MODE),default='off')
    p.add_argument('--relay-receipt',type=Path,required=True);p.add_argument('--execute',action='store_true')
    a=p.parse_args(argv)
    if not a.execute:
        print(json.dumps(dict(execution_started=False,bundle_id=BUNDLE_ID,condition=a.condition,seed=a.seed,
            cap_s=120,carry_lease_renewal=a.carry_lease_renewal)));return 0
    persistent_output(a.output);live.previous.archive_guard(a.expected_source_sha,a.output)
    if os.environ.get('LP_NUM_THREADS')!='4':raise ValueError('LP_NUM_THREADS=4 required')
    live.write(a.output.parent/'driver.json',dict(pid=os.getpid(),pgid=os.getpgid(0),job=a.output.parent.name,source_sha=a.expected_source_sha))
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:r=run(bundle(a.expected_source_sha,a.condition,a.seed,a.carry_lease_renewal),a.output,a.relay_receipt)
    finally:undo()
    print(json.dumps(r));return int(r['status']=='HOST_ERROR')


if __name__=='__main__':raise SystemExit(main())
