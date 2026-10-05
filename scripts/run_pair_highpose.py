"""Managed v96 student candidate.

MEASURED_SIM (default): plan-only until an approved v92 measured calibration
and a runnable bundle. DEV_PILOT (``--admission dev-pilot``): one exact
registered calibration sha256 (c0 = 0); every result is FUNCTIONAL_DEV with
its own cohort and can never be promoted to confirmatory/MEASURED_SIM evidence.
"""
from __future__ import annotations

import argparse
import errno
import json
from pathlib import Path
import shutil
import subprocess
import sys

from harness import zone_pair_highpose_contract as contract
from harness.zone_pair_highpose_runtime import Runtime
from harness import zone_pair_highpose_timing as time_budget
from harness import zone_pair_highpose_starts as starts
from scripts.run_final_environment_checks import write, check_source


def checkpoint_record(runtime_record, checkpoint):
    """Actual carried-prefix stop/reobserve receipts; never teleport/regrasp."""
    if not runtime_record or not runtime_record.get('pair'):
        return {'status': 'NOT_REACHED', 'checkpoint': checkpoint, 'robots': {}}
    session = runtime_record['pair'][0]
    wanted = session['plan']['checkpoint_segments'].get(checkpoint)
    rows = {}
    for rid, robot in session['robots'].items():
        events = robot['events']
        # v98 sigma re-fix (zone_pair_highpose_refix): a set-down at this stop replaces the HIGH stop; its receipt
        # is the own fix taken on the floor, raised again to HIGH (kind 'floor_refix', never labelled 'fix').
        stopped = [e for e in events if (e['event'] == 'checkpoint_high_stop' and e['seg'] == wanted)
                   or (e['event'] == 'refix_set_down' and e.get('stop') == wanted)]
        # v98: a fresh fix after the stop, or the own DR receipt within the unchanged budget (kind kept per row).
        from harness.zone_pair_highpose_dr_checkpoint import RECEIPT_EVENTS
        receipts = {**RECEIPT_EVENTS, 'refix_resumed_high': 'floor_refix'}
        observed = [{**e, 'receipt': receipts[e['event']]} for e in events
                    if e['event'] in receipts and e['seg'] == wanted]
        # Every preceding leg must have started under a carry GO. A receipt
        # name alone cannot stand in for carrying the route from the dock.
        carried = {e.get('seg') for e in events if e['event'] == 'state' and e.get('state') == 'carry'}
        rows[rid] = {'high_stop': stopped, 'high_reobserved': observed,
                     'carried_prefix': wanted is not None and set(range(wanted)) <= carried}
    reached = (set(rows) == set(contract.ROBOTS)
               and all(r['high_stop'] and r['high_reobserved'] and r['carried_prefix'] for r in rows.values()))
    return {'status': 'SEQUENCE_OBSERVED_UNQUALIFIED' if reached else 'NOT_REACHED',
            'checkpoint': checkpoint, 'segment': wanted, 'robots': rows,
            'physical_success': None, 'cohort_role': 'FUNCTIONAL_DEV_REPLAY', 'confirmation_sample': False}


