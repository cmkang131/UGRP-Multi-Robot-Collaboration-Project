"""S4 DEV four-condition Oracle x86 stage probe; never Mac physics or E2E."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import time
import traceback

from harness import s4_live_stage as stage
from harness.s4_live_transport import TunnelLedger, URL
from harness.zone_study_llm_driver import load_registry, client_factory
from harness.zone_study_integration import ModelAdapter
from harness.zone_main_budget import MainStudyBudget
from harness.zone_study_contract import digest
from harness.zone_study_inputs import OrderSheetSource
from harness.zone_event_scheduler import CallPolicy
from harness.zone_study_decisions import DecisionLimits
from harness.python_source_closure import source_closure
from harness import zone_map_schematic as maps
from scripts import run_s3_x86_probe as previous
from scripts.run_s3_host import write, artifact_manifest, environment_record

ROOT = previous.ROOT
BUNDLE_ID = 'zone-s4-live-dev-v157'
WORKFLOW_VERSION = '7.51.0'
SCENARIO = 'configs/zone_study_dev/dev_s1lite.json'
WORKFLOW = 'configs/simulation_workflows.d/s4_live_v157.json'
PLAN = 'experiments/2026-10-06-s4-llm/s4live1/README.md'


def inputs():
    scenario = json.loads((ROOT/SCENARIO).read_text())
    mapped = maps.map_bundle(scenario['map_id'], landmark_detail='none')
    return scenario, mapped, OrderSheetSource(scenario, mapped).sheet()


def bundle(sha, condition, cap, *, seed=601):
    if condition not in stage.CONDITIONS or cap not in (7.5, 90., 120.):
        raise ValueError('registered condition and 7.5/90/120 SIM-second cap required')
    if type(seed) is not int or seed not in (601, 602):
        raise ValueError('registered DEV seed required')
    b = previous.bundle(sha, 'cyan')
    scenario, mapped, sheet = inputs()
    b.update(schema='ugrp.s4_live_stage.v157', execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION, seed=seed, provider_seeds={r:seed+i for i,r in enumerate(stage.s4.routing.ROBOTS)},
        scenario_id='dev_s1lite', scenario_sha256=digest(scenario), map_bundle_sha256=digest(mapped),
        order_sheet_sha256=digest(sheet), case_cap_s=cap, wall_cap_s=1800.,
        condition=condition, research_result=False, model_calls=None,
        stage_scope='r3 claim-pick-lift-depart-carry; r1/r2 claim-only',
        no_scripted_claims=True, departure_window_s=10., concurrent_limit=6,
        authentication='Mac audited proxy via SSH loopback; no credentials transferred')
    paths = set(b['source_sha256']) | set(source_closure(ROOT, ['scripts/run_s4_live.py']))
    paths.update((WORKFLOW, PLAN, SCENARIO, 'scripts/s4_proxy_relay.py'))
    b['source_sha256'] = {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(paths)}
    return b


def setup_record(scenario):
    data = previous.setup_record(None, 'cyan')
    for placement in scenario['eval']['setup']['placements']:
        row = data['truth']['items'][placement['item_id']]
        row['x'], row['y'], row['yaw'] = placement['pose_m']
    cyan = data['truth']['items']['cyan_1']
    r3 = data['robots']['r3']['pose']
    r3['robot_xyz_m'][:2] = [cyan['x']-.24, cyan['y']]
    r3['robot_yaw_rad'] = 0.
    data.update(classification='dev_s1lite synthetic r3 alignment entrance; setup-only, not navigation success',
                scenario_id='dev_s1lite', feedback_to_controller=False)
    return data


def run(b, out, receipt, *, pair_extension=None, backend_factory=None):
    from sim.s3_stage_safety import PhysicsBackend
    from harness.zone_s3_recovery_runtime import Runtime
    from harness.zone_solo_cyan_v106 import passage_route
    from harness.pair_llm_live import live_records, live_walls
    from harness.zone_s3_no_prior_contract import hp
    out.mkdir(parents=True, exist_ok=False)
    write(out/'bundle.json', b); write(out/'environment.json', environment_record())
    scenario, mapped, sheet = inputs()
    profile = copy.deepcopy(load_registry()['driver_profiles']['main_study_gemini_v1'])
    profile['proxy_url'] = URL
    profile['sha256'] = digest(profile)
    run_key = f's4live1-{b["condition"]}-{out.parent.name}'
    budget = MainStudyBudget.create(out/'budget.sqlite')
    budget.register_cohort(run_key, token_cap=b.get('token_cap',300000 if pair_extension is None else 1100000), unknown_usage_charge_tokens=16000,
                          prereg_sha256=b['source_sha256'][PLAN], source={'source_sha':b['source_sha']})
    budget.start_run(run_key, cohort_id=run_key, bundle_id=b['execution_bundle_id'], bundle_sha256=digest(b),
                     record={'research_result':False})
    ledger = TunnelLedger(receipt=receipt, store_dir=out/'wire', budget=budget, run_key=run_key, profile=profile)
    write(out/'proxy-identity.json', ledger.proxy_identity)
    adapter = ModelAdapter(client_factory(profile), ledger)
    result = dict(status='HOST_ERROR', research_result=False, source_sha=b['source_sha'],
        execution_bundle_id=b['execution_bundle_id'], condition=b['condition'], seed=b['seed'], host='oracle-x86',
        gt_control_inputs=False, weld='off', dev_light=True, model_calls=0,
        pair_scope='claim_only_no_pair_motion', physical_success=None, loadavg_start=os.getloadavg())
    began = time.monotonic(); backend = runtime = host = pair_driver = None; states = []; causal = []
    try:
        backend = (backend_factory or PhysicsBackend)(b, out, seed=b['seed']); backend.reset(b['reset_cap_s'])
        previous.previous.restore_scene(backend, setup_record(scenario))
        start = backend.now; backend.set_deadline(start+b['case_cap_s'])
        static = hp.resolve(b['map_id'])[0]
        internal_orders = copy.deepcopy(sheet['orders'])
        for order in internal_orders: order['destination_zone'] = 'B'
        runtime = Runtime(static, internal_orders, ROOT/b['calibration'], b['calibration_sha256'],
                          seed=b['seed'], config=b['controller_config'])
        own = stage.use_public_destination(runtime, next(o for o in sheet['orders'] if o['kind']=='cyan'), static)
        runtime.initial_commands(start, backend.commands)
        runtime.boot_finished_at = start
        link_cls, host_cls, extra = (stage.Link, stage.Host, {}) if pair_extension is None else pair_extension.components()
        links = {r:link_cls(runtime.links[r], condition=b['condition'], origin_s=start,
            executor=runtime.pair.actors[r] if r != 'r3' else None, **extra) for r in stage.s4.routing.ROBOTS}
        host = host_cls(scenario, condition=b['condition'], links=links, seed=b['seed'], map_bundle=mapped,
            horizon_s=b['case_cap_s'], model_adapter=adapter, code_sha=b['source_sha'],
            policy=CallPolicy(max_calls_per_actor=b.get('calls_per_actor',6 if pair_extension is None else 30),
                max_http_attempts_per_actor=b.get('calls_per_actor',6 if pair_extension is None else 30),
                max_attempts_total=b.get('calls_total',18 if pair_extension is None else 90), max_retries=0),
            decision_limits=DecisionLimits(max_calls_total=b.get('calls_total',18 if pair_extension is None else 90),
                max_utterances_per_actor=b.get('utterances_per_actor',6), max_utterances_total=b.get('utterances_total',12)))
        if pair_extension is not None:
            pair_driver = pair_extension.driver(host, runtime.pair.producer)
            result['pair_scope'] = 'claim-align-grasp-mutual-go-carry-own-rgb-monitor'
        entered = False
        steps = round(b['case_cap_s']/.05)
        for i in range(steps+1):
            now = backend.now; rel = round(now-start, 8)
            backend.eval_sample()
            if i == steps: break
            if time.monotonic()-began > b['wall_cap_s']: raise TimeoutError('S4_WALL_CAP')
            frames = backend.capture(); previous.previous.assert_frame_commands(backend, frames)
            runtime.on_frames(now, frames)
            for link in links.values(): link.capture_frame()
            if pair_extension is not None and hasattr(pair_extension, 'health') and i % 20 == 0:
                pair_extension.health(backend, runtime, host, causal, rel)
            if not host.started: host.begin(0.)
            if own.state == 'carry' and links['r3'].departure_opened is None:
                host.trial.open_departure(rel)
            if pair_driver is not None: pair_driver.poll(now)
            host.step_to(rel)
            commands = []
            if runtime.links['r3'].active:
                if not entered:
                    fits = own.vision.detect(own.last_obs, own.servo)
                    if len(fits) != 1: raise ValueError('CYAN_STAGE_NOT_UNIQUELY_VISIBLE')
                    own.target = fits[0]['estimated_box_center_base_m'][:2]
                    own.set_state('align', now); entered = True
                waiting = own.state == 'carry' and not links['r3'].departure_accepted
                if not waiting: commands = own.step(now)
            if pair_driver is not None: commands = [*commands, *pair_driver.step(now)]
            if pair_extension is not None and hasattr(pair_extension, 'record_states'):
                pair_extension.record_states(runtime,now)
            for rid, action in commands:
                backend.issue(rid, action); runtime.on_command(rid, now, action)
                causal.append(dict(t=now, robot_id=rid, action=action, claim_call_id=links[rid].claim_call,
                    departure_call_id=next((d['call_id'] for d in links['r3'].departure_decisions if d['accepted']),None)
                    if rid=='r3' else None,
                    **({'pair_permit': copy.deepcopy(pair_driver.handshake.permits[-1])
                        if pair_driver.handshake.permits else None} if rid != 'r3' and pair_driver is not None else {})))
            states.append(dict(t=now, relative_sim_s=rel, state=own.state, failure=own.failure,
                departure_pending=links['r3'].departure_opened is not None and not links['r3'].departure_accepted))
            if own.failure: raise RuntimeError('CONTROLLER_FAILURE:'+own.failure)
            if pair_driver is not None and pair_driver.handshake.failure:
                result['pair_failure'] = pair_driver.handshake.failure
                break
            if pair_extension is not None and hasattr(pair_extension, 'terminal') and pair_extension.terminal():
                result['own_executor_route_complete'] = True
                break
            backend.advance_to(start+(i+1)*.05)
        if b.get('terminal_censor', False):
            from harness.s4_pair_recovery import settle_without_commands
            result['terminal_settlement'] = settle_without_commands(host, round(backend.now-start,8))
        else:
            host.finish(round(backend.now-start,8))
        result.update(status='PAIR_STOP' if result.get('pair_failure') else 'DEV_STAGE_FINISHED', final_state=own.state,
            departure_accepted=links['r3'].departure_accepted,
            departure_decisions=links['r3'].departure_decisions,
            accepted_claims={r:links[r].claim_call for r in links})
    except Exception as exc:
        result.update(failure_type=type(exc).__name__, failure=traceback.format_exc())
        if type(exc).__name__=='PhysicalStop': result['status']='PHYSICAL_STOP'
        if host is not None: host.failed = host.failed or exc
    finally:
        if backend is not None:
            result['check_sim_s'] = backend.now-start if 'start' in locals() else 0.
            for rid in ('r1','r2','r3'):
                backend.issue(rid, {'kind':'hold'})
            if pair_extension is not None and hasattr(pair_extension, 'health'):
                pair_extension.health(backend, runtime, host, causal, result['check_sim_s'], result=result)
        if host is not None:
            if b.get('terminal_censor', False) and not host.finished:
                from harness.s4_pair_recovery import settle_without_commands
                result['terminal_settlement'] = settle_without_commands(host, result.get('check_sim_s',0.))
            host.save(out/'llm')
        if pair_driver is not None:
            write(out/'pair-handshake.json', pair_driver.handshake.record())
            write(out/'pair-submissions.json', {r:links[r].pair_submission_log for r in ('r1','r2')})
        if runtime is not None:
            write(out/'student_record.json', runtime.record()); runtime.close()
        if backend is not None: backend.close()
        records = live_records(ledger)
        result.update(wall_s=time.monotonic()-began, model_calls=records['usage']['requests'],
            model_usage=records['usage'], model_response_wall_s=live_walls(host.trial) if host else [],
            commands_issued=len(causal), loadavg_end=os.getloadavg())
        budget.finish_run(run_key, status=result['status'], summary=result)
        write(out/'result.json',result); write(out/'stage-states.json',states)
        write(out/'decision-command-links.json',causal); write(out/'model_calls.json',records)
        artifact_manifest(out)
    return result


def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--condition', choices=stage.CONDITIONS, required=True)
    p.add_argument('--cap-s', type=float, choices=(7.5,90.), default=90.)
    p.add_argument('--relay-receipt', type=Path, required=True); p.add_argument('--execute', action='store_true')
    p.add_argument('--pair-mode', choices=('off','mutual_go_v1'), default='off')
    p.add_argument('--pair-release', type=Path,
        default=Path('experiments/2026-10-06-s4-llm/s4live4/release.json'))
    a=p.parse_args(argv)
    if a.pair_mode != 'off':
        from scripts.run_s4_pair_preparation import dispatch
        return dispatch(a)
    if not a.execute:
        print(json.dumps(dict(execution_started=False, bundle_id=BUNDLE_ID, condition=a.condition))); return 0
    previous.archive_guard(a.expected_source_sha, a.output)
    from harness.zone_pair_highpose_exact_speedups import install
    _, undo=install('v98-exact-v6')
    try:
        result=run(bundle(a.expected_source_sha,a.condition,a.cap_s),a.output,a.relay_receipt)
        print(json.dumps(result)); return int(result['status']=='HOST_ERROR')
    finally: undo()


if __name__=='__main__': raise SystemExit(main())
