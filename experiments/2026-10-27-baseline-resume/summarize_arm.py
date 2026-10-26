"""Post-run CPU audit only. Never imports/loads a policy or runs physics/rendering.

Geometry/funnel and carry evaluation come from the frozen T source. READY is
the registered simultaneous policy-stage observation; physical success remains
the original raw physical_success AND carry_eval.success. Raw files are read only.
"""
import argparse
from collections import Counter
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys

STAGES = ('approach', 'alignment', 'READY', 'grasp', 'hold_3s', 'carry_1m', 'door', 'place')
PACKAGE = Path('/home/ugrp/ugrp-sim/baseline-treatment')
TEACHER = Path('/home/ugrp/ugrp-sim/src/26f84d0f0ada1c33473c83cca2d3415ce51bd247')
STUDENT = Path('/home/ugrp/ugrp-sim/src/pairact-p5/student')
# Literal inventories from frozen S PairActBarrier/StudentBarrier and the
# registered treatment controller. Unknown records cannot prove zero rejects.
BARRIER_EVENTS = {'READY', 'proposal_rejected', 'stage_proposal_released_after_GO_ACK',
                  'treatment_close_gate_bypassed', 'PLACE_READY', 'place_proposal_released_after_GO_ACK'}
REJECTION_REASONS = {'close_before_learned_ready', 'execution_without_GO_ACK'}
PROTOCOL_EVENTS = {'GO', 'ACK', 'START', 'READY_withdrawn_rearm'}
OBSERVATION_SOURCES = {'approach': 'eval_only_GT_geometry', 'alignment': 'eval_only_GT_geometry',
    'READY': 'simultaneous_own_policy_stage_ready', 'grasp': 'eval_only_GT_contact',
    'hold_3s': 'original_physics_held_flag', 'carry_1m': 'original_eval_only_carry_evaluator',
    'door': 'original_eval_only_carry_evaluator', 'place': 'original_eval_only_carry_evaluator'}


def barrier_inventory(student, roles, arm):
    events, rejects, issues = Counter(), Counter(), []
    collections = student.get('barrier_events')
    if not isinstance(collections, dict) or set(collections) != set(roles):
        return events, rejects, ['missing_or_wrong_barrier_event_robot_inventory']
    for rid, collection in collections.items():
        if not isinstance(collection, list):
            issues.append('invalid_barrier_event_collection:' + rid)
            continue
        for event in collection:
            name = event.get('event') if isinstance(event, dict) else None
            events[name or 'UNKNOWN_NOT_RECORDED'] += 1
            if name not in BARRIER_EVENTS:
                issues.append('unknown_or_missing_barrier_event:' + str(name))
            if name == 'proposal_rejected':
                reason = event.get('reason_category') or 'INVALID_EMPTY_REASON'
                rejects[reason] += 1
                if reason not in REJECTION_REASONS:
                    issues.append('unknown_or_empty_rejection_reason:' + str(reason))
                if arm == 'arm_c': issues.append('unexpected_ArmC_proposal_rejection')
                if reason == 'close_before_learned_ready': issues.append('removed_G1_gate_rejection')
            if name == 'treatment_close_gate_bypassed' and event.get('reason_category') != 'close_before_learned_ready_suppressed':
                issues.append('unknown_or_missing_bypass_reason')
    return events, rejects, issues


def binomial_tail(n, k, p, upper):
    indices = range(k, n + 1) if upper else range(k + 1)
    return sum(math.comb(n, j) * p**j * (1-p)**(n-j) for j in indices)


def clopper_pearson(k, n):
    """Registered two-sided 95% exact binomial inversion, to adjacent floats."""
    if n == 0:
        return None
    def inverse(upper):
        lo, hi = 0., 1.
        while math.nextafter(lo, math.inf) < hi:
            mid = lo + (hi-lo) / 2
            value = binomial_tail(n, k, mid, upper)
            if (value < .025) if upper else (value > .025):
                lo = mid
            else:
                hi = mid
        return lo + (hi-lo)/2
    return [0. if k == 0 else inverse(True), 1. if k == n else inverse(False)]