# Stage probes (FUNCTIONAL_DEV diagnostics, never a case result). v96 starts
# from the public dock, so the only short stages are prefixes of the registered
# route: the run stops when BOTH robots log the stage-terminal event, or on the
# first controller failure / job end, or at the probe cap. Carry to the first
# checkpoint, checkpoint to checkpoint and lower+open are the P03 cases and the
# full carry case themselves (no mid-carry controller-state staging exists).
STAGE_PROBES = {
    'raise_high': {'terminal_event': 'high_carry_pose', 'barrier': None, 'cap_s': 150.,
                   'covers': 'dock -> RGB align/grasp -> low lift -> raise to HIGH'},
    'high_hold': {'terminal_event': 'barrier_go', 'barrier': 'carry', 'cap_s': 150.,
                  'covers': 'raise_high + 8 s HIGH settle + carry barrier GO from command history/status'},
    # 2026-10-05 (coordinator): the unloaded approach alone, from the real dock and the real PF prior (not staged),
    # so the r2 no_fix look gate and the own-RGB arrival check meet physics before the grasp. Ends when both robots
    # have entered wait_approach (after the arrival view check); cap >= 200 SIM s as ordered.
    'dock_approach': {'terminal_event': 'state', 'terminal_state': 'wait_approach', 'barrier': None, 'cap_s': 240.,
                      'covers': 'dock -> look_around -> pair approach -> arrival view check -> wait_approach (both)'},
}
# v98 staged probes (harness/zone_pair_highpose_staging.py): staged test setup
# before the controller exists, so stages after approach run without it.
from harness import zone_pair_highpose_staging as staging  # noqa: E402
STAGE_PROBES.update({k: {**v, 'staged': True} for k, v in staging.PROBE_SPECS.items()})
STAGE_STATUS = ('STAGE_PROBE_REACHED', 'STAGE_PROBE_FAILED', 'STAGE_PROBE_NOT_REACHED')


CASE_END_SETTLE_S = 3.


def jobs_ended_all(runtime):
    """True when every robot has an ended non-look_around (pair/carry) job."""
    actors = getattr(runtime, 'actors', None) or {}
    return bool(actors) and all(any(j.get('kind') != 'look_around' for j in actors[r].jobs_done)
                                for r in contract.ROBOTS if r in actors) and all(r in actors for r in contract.ROBOTS)


def stage_progress(runtime, probe):
    """Live controller events/failures (control-side objects only; no eval labels)."""
    spec = STAGE_PROBES[probe]
    reached, failures, jobs = {}, {}, {}
    for session in getattr(getattr(runtime, 'team', None), 'sessions', None) or []:
        for rid, ep in session['endpoints'].items():
            hits = [e for e in ep.events if e.get('event') == spec['terminal_event']
                    and (spec['barrier'] is None or e.get('barrier') == spec['barrier'])
                    and (spec.get('terminal_state') is None or e.get('state') == spec['terminal_state'])]
            reached[rid] = reached.get(rid) or bool(hits)
            if ep.controller.failure is not None:
                failures[rid] = ep.controller.failure
    recovery = getattr(runtime, 'look_recovery', None)
    if recovery is not None:
        # v98 look recovery exhausted: this robot stops submitting, so the probe cannot reach its stage.
        failures.update(recovery.failures())
    for rid, own in (getattr(runtime, 'actors', None) or {}).items():
        # The opening look_around job (and v98 re-looks, also look_around) always ends before the pair job is
        # submitted; only an ended pair/carry job stops a probe.
        ended = [dict(j) for j in own.jobs_done if j.get('kind') != 'look_around']
        if ended:
            jobs[rid] = ended
    done = set(reached) >= set(contract.ROBOTS) and all(reached.get(r) for r in contract.ROBOTS)
    return {'reached': reached, 'failures': failures, 'jobs_ended': jobs, 'done': done,
            'stop': done or bool(failures) or bool(jobs)}


# v98 evaluation-side cause labels. harness/pair_stage_probe.py (hash-pinned by older review records) is left
# unchanged; its map is extended here with the blind final approach refusal names.
FAILURE_CAUSE_TEXT = {
    'HOVER_NOT_CONFIRMED': 'own-RGB hover check refused the blind descent (pre-close check / band / posture)',
    'BLIND_WINDOW_CLOSED': 'blind final approach refused at the grasp posture (window not armed or closed by a command,'
                           ' time, distance or track limit)',
    'ARRIVAL_VIEW_NOT_CONFIRMED': 'approach arrival refused: the own frame did not show the beam inside the image bands'
                                  ' of the arrival tolerance (rejected after the bounded relocalize + approach-again)'}
# v98 controller failure names absent from the frozen map (review delta2 P2-4). DR over budget and an infeasible
# horizon after a re-fix are own-pose uncertainty (the existing cause); the decision-exchange failures get their own
# label so a pair-coordination stop is not counted as pose uncertainty.
FAILURE_CAUSE_TEXT['PAIR_DECISION_EXCHANGE'] = ('re-fix decision exchange failed at a carry stop (partner status '
                                                'never seen in the window, or the re-fix echo did not come)')
FAILURE_CAUSE_TEXT['PAIR_BARRIER_WAIT'] = ('re-fix hover@k+1 pair barrier: the partner did not become hover ready within '
                                           'its own derived limits, or the barrier aborted')
# 2026-10-05: the close barrier of a pair re-grasp (runtime _wait_close) had no label (14ba8b5e probe ->
# UNCLASSIFIED). Its stop is a pair-coordination stop like the hover barrier, so it gets its own label too.
FAILURE_CAUSE_TEXT['PAIR_BARRIER_CLOSE'] = ('close pair barrier (wait_close) before the jaws close: the barrier aborted'
                                            ' (e.g. LATE_OR_EXPIRED_GO, own poll after the shared GO time) or timed out')
V98_FAILURE_TO_CAUSE = {
    'BARRIER_CLOSE_ABORT': 'PAIR_BARRIER_CLOSE',
    'BARRIER_CLOSE_TIMEOUT': 'PAIR_BARRIER_CLOSE',
    'REFIX_HOVER_BARRIER_TIMEOUT': 'PAIR_BARRIER_WAIT',
    'REFIX_HOVER_BARRIER_ABORT': 'PAIR_BARRIER_WAIT',
    'HIGH_CHECKPOINT_DR_BUDGET_EXCEEDED': 'SELF_POSE_UNCERTAIN',
    'REFIX_HORIZON_INFEASIBLE': 'SELF_POSE_UNCERTAIN',
    'REFIX_DISAGREEMENT': 'PAIR_DECISION_EXCHANGE',
    'REFIX_PARTNER_STATUS_UNSEEN': 'PAIR_DECISION_EXCHANGE'}


def failure_cause(reason):
    """Cause label for one controller failure name (labelled, not a proof of cause)."""
    from harness import pair_stage_probe as sp
    from harness import zone_pair_highpose_blind_close as blind
    from harness import zone_pair_highpose_arrival_confirm as arrival
    if reason is None:
        return None
    if reason in blind.HOVER_CODES:
        return {'code': 'HOVER_NOT_CONFIRMED', 'sub': reason}
    if reason in blind.BLIND_CODES:
        return {'code': 'BLIND_WINDOW_CLOSED', 'sub': reason}
    if reason == arrival.FAILURE:
        return {'code': arrival.CAUSE, 'sub': reason}
    code = sp.FAILURE_TO_CAUSE.get(reason) or V98_FAILURE_TO_CAUSE.get(reason) or ('PARTNER_ABORT' if str(reason).startswith('PARTNER') else 'UNCLASSIFIED')
    return {'code': code, 'sub': reason}


def controller_outcome(runtime):
    """Per-robot final controller state/failure and job ends (report only)."""
    rows = {}
    for session in getattr(getattr(runtime, 'team', None), 'sessions', None) or []:
        for rid, ep in session['endpoints'].items():
            rows[rid] = {'state': ep.controller.state, 'failure': ep.controller.failure,
                         'failure_cause': failure_cause(ep.controller.failure),
                         'high_carry_pose': any(e.get('event') == 'high_carry_pose' for e in ep.events),
                         'carry_go': sum(e.get('event') == 'barrier_go' and e.get('barrier') == 'carry' for e in ep.events)}
    for rid, own in (getattr(runtime, 'actors', None) or {}).items():
        rows.setdefault(rid, {})['jobs_ended'] = [{k: j.get(k) for k in ('kind', 'outcome')} for j in own.jobs_done]
    return rows


def time_case(case, check):
    return case['checkpoint'] if check == 'p03' else 'carry_full_route'