class Reader:
    def __init__(self):
        self.manifest = {}

    def bytes(self, nominal):
        nominal = Path(nominal)
        present = [p for p in (nominal, Path(str(nominal)+'.zst')) if p.is_file()]
        if len(present) != 1:
            raise ValueError('missing_or_ambiguous_record:' + str(nominal))
        path = present[0]
        packed = path.read_bytes()
        raw = subprocess.check_output(['zstd', '-qdc'], input=packed) if path.suffix == '.zst' else packed
        self.manifest[str(path)] = {'bytes': len(packed), 'sha256': hashlib.sha256(packed).hexdigest(),
                                   'decoded_bytes': len(raw), 'decoded_sha256': hashlib.sha256(raw).hexdigest()}
        return raw

    def json(self, path):
        return json.loads(self.bytes(path))

    def rows(self, path):
        return [json.loads(line) for line in self.bytes(path).splitlines() if line.strip()]


def sampled_hold(truth, roles):
    # Existing registered contact >=.5, min_z >=.012m, tilt <=10deg; 10Hz
    # samples are a diagnostic and do not replace the original physics judge.
    since, maximum = None, 0.
    for row in truth:
        stable = (all(min(row['contacts'][rid]) >= .5 for rid in roles)
                  and row['beam']['min_z'] >= .012 and row['beam']['tilt_deg'] <= 10.)
        since = (row['t'] if since is None else since) if stable else None
        maximum = max(maximum, 0. if since is None else row['t'] - since)
    return maximum


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arm', choices=('arm_c', 'arm_s'), required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    sys.dont_write_bytecode = True
    args.out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(TEACHER))
    from harness.pairact_student_eval import StudentFunnel
    from harness.pair_carry_eval import evaluate
    sys.path.insert(0, str(PACKAGE))
    from audit_cpu import read_physical_motion, termination, pilot_gate
    spec = importlib.util.spec_from_file_location('frozen_own_context', STUDENT/'harness/grasp_act_contract.py')
    context = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(context)
    reader = Reader()
    summary = reader.json(args.input/'summary.json')
    acknowledged = {int(row['world']): row for row in summary.get('worlds', [])}
    static = reader.json(TEACHER/'maps/zones_final_v3/zone_wide_two_doors_final_v3.json')
    episodes, errors, raw_by_world, motion_by_world = [], [], {}, {}
    stages, events, rejects, metric_totals, skills = Counter(), Counter(), Counter(), Counter(), Counter()
    frame_counts = {name: Counter() for name in STAGES[:5]}
    input_audit = Counter()
    state_changes = {}
    for world in range(20):
        base = args.input/f'world-{world:03d}'
        row = {'world': world, 'planned_seed': 8342000+world, 'raw_dir': str(base/'raw')}
        try:
            raw = reader.json(base/'raw/result.json')
            row.update(raw_status=raw.get('status'), acknowledged_completed=world in acknowledged)
            if raw.get('status') != 'complete' or world not in acknowledged:
                row.update(normal_complete=False, success=None,
                    completion_class=('administrative_interruption' if summary.get('status') == 'treatment_administrative_stop'
                                      else 'HOST_ERROR' if raw.get('status') == 'HOST_ERROR' or raw.get('HOST_ERROR') else 'uncompleted'),
                    reason_category=raw.get('error_type') or raw.get('end_reason') or 'completion_not_acknowledged',
                    raw_sim_s=raw.get('sim_s'), raw_cap_end=raw.get('cap_end'),
                    blocked_object='UNKNOWN:not_observed', min_gap_m=None,
                    gap_scope='not measured in available completed records')
                episodes.append(row)
                continue
            plan = reader.json(base/'raw/plan.json')
            row['seed'] = plan['seed']
            if plan['seed'] != row['planned_seed']:
                errors.append({'world': world, 'issue': 'registered_seed_mismatch'})
            roles = plan['roles']
            truth = reader.rows(base/'raw/eval-only.jsonl')
            log = reader.rows(base/'raw/student-eval.jsonl')
            by_t = {value['t']: value for value in truth}
            student = raw.get('student_eval') or {}
            treatment = student.get('treatment') or {}
            metrics = treatment.get('metrics') or {}
            world_errors = []
            if treatment.get('mode') != args.arm or set(metrics) != set(roles):
                world_errors.append('wrong_or_missing_treatment_metadata')
            for rid, value in metrics.items():
                ticks = value.get('ticks')
                if not (type(ticks) is int and ticks > 0 and value.get('inference_calls') == ticks
                        and value.get('discard_calls') == ticks and value.get('issued_ticks') == ticks
                        and sum(value.get('stage_counts', {}).values()) == ticks
                        and value.get('skill_counts') == {'grasp': ticks} and value.get('state225_nonzero') == 0):
                    world_errors.append('cadence_HOLD_or_stage_sample_mismatch:' + rid)
                if args.arm == 'arm_c' and value.get('software_hold_ticks') != 0:
                    world_errors.append('unexpected_ArmC_software_hold:' + rid)
                stages.update(value.get('stage_counts', {})); skills.update(value.get('skill_counts', {}))
                for key in ('ticks','inference_calls','discard_calls','issued_ticks','software_hold_ticks',
                            'nonzero_wheel_ticks','state225_nonzero'):
                    if type(value.get(key)) is int:
                        metric_totals[key] += value[key]
                    else:
                        world_errors.append('missing_metric:' + rid + ':' + key)
            corrections = {k: student.get(k) for k in ('gt_inputs_to_student','teacher_steps','truth_inputs','teacher_actions')}
            if any(type(v) is not int or v != 0 for v in corrections.values()):
                world_errors.append('nonzero_or_unmeasured_input_correction_counter')
            observed_events, observed_rejects, event_issues = barrier_inventory(student, roles, args.arm)
            events.update(observed_events); rejects.update(observed_rejects); world_errors.extend(event_issues)
            protocol_records = student.get('protocol_events')
            protocol = Counter()
            if not isinstance(protocol_records, list):
                world_errors.append('missing_or_invalid_protocol_event_inventory')
            else:
                for event in protocol_records:
                    name = event.get('event') if isinstance(event, dict) else None
                    protocol[name or 'UNKNOWN_NOT_RECORDED'] += 1
                    if name not in PROTOCOL_EVENTS: world_errors.append('unknown_or_missing_protocol_event:' + str(name))
            funnel = StudentFunnel()
            previous_command, previous_state, previous_rgb, changes = {}, {}, {}, {}
            trace_stages = {rid:Counter() for rid in roles}
            trace_software_hold, trace_nonzero_wheels = Counter(), Counter()
            done_intervals, active_done, close_issued = {rid:[] for rid in roles}, {}, Counter()
            policy_ready_ticks = protocol_ready_ticks = permit_robot_ticks = 0
            policy_ready_robot_ticks = protocol_ready_robot_ticks = 0
            first_policy_ready_t = expected_funnel_ready_t = None
            for tick_index, entry in enumerate(log, 1):
                now = entry['t']; truth_row = by_t[now]
                if set(entry['inputs']) != set(roles): world_errors.append('input_robot_set_mismatch')
                policy_ready = {rid: entry['issued'][rid]['stage'] == 'ready' for rid in roles}
                policy_ready_ticks += int(all(policy_ready.values()))
                policy_ready_robot_ticks += sum(policy_ready.values())
                if all(policy_ready.values()) and first_policy_ready_t is None: first_policy_ready_t = now
                protocol_ready_ticks += int(all(entry.get('ready', {}).get(rid, False) for rid in roles))
                protocol_ready_robot_ticks += sum(bool(entry.get('ready', {}).get(rid, False)) for rid in roles)
                permit_robot_ticks += sum(bool(entry['issued'][rid].get('permit')) for rid in roles)
                # Keep original geometry, contact and physics-held flag. Only
                # READY's registered observation source is policy stage.
                passed = funnel.add(now, truth_row, roles, policy_ready, entry['eval_passed']['hold_3s'])
                if passed['READY'] != all(policy_ready.values()): world_errors.append('READY_policy_source_mismatch')
                # A8 retains the sequential approach/alignment prefix. A raw
                # simultaneous READY before alignment is not a funnel pass.
                if 'alignment' in funnel.first and all(policy_ready.values()) and expected_funnel_ready_t is None:
                    expected_funnel_ready_t = now
                if funnel.first.get('READY') != expected_funnel_ready_t:
                    world_errors.append('READY_first_eligible_policy_tick_mismatch')
                for index, name in enumerate(STAGES[:5]):
                    eligible = index == 0 or STAGES[index-1] in funnel.first
                    frame_counts[name]['eligible'] += int(eligible)
                    frame_counts[name]['passed_cumulative'] += int(eligible and name in funnel.first)
                    frame_counts[name]['rejected'] += int(eligible and name not in funnel.first)
                    if name != 'READY' and passed[name] != entry['eval_passed'][name]:
                        world_errors.append('original_eval_geometry_or_contact_flag_mismatch:' + name)
                input_audit['frames'] += 1
                for rid, obs in entry['inputs'].items():
                    input_audit['robot_ticks'] += 1
                    try: vector = context.context(obs)
                    except (ValueError, TypeError, KeyError) as error:
                        world_errors.append('input_allowlist_or_context:' + str(error)); continue
                    if obs['robot_id'] != rid or obs['role'] != roles[rid]: world_errors.append('wrong_own_identity_or_role')
                    if obs['skill'] != 'grasp' or vector[225] != 0: world_errors.append('grasp_HOLD_violation')
                    if rid in previous_command and obs['issued'][-1] != previous_command[rid]:
                        world_errors.append('own_issued_history_mismatch')
                    issued = entry['issued'][rid]
                    trace_stages[rid][issued['stage']] += 1
                    trace_software_hold[rid] += int(issued['software_hold'])
                    trace_nonzero_wheels[rid] += int(any(w != 0 for w in issued['command']['wheels']))
                    if issued['inference_calls'] != tick_index or issued['discard_calls'] != tick_index:
                        world_errors.append('trace_cadence_mismatch:' + rid)
                    close_issued[rid] += int(issued['command']['pwm']['1'] < obs['issued'][-1]['pwm']['1'])
                    segment = issued.get('segment')
                    prior_done = active_done.get(rid)
                    if prior_done and (not issued.get('done') or prior_done['segment'] != segment):
                        done_intervals[rid].append(prior_done);active_done.pop(rid,None)
                    if issued.get('done'):
                        interval = active_done.setdefault(rid,{'segment':segment,'first_t':now,'last_t':now,'ticks':0})
                        interval['last_t'] = now;interval['ticks'] += 1
                    for ref in obs['rgb']:
                        input_audit['own_rgb_refs'] += 1
                        if ref['robot_id'] != rid or not ref['path'].startswith('rgb/'+rid+'/'):
                            world_errors.append('foreign_camera_reference')
                    previous_command[rid] = entry['issued'][rid]['command']
                    change = changes.setdefault(rid, Counter())
                    rgb = [value['sha256'] for value in obs['rgb']]
                    if rid in previous_state:
                        old = previous_state[rid]
                        change['history_state_changed_ticks'] += int(vector[:224] != old[:224])
                        change['history_state_L1_sum'] += sum(abs(a-b) for a,b in zip(vector[:224], old[:224]))
                        change['state250_changed_ticks'] += int(vector[250] != old[250])
                        change['state251_changed_ticks'] += int(vector[251] != old[251])
                        change['own_rgb_history_changed_ticks'] += int(rgb != previous_rgb[rid])
                        change['current_own_rgb_sha_changed_ticks'] += int(rgb[-1] != previous_rgb[rid][-1])
                    previous_state[rid], previous_rgb[rid] = vector, rgb
            for rid, value in metrics.items():
                if value.get('ticks') != len(log): world_errors.append('trace_vs_metric_ticks:' + rid)
                if value.get('stage_counts') != dict(trace_stages[rid]): world_errors.append('trace_vs_stage_counts:' + rid)
                if value.get('software_hold_ticks') != trace_software_hold[rid]: world_errors.append('trace_vs_software_hold:' + rid)
                if value.get('nonzero_wheel_ticks') != trace_nonzero_wheels[rid]: world_errors.append('trace_vs_nonzero_wheel:' + rid)
            for rid, interval in active_done.items(): done_intervals[rid].append(interval)
            carry = raw.get('carry_eval')
            carry_equal = None
            if carry is not None:
                if type(carry.get('success')) is not bool: world_errors.append('carry_success_not_boolean')
                recomputed = evaluate(truth, static, roles, lower_start_t=carry['lower_start_t'], handover_t=carry['handover_t'])
                # Match the earlier independent recount: compare every field
                # emitted by the frozen evaluator; retain optional extra record
                # metadata without treating it as a numerical outcome mismatch.
                carry_equal = all(carry.get(key) == value for key,value in recomputed.items())
                if not carry_equal: world_errors.append('original_carry_evaluator_recount_mismatch')
            record = funnel.record(carry)
            motion = read_physical_motion(base/'raw', raw)
            # The registered translation gate is only the first four completed
            # C lanes. Other lanes' motion is reported without adding a gate.
            motion_by_world[world], raw_by_world[world] = motion, raw
            (args.out/f'physical-motion-world-{world:03d}.json').write_text(json.dumps(motion, indent=2))
            term = termination(raw, acknowledged[world].get('cap_end'))
            if term['audit_issues']: world_errors.extend(term['audit_issues'])
            physical = raw.get('physical_success')
            if type(physical) is not bool: world_errors.append('physical_success_not_boolean')
            if physical is True and carry is None: world_errors.append('physical_success_without_carry_evaluation')
            success = bool(physical and carry and carry.get('success'))
            row.update(normal_complete=True, completion_class='normal_complete', success=success, raw_physical_success=physical,
                carry_success=(carry or {}).get('success'), carry_recount_equal=carry_equal,
                termination=term, sim_s=raw.get('sim_s'), funnel=record['reached'], first_pass_t=record['first_pass_t'],
                correction_counters=corrections, treatment_metrics=metrics, protocol_events=dict(protocol),
                barrier_event_counts=dict(observed_events), actual_rejection_reasons=dict(observed_rejects),
                simultaneous_policy_READY_ticks=policy_ready_ticks, simultaneous_protocol_READY_ticks=protocol_ready_ticks,
                policy_READY_robot_ticks=policy_ready_robot_ticks, protocol_READY_robot_ticks=protocol_ready_robot_ticks,
                READY_source_crosscheck={'first_simultaneous_policy_t':first_policy_ready_t,
                    'first_simultaneous_policy_t_after_alignment':expected_funnel_ready_t,
                    'funnel_first_READY_t':funnel.first.get('READY'),
                    'matches':funnel.first.get('READY') == expected_funnel_ready_t},
                protocol_GO_count=protocol['GO'], protocol_ACK_count=protocol['ACK'], protocol_START_count=protocol['START'],
                protocol_observation_source='original_READY_GO_ACK_boolean_protocol_log',
                permit_robot_ticks=permit_robot_ticks, state_changes={rid:dict(value) for rid,value in changes.items()},
                release_t=treatment.get('release_t'), robot_finish_t=treatment.get('robot_finish_t'),
                final_segments=treatment.get('segments'), close_issued_ticks=dict(close_issued),
                close_proposal_ticks=dict(close_issued) if args.arm=='arm_c' else None,
                close_proposal_scope=('C current proposal passes through unchanged; count equals issued close deltas'
                    if args.arm=='arm_c' else 'proposal PWM is absent in frozen trace; G1 bypass events measure withdrawal-stage close proposals only, not all stages'),
                own_done_true_intervals=done_intervals,
                max_stable_hold_s_raw=raw.get('max_stable_hold_s'), max_sampled_stable_hold_s=sampled_hold(truth, roles),
                robot_robot_contacts=None, robot_robot_contacts_scope='not measured in original stored fields',
                drop_events=(carry or {}).get('drop_events'), drop_scope='original carry evaluator' if carry else 'carry phase unobserved',
                reason_category=('success' if success else 'cap_end' if raw.get('cap_end') else raw.get('end_reason') or 'UNKNOWN_NOT_RECORDED'),
                blocked_object='UNKNOWN:not_observed', min_gap_m=None, gap_scope='not measured; no obstacle identity inferred',
                audit_issues=sorted(set(world_errors)))
            errors.extend({'world':world,'issue':issue} for issue in sorted(set(world_errors)))
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
            row.update(normal_complete=False, completion_class='unmeasured_record_or_audit_error', success=None,
                       reason_category='UNMEASURED_RECORD_OR_AUDIT_ERROR', error=str(error))
            errors.append({'world':world,'issue':str(error)})
        row.setdefault('blocked_object','UNKNOWN:not_observed');row.setdefault('min_gap_m',None)
        row.setdefault('gap_scope','not measured in available completed records')
        episodes.append(row)
        print(json.dumps({k:row.get(k) for k in ('world','seed','normal_complete','success','reason_category')}),flush=True)
    complete = [row for row in episodes if row.get('normal_complete')]
    n, successes = len(complete), sum(row['success'] for row in complete)
    candidate = []
    previous = n
    for stage in STAGES:
        passed = sum(row['funnel'][stage] for row in complete)
        candidate.append({'stage':stage,'passed_cumulative_N':passed,'rejected_N':previous-passed,'denominator_normal_N':n,
                          'observation_source':OBSERVATION_SOURCES[stage]})
        previous = passed
    speed = reader.json(args.input/'treatment-first30-audit.json')
    pilot = reader.json(args.input/'pilot-gate.json') if args.arm == 'arm_c' else None
    pilot_recount = None
    if pilot and len(pilot.get('completed_worlds', [])) == 4:
        ids = pilot['completed_worlds']
        if all(world in raw_by_world for world in ids):
            pilot_recount = pilot_gate([(world,raw_by_world[world]) for world in ids],motion_by_world)
            if pilot_recount['checks'] != pilot['checks'] or pilot_recount['pass_gate'] != pilot['pass_gate']:
                errors.append({'issue':'pilot_original_vs_closed_log_recount_mismatch'})
    for source in [Path(__file__), PACKAGE/'audit_cpu.py', TEACHER/'harness/pairact_student_eval.py',
                   TEACHER/'harness/pair_carry_eval.py', STUDENT/'harness/grasp_act_contract.py']:
        reader.bytes(source)
    normal_complete = summary.get('status') == 'complete' and n == 20 and summary.get('completed_N') == 20
    integrity = normal_complete and not errors
    followup = (args.arm == 'arm_c' and integrity and pilot is not None and pilot.get('pass_gate') is True
                and speed.get('SPEED_GATE_FAIL') is False)
    frame_all = {name:dict(value) for name,value in frame_counts.items()}
    no_eligible_carry = frame_counts['hold_3s']['passed_cumulative'] == 0
    for stage in STAGES[5:]:
        frame_all[stage] = ({'eligible':0,'passed_cumulative':0,'rejected':0,
                             'scope':'no completed frame cumulatively passed hold_3s, so no downstream eligibility'}
                            if no_eligible_carry else {'eligible':None,'passed_cumulative':None,'rejected':None,
                             'scope':'per-frame carry/door/place flags not reconstructed; episode counts are measured'})
    for stage, counts in frame_all.items(): counts['observation_source'] = OBSERVATION_SOURCES[stage]
    event_gate_counts = [
        {'gate':'propose_robot_ticks','eligible':metric_totals['ticks'],'passed_cumulative':metric_totals['ticks'],'rejected':0},
        {'gate':'one_discard','eligible':metric_totals['ticks'],'passed_cumulative':metric_totals['discard_calls'],
         'rejected':metric_totals['ticks']-metric_totals['discard_calls']},
        {'gate':'fresh_inference','eligible':metric_totals['discard_calls'],'passed_cumulative':metric_totals['inference_calls'],
         'rejected':metric_totals['discard_calls']-metric_totals['inference_calls']},
        {'gate':'stage_sample','eligible':metric_totals['inference_calls'],'passed_cumulative':sum(stages.values()),
         'rejected':metric_totals['inference_calls']-sum(stages.values())},
        {'gate':'actual_proposal_acceptance','eligible':sum(stages.values()),
         'passed_cumulative':sum(stages.values())-sum(rejects.values()),'rejected':sum(rejects.values())}]
    result = {'schema':'ugrp.baseline.closed-arm-audit.v1','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'arm':args.arm,'raw_root':str(args.input),'planned_N':20,'batch_status':summary.get('status'),
        'started_N':summary.get('started_N'),'batch_completed_N':summary.get('completed_N'),'N_eff':n,
        'successes':successes,'success_rate':successes/n if n and integrity else None,
        'validity':'VALID_NORMAL_COMPLETE' if integrity else 'UNVERIFIED_OR_INCOMPLETE',
        'success_definition':'raw physical_success AND original carry_eval.success',
        'success_95pct_clopper_pearson':clopper_pearson(successes,n) if integrity else None,
        'statistics_scope':'registered Arm C confirmatory comparison' if args.arm=='arm_c' else 'Arm S diagnostic/descriptive only',
        'C_vs_frozen_r2_exact_McNemar_p':min(1.,2.**(1-successes)) if args.arm=='arm_c' and integrity else None,
        'confirmatory_complete':args.arm=='arm_c' and integrity,
        'normal_complete':normal_complete,'integrity_pass':integrity,'followup_S_admissible_subject_to_budget_disk':followup,
        'pilot':pilot,'pilot_recount_checks':pilot_recount['checks'] if pilot_recount else None,'speed':speed,
        'candidate_funnel':candidate,'frame_funnel':frame_all,
        'frame_scope':'acknowledged normally completed worlds only; other worlds listed as uncompleted/unmeasured',
        'frame_funnel_first5':{name:dict(value) for name,value in frame_counts.items()},
        'frame_definition':'at each stored tick: previous gate ever reached and current gate cumulatively reached, matching original StudentFunnel chronology',
        'later_frame_funnel':'carry/door/place per-frame flags absent in original recorder; episode-level counts measured above; never fill unmeasured with0',
        'event_funnel':dict(metric_totals),'stage_counts':dict(stages),'skill_counts':dict(skills),
        'event_gate_funnel':event_gate_counts,
        'event_gate_scope':'counter reconciliation along proposal path; rejected proposals can still issue a software hold command, so issued_ticks/nonzero_wheel_ticks are separate accounting, not downstream cumulative proposal passes',
        'actual_rejection_reasons':dict(rejects),'barrier_event_counts':dict(events),'input_trace_audit':dict(input_audit),
        'missing_or_uncompleted_worlds':[row['world'] for row in episodes if not row.get('normal_complete')],
        'audit_issues':errors,'episodes':episodes,'gpu_analysis_calls':0,'policy_forward_calls':0,
        'scope':'CPU post-run on original execution VM. Raw/decision/rows untouched. Sampled hold is diagnostic; full image bytes are not independently reverified.'}
    (args.out/'audit.json').write_text(json.dumps(result,indent=2))
    (args.out/'termination-crosscheck.json').write_text(json.dumps({'raw_root':str(args.input),
        'episodes':[{'world':row['world'],'completion_class':row.get('completion_class'),
            'normal_complete':row.get('normal_complete'),'raw_status':row.get('raw_status'),
            'raw_sim_s':row.get('sim_s',row.get('raw_sim_s')),
            'raw_cap_end':(row.get('termination') or {}).get('raw_cap_end',row.get('raw_cap_end')),
            'raw_result_path':str(args.input/f"world-{row['world']:03d}"/'raw/result.json'),
            'raw_physical_success':row.get('raw_physical_success'),'termination':row.get('termination'),
            'reason_category':row['reason_category']} for row in episodes],
        'source_sha256_manifest':str(args.out/'source-sha256.json')},indent=2))
    (args.out/'funnel.json').write_text(json.dumps({'schema':'ugrp.baseline.derived-funnel.v1','raw_root':str(args.input),
        'prior_funnel':str(PACKAGE/'prior-funnel.json'),'planned_N':20,'N_eff':n,'candidate':candidate,
        'frame':frame_all,'frame_scope':result['frame_scope'],'later_frame_scope':result['later_frame_funnel'],
        'event':dict(metric_totals),'event_gate_funnel':event_gate_counts,'event_gate_scope':result['event_gate_scope'],
        'rejections':[{'reason_category':key,'count':value,'blocked_object':'UNKNOWN:not_observed',
            'min_gap_m':None,'gap_scope':'not measured: software gate'} for key,value in rejects.items()],
        'failures':[{'world':row['world'],'reason_category':row['reason_category'],'blocked_object':row['blocked_object'],
            'min_gap_m':row['min_gap_m'],'gap_scope':row['gap_scope']} for row in episodes if row.get('success') is not True],
        'source_manifest':str(args.out/'source-sha256.json'),
        'reproduce':['python3',str(Path(__file__)), '--arm',args.arm,'--input',str(args.input),'--out','NEW_DERIVED_OUTPUT']},indent=2))
    (args.out/'source-sha256.json').write_text(json.dumps(reader.manifest,indent=2))
    print(json.dumps({key:result[key] for key in ['arm','planned_N','N_eff','successes','normal_complete','integrity_pass','followup_S_admissible_subject_to_budget_disk']}),flush=True)


if __name__ == '__main__':
    main()