def run_case(bundle, out, *, seed, backend_factory, runtime_factory=Runtime,
             calibration=None, calibration_sha=None):
    # Check even a direct caller before creating output/backend/provider.
    starts.require_dev_seed(seed)
    mode = bundle.get('admission_mode', contract.MEASURED_SIM)
    cal = contract.calibration_for(mode, calibration, calibration_sha, bundle['map_id'])
    contract.require_runnable(bundle)
    time_budget.require_feasible(contract.resolve(bundle['map_id'])[0], time_case(bundle['case'], bundle['check']),
                                 bundle['check'], calibration=cal)
    expected = {**contract.bundle(bundle['map_id'], bundle['check'], mode),
                'source_sha': bundle['source_sha'], 'case': bundle['case']}
    if (contract.base.digest(bundle) != contract.base.digest(expected)
            or bundle['case'] not in contract.cases(bundle['check'], bundle['map_id'])):
        raise ValueError('v96 bundle/case mismatch')
    return student_run_case(bundle, out, seed=seed, backend_factory=backend_factory,
        runtime_factory=runtime_factory, calibration=calibration, calibration_sha=calibration_sha)


def student_run_case(bundle, out, *, seed, backend_factory, runtime_factory=Runtime,
                     calibration=None, calibration_sha=None, probe=None):
    """Student-only copy of scripts/run_final_pair_v3.run_case with the v96 cap.

    The parent hard-codes the v88 120 SIM s student cap. v96 uses the
    coordinator's a-priori amendment (contract.CASE_CAP_S per case: 300, v98-cap-3 900).
    Loop, clock, eval_sample/capture order and records are otherwise the
    parent's; no collection branch (v96 has no calibration checks).
    probe (STAGE_PROBES key): same loop, stops at the stage end/failure or the
    probe cap and reports a STAGE_PROBE_* status, never COLLECTED_UNQUALIFIED.
    """
    import os
    # Direct callers get the same admission as run_case (REVIEW_363 re-review
    # #2): the calibration must match the bundle's own admission mode, so a DEV
    # file can never run inside a MEASURED_SIM (unlabelled) bundle.
    mode = bundle.get('admission_mode', contract.MEASURED_SIM)
    seed_record = seed_admission(seed, probe, mode)    # before the output folder and the backend (delta4 P1-1)
    contract.calibration_for(mode, calibration, calibration_sha, bundle['map_id'])
    contract.require_runnable(bundle)
    out = Path(out)
    cap = contract.CASE_CAP_S
    if (bundle['check'] not in contract.CHECKS or bundle['case']['sim_cap_s'] != cap
            or bundle['timing'] != contract.execution_timing(bundle['check'])):
        raise ValueError('v96 case cap/timing differs from the registered student protocol')
    if probe is not None:
        if bundle.get('admission_mode') != contract.DEV_PILOT or probe not in STAGE_PROBES:
            raise ValueError('v96 stage probes are DEV_PILOT FUNCTIONAL_DEV diagnostics only')
        cap = STAGE_PROBES[probe]['cap_s']
    staged = probe is not None and STAGE_PROBES[probe].get('staged', False)
    staging_record = None
    if staged:
        static_, _, _ = contract.resolve(bundle['map_id'])
        from harness.zone_final_pair_skill import task
        beam = task(static_)['beam_pose']
        stations = staging.spawn_poses(static_, beam, probe)
        staging_record = {'stage': probe, 'beam_xyyaw_staging': list(beam), 'stations_xyyaw': stations,
                          'priors': {rid: staging.stated_prior(st) for rid, st in stations.items()},
                          'qualification': 'TEST SETUP before the controller exists (DEV stage probe)',
                          'ground_truth_inputs': {
                              'priors.*.mean_xyyaw': 'true staged spawn pose',
                              'stations_xyyaw': 'true staged spawn pose (sim harness)',
                              'teacher_commands': 'teacher pre-roll (HIGH entries: gripped/lifted claims)'},
                          **staging.TEST_SETUP_GT}
        real_backend = backend_factory
        from sim.final_pair_v3 import PhysicsBackend as _V3
        from sim.final_pair_highpose_clock import PhysicsBackend as _V3Clock
        if real_backend in (_V3, _V3Clock):   # StagedBackend carries host clock v2 itself
            from sim.final_pair_highpose_staged import StagedBackend
            backend_factory = lambda b, o, *, seed: StagedBackend(b, o, seed=seed, stations=stations)
        if runtime_factory is Runtime:
            runtime_factory = lambda st, cal, sha, *, seed: staging.StagedRuntime(
                st, cal, sha, seed=seed, stage=probe, staging=staging_record)
    out.mkdir(parents=True, exist_ok=False)
    write(out/'bundle.json', bundle)
    write(out/'inputs/schedule.json', [])
    backend = runtime = None
    labels = ({k: bundle[k] for k in contract.DEV_PILOT_LABELS}
              if bundle.get('admission_mode') == contract.DEV_PILOT else {})
    if probe is not None:
        labels['stage_probe'] = {'stage': probe, **STAGE_PROBES[probe], 'case_result': False}
    commands = {rid: 0 for rid in contract.ROBOTS}
    result = {**labels, 'check': bundle['check'], 'case': bundle['case'], 'status': 'HOST_ERROR',
              'protocol_complete': False, 'physical_success': None, 'research_result': False,
              'student_control': True, 'reset_sim_cap_s': contract.RESET_CAP_S, 'check_sim_cap_s': cap,
              'timing': bundle['timing'], 'clearance_preflight': None, 'calibration_sha256': calibration_sha,
              'loadavg_start': list(os.getloadavg()), 'failure': None, **seed_record}
    try:
        backend = backend_factory(bundle, out, seed=seed)
        # 2026-10-05: which SIM clock the host used (host clock v2 = integer substeps; never pooled with earlier runs).
        from sim import final_pair_highpose_clock as host_clock
        result['host_clock'] = (host_clock.record() if getattr(backend, 'host_clock', None) == host_clock.ID
                                else {'id': 'float_running_sum_v1'})
        reset = backend.reset(contract.RESET_CAP_S)
        if not 0 <= reset <= contract.RESET_CAP_S+1e-8:
            raise RuntimeError('RESET_SIM_CAP_EXCEEDED')
        if staged:
            staging_record.update(staging.run_preroll(backend, STAGE_PROBES[probe]['preroll']))
            write(out/'stage_probe_staging.json', staging_record)
            result['staging'] = staging_record
        start = backend.now
        backend.set_deadline(start+cap)
        result['reset_sim_s'] = reset
        static, _, _ = contract.resolve(bundle['map_id'])
        runtime = runtime_factory(static, calibration, calibration_sha, seed=seed)
        runtime.initial_commands(start, backend.commands)
        steps = round(cap/contract.TICK_S)
        case_end_at = None
        for i in range(steps+1):
            # Raw labels have no return channel into the command selector.
            backend.eval_sample()
            runtime.on_frames(backend.now, backend.capture())
            if i == steps:
                break
            for rid, action in runtime.step(backend.now):
                backend.issue(rid, action)
                runtime.on_command(rid, backend.now, action)
                commands[rid] += 1
            for rid, action in runtime.arm_step(backend.now):
                backend.issue(rid, action)
                runtime.on_command(rid, backend.now, action)
                commands[rid] += 1
            backend.advance_to(start+(i+1)*contract.TICK_S)
            if probe is not None:
                progress = stage_progress(runtime, probe)
                if progress['stop']:
                    break
            elif contract.DEV_LIGHT:
                # DEV light (2026-10-05): a full case used to run to the 900 s cap after both pair jobs had ended
                # (v105light a6fec250: jobs ended at 138.85 s, ~25 min of idle SIM). Stop CASE_END_SETTLE_S after both
                # robots' pair/carry jobs have ended (control-side job records only, no eval labels).
                ended = jobs_ended_all(runtime)
                if ended and case_end_at is None:
                    case_end_at = backend.now
                    result['case_end'] = {'rule': 'dev_light_both_jobs_ended', 'jobs_ended_sim_s': backend.now-start,
                                          'settle_s': CASE_END_SETTLE_S}
                if case_end_at is not None and backend.now-case_end_at >= CASE_END_SETTLE_S-1e-9:
                    break
        if probe is not None:
            progress = stage_progress(runtime, probe)
            status = ('STAGE_PROBE_REACHED' if progress['done'] and not progress['failures'] else
                      'STAGE_PROBE_FAILED' if progress['failures'] or progress['jobs_ended'] else
                      'STAGE_PROBE_NOT_REACHED')
            result.update(status=status, stage_progress=progress, check_sim_s=backend.now-start)
        else:
            if abs(backend.now-start-cap) > 1e-7:
                raise RuntimeError('INCOMPLETE_BOUNDED_PROTOCOL')
            result.update(protocol_complete=True, status='COLLECTED_UNQUALIFIED', check_sim_s=backend.now-start)
    except Exception as exc:
        result.update(status='HOST_ERROR', failure={'type': type(exc).__name__, 'message': str(exc),
            'class': 'ENOSPC' if getattr(exc, 'errno', None) == errno.ENOSPC else 'HOST_ERROR'})
    finally:
        if runtime is not None:
            try:
                record = runtime.record()
                write(out/'student_record.json', record)
                result['commands_issued'] = commands
                result['controller_outcome'] = controller_outcome(runtime)
                if bundle['check'] == 'p03' and probe is None:
                    result['checkpoint'] = {**checkpoint_record(record, bundle['case']['checkpoint']), **labels}
            except Exception as exc:
                result.update(status='HOST_ERROR', record_error=str(exc))
        for owner in (runtime, backend):
            if owner is not None:
                try:
                    owner.close()
                except Exception as exc:
                    result.update(status='HOST_ERROR', cleanup_error=str(exc))
        if (out/'student_record.json').is_file():
            # Evaluation only (v98 receipts are "σ 예산 영수증", not accuracy evidence): after the loop has ended, NEES of
            # every HIGH checkpoint receipt against the eval-only truth. No return channel; never changes the status.
            try:
                from scripts import eval_highpose_receipt_nees as receipt_nees
                result['receipt_nees_eval_only'] = receipt_nees.write_for_run(out)
            except Exception as exc:  # noqa: BLE001 - evaluation only, recorded, never touches status
                result['receipt_nees_eval_only'] = {'error': f'{type(exc).__name__}: {exc}'[:300]}
        result['loadavg_end'] = list(os.getloadavg())
        write(out/'result.json', result)
        write(out/'artifacts.sha256.json', {str(p.relative_to(out)): contract.base.sha(p)
            for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'artifacts.sha256.json'})
    return result


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', choices=contract.CHECKS, required=True)
    p.add_argument('--map-id', choices=contract.registry()['maps'])
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--lock-owner', choices=('codex', 'claude', 'kiro'))
    p.add_argument('--calibration', type=Path)
    p.add_argument('--calibration-sha256')
    p.add_argument('--seed', type=int, default=911)
    p.add_argument('--admission', choices=('measured-sim', 'dev-pilot'), default='measured-sim',
                   help='dev-pilot: exact registered sha256 only; FUNCTIONAL_DEV, never promotable')
    p.add_argument('--sim-slot', help='owned sim-* slot under a non-timing SIM coordinator; omitted uses exclusive physics lock')
    p.add_argument('--case-id', help='run one registered case of --check/--map-id in this process')
    p.add_argument('--stage-probe', choices=sorted(STAGE_PROBES),
                   help='DEV_PILOT prefix stage probe on one case; STAGE_PROBE_* status, never a case result')
    return p


def admission_mode(args):
    return contract.DEV_PILOT if args.admission == 'dev-pilot' else contract.MEASURED_SIM


# 2026-10-05 coordinator (speed): extra DEV stage-probe seeds to find more failure types at once. Stage probes only,
# DEV_PILOT only, labelled in the plan; never evidence, never pooled with seed 911 or a case result.
STAGE_PROBE_DEV_EXTRA_SEEDS = (912, 913)


def seed_admission(seed, probe, mode):
    """One seed rule for every execution entry point (CLI plan, run_case, student_run_case; review delta4 P1-1).

    Seed 911 (FUNCTIONAL_DEV replay) everywhere; 912/913 only for a DEV_PILOT stage probe. Anything else, including
    the confirmation seeds, is refused before an output folder or a backend exists. Returns the record for result.json.
    """
    confirmation = {row['seed'] for row in starts.registration()['confirmation_starts']}
    if set(STAGE_PROBE_DEV_EXTRA_SEEDS) & (confirmation | {starts.DEV_SEED}):
        raise ValueError('extra DEV seeds must differ from the dev and confirmation seeds')
    extra = (seed != starts.DEV_SEED and seed in STAGE_PROBE_DEV_EXTRA_SEEDS
             and probe is not None and mode == contract.DEV_PILOT)
    if not extra:
        starts.require_dev_seed(seed)
    return {'seed': seed, 'extra_dev_seed': ({'seeds': list(STAGE_PROBE_DEV_EXTRA_SEEDS), 'evidence': False,
                                              'pooled': False} if extra else None)}


def extra_dev_seed(args):
    mode = contract.DEV_PILOT if args.admission == 'dev-pilot' else contract.MEASURED_SIM
    try:
        return seed_admission(args.seed, args.stage_probe, mode)['extra_dev_seed'] is not None
    except ValueError:
        return False


def plan(args):
    seed_admission(args.seed, args.stage_probe, admission_mode(args))
    starts.registration()
    cases = contract.cases(args.check, args.map_id)
    if args.case_id is not None:
        cases = [c for c in cases if c['id'] == args.case_id]
        if len(cases) != 1:
            raise ValueError('--case-id must name exactly one registered case of this check/map')
    mode = admission_mode(args)
    if args.stage_probe is not None and (mode != contract.DEV_PILOT or args.case_id is None):
        raise ValueError('--stage-probe needs --admission dev-pilot and one --case-id')
    bundles = [{**contract.bundle(c['map_id'], args.check, mode), 'case': c,
                'source_sha': args.expected_source_sha} for c in cases]
    blocked = []
    try:
        for c in cases:
            contract.calibration_for(mode, args.calibration, args.calibration_sha256, c['map_id'])
    except (ValueError, OSError, KeyError, TypeError) as exc:
        blocked.append(str(exc))
    try:
        for b in bundles:
            contract.require_runnable(b)
    except ValueError as exc:
        blocked.append(str(exc))
    lower_bounds = [row for c in cases for row in time_budget.bounds(contract.resolve(c['map_id'])[0], args.check)
                    if row['case'] == time_case(c, args.check)]
    blocked.extend('TIME_LOWER_BOUND_EXCEEDS_CASE_CAP: '+r['map_id']+'/'+r['case'] for r in lower_bounds if not r['feasible'])
    value = {'time_lower_bounds': lower_bounds, 'cohort_role': 'FUNCTIONAL_DEV_REPLAY',
        'confirmation_sample': False, 'admission_mode': mode,
        **(contract.DEV_PILOT_LABELS if mode == contract.DEV_PILOT else {}), 'execution_bundle_id': contract.BUNDLE_ID, 'status': 'DRAFT_UNSEALED',
        'check': args.check, 'execution_started': False, 'cases': cases, 'denominator': len(cases),
        'runnable': not blocked, 'blocked_on': blocked,
        'precondition': contract.DEV_PILOT_PRECONDITION if mode == contract.DEV_PILOT else contract.PRECONDITION,
        'calibration_sha256': args.calibration_sha256, 'source_sha': args.expected_source_sha,
        'seed': args.seed, 'extra_dev_seed': ({'seeds': list(STAGE_PROBE_DEV_EXTRA_SEEDS), 'evidence': False,
                                                'pooled': False} if extra_dev_seed(args) else None),
        'bundles_sha256': [contract.base.digest(b) for b in bundles],
        'case_selection': args.case_id, 'registered_denominator': len(contract.cases(args.check, args.map_id)),
        'stage_probe': ({'stage': args.stage_probe, **STAGE_PROBES[args.stage_probe], 'case_result': False}
                        if args.stage_probe else None),
        'lock_mode': 'sim_slot' if args.sim_slot else 'exclusive', 'sim_slot': args.sim_slot,
        'physical_success': None, 'research_result': False}
    return value, bundles


def main(argv=None):
    args = parser().parse_args(argv)
    admission, bundles = plan(args)
    if not args.execute:
        print(json.dumps(admission, ensure_ascii=False, indent=2))
        return 0
    if not admission['runnable']:
        raise ValueError('; '.join(admission['blocked_on']))
    check_source(args.expected_source_sha)
    primary = Path(subprocess.check_output(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'],
        cwd=contract.ROOT, text=True).strip()).parent
    if not args.output.is_absolute() or not args.output.resolve().is_relative_to((primary/'outputs').resolve()):
        raise ValueError('raw output must be absolute under primary outputs')
    if args.output.exists():
        raise FileExistsError(args.output)
    if shutil.disk_usage(primary).free < 10*1024**3:
        raise OSError(errno.ENOSPC, 'less than 10 GiB free')
    from scripts.agent_lock import DEFAULT_ROOT, status
    from scripts.agent_sim_slots import require_sim_slot, sim_snapshot, sim_holders
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=contract.ROOT, text=True).strip()
    if args.sim_slot:
        require_sim_slot(DEFAULT_ROOT, slot=args.sim_slot, owner=args.lock_owner, branch=branch)
    else:
        held = status(DEFAULT_ROOT)
        if (not held or not held['pid_alive'] or held['owner'] != args.lock_owner
                or held['branch'] != branch or sim_holders(DEFAULT_ROOT)):
            raise ValueError('live owned host lock for this branch required')
    from sim.final_pair_highpose_clock import PhysicsBackend   # v98 host clock v2 (integer substep time)
    args.output.mkdir(parents=True)
    admission.update(execution_started=True, host_start=sim_snapshot(DEFAULT_ROOT))
    write(args.output/'plan.json', admission)
    shutil.copyfile(args.calibration, args.output/('dev_pilot_calibration.json' if admission_mode(args) == contract.DEV_PILOT
                                                   else 'measured_calibration.json'))
    results = []
    for bundle in bundles:
        results.append(run_case(bundle, args.output/bundle['case']['id'], seed=args.seed,
            backend_factory=PhysicsBackend, calibration=args.calibration, calibration_sha=args.calibration_sha256)
            if args.stage_probe is None else
            student_run_case(bundle, args.output/bundle['case']['id'], seed=args.seed, backend_factory=PhysicsBackend,
                             calibration=args.calibration, calibration_sha=args.calibration_sha256,
                             probe=args.stage_probe))
        if results[-1]['status'] == 'HOST_ERROR':
            break
    unattempted = [c['id'] for c in admission['cases'][len(results):]]
    mode = admission_mode(args)
    unchanged = all({**contract.bundle(b['map_id'], args.check, mode), 'case': b['case'],
                     'source_sha': args.expected_source_sha} == b for b in bundles)
    failed = bool(unattempted) or not unchanged or any(r['status'] == 'HOST_ERROR' for r in results)
    labels = contract.DEV_PILOT_LABELS if mode == contract.DEV_PILOT else {}
    status_ = ('HOST_ERROR' if failed else 'STAGE_PROBE_COLLECTED' if args.stage_probe else 'COLLECTED_UNQUALIFIED')
    write(args.output/'result.json', {**labels, 'status': status_, 'stage_probe': admission['stage_probe'],
        'cases': results, 'unattempted': unattempted, 'denominator': len(admission['cases']),
        'case_selection': args.case_id, 'registered_denominator': admission['registered_denominator'],
        'lock_mode': admission['lock_mode'], 'sim_slot': args.sim_slot,
        'host_start': admission['host_start'], 'host_end': sim_snapshot(DEFAULT_ROOT),
        'source_unchanged': unchanged, 'physical_success': None, 'research_result': False})
    return int(failed)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
