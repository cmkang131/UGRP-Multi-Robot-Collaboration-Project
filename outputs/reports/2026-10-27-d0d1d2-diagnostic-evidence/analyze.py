#!/usr/bin/env python3
"""Offline recorded-data diagnostics. Stdlib + zstd; no simulator/model imports.

All geometry constants are taken verbatim from the frozen recount.geometry and
runtime-episode.StudentFunnel. They are descriptive evaluation criteria, not new
control/acceptance thresholds. Nothing starts a VM or opens a GPU device.
"""
import ast
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
from itertools import zip_longest
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys

os.environ['CUDA_VISIBLE_DEVICES'] = ''
sys.dont_write_bytecode = True
ROOT = Path('/home/ubuntu/UGRP')
OUT = Path(__file__).resolve().parent
BASE = Path('/home/ubuntu/ugrp-archive/runs/baseline-resume-20261027T1936Z-tokyo-c')
PRIOR = ROOT / 'outputs/reports/2026-10-27-baseline-resume-evidence'
RECOUNT = ROOT / 'outputs/reports/2026-10-26-round2-recount-evidence/recount.py'
STAGES = ('approach', 'alignment', 'ready', 'execute', 'carry', 'place', 'recover', 'complete')
MANIFEST = {}
CHECKS = Counter()


def write(name, obj):
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def record(path, expected=None):
    path = Path(path)
    if str(path) in MANIFEST:
        return
    h = hashlib.sha256()
    with path.open('rb') as f:
        for buf in iter(lambda: f.read(1024 * 1024), b''):
            h.update(buf)
    entry = dict(bytes=path.stat().st_size, sha256=h.hexdigest())
    if expected is not None:
        assert entry['sha256'] == expected['sha256'], ('source_sha256_mismatch', path)
        assert entry['bytes'] == expected['bytes'], ('source_size_mismatch', path)
        entry['matches_frozen_source_manifest'] = True
        CHECKS['matched_frozen_source_files'] += 1
    MANIFEST[str(path)] = entry


def content(path, expected=None):
    path = Path(path)
    if not path.exists():
        path = Path(str(path) + '.zst')
    record(path, expected)
    return subprocess.check_output(['zstd', '-qdc', str(path)]) if path.suffix == '.zst' else path.read_bytes()


def read(path, expected=None):
    return json.loads(content(path, expected))


def lines(path, expected):
    record(path, expected)
    proc = subprocess.Popen(['zstd', '-qdc', str(path)], stdout=subprocess.PIPE)
    complete = False
    try:
        for line in proc.stdout:
            if line.strip():
                yield json.loads(line)
        complete = True
    finally:
        proc.stdout.close()
        rc = proc.wait()
        if complete:
            assert rc == 0, ('zstd_failed', path, rc)


def quantiles(values):
    """Sorted linear interpolation at (n-1)*q; descriptive, no pass cutoff."""
    s = sorted(values)
    if not s:
        return dict(n=0, min=None, p05=None, p25=None, p50=None, p75=None, p95=None, max=None)
    def q(p):
        i = (len(s) - 1) * p
        lo = math.floor(i)
        hi = math.ceil(i)
        return s[lo] + (s[hi] - s[lo]) * (i - lo)
    return dict(n=len(s), min=s[0], p05=q(.05), p25=q(.25), p50=q(.5), p75=q(.75), p95=q(.95), max=s[-1])


def rate(num, den):
    return dict(n=num, N=den, rate=num / den if den else None)


def extract_geometry():
    # Compile only the original pure geometry() AST. In particular do NOT import
    # recount.py: its module body imports an unavailable frozen evaluator tree.
    record(RECOUNT)
    tree = ast.parse(RECOUNT.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'geometry')
    ns = {'math': math}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(RECOUNT), 'exec'), ns)
    return ns['geometry']


GEOMETRY = extract_geometry()


def components(row, roles):
    out = {}
    for rid, role in roles.items():
        pose = row['robots'][rid]['pose']
        end = row['beam']['ends'][role]
        yaw = row['beam']['pose'][2] + (math.pi if role == 'blue' else 0.)
        goal = (end[0] - .203 * math.cos(yaw), end[1] - .203 * math.sin(yaw))
        d = math.dist(pose[:2], goal)
        theta = abs(math.atan2(math.sin(yaw-pose[2]), math.cos(yaw-pose[2])))
        assert math.isfinite(d) and math.isfinite(theta)
        out[rid] = dict(role=role, d_m=d, yaw_rad=theta,
                        position_margin=d / .03 - 1, yaw_margin=theta / .06 - 1,
                        aligned=d <= .03 and theta <= .06,
                        position_pass=d <= .03, yaw_pass=theta <= .06)
    return out


def geometry_check():
    # Known exact poses, both role directions, inclusive boundaries and yaw wrap.
    # These test numerical meaning only; no new tolerance or success rule.
    roles = {'r1': 'blue', 'r2': 'teal'}
    def fixture(dx=0., dyaw=0., wrap=False):
        row = dict(beam=dict(pose=[0., 0., 0.], ends=dict(blue=[0., 0., 0.], teal=[0., 0., 0.])),
                   robots={}, contacts=dict(r1=[1., 1.], r2=[1., 1.]))
        for rid, role in roles.items():
            yaw = math.pi if role == 'blue' else 0.
            row['robots'][rid] = dict(pose=[-.203 * math.cos(yaw), -.203 * math.sin(yaw),
                                           yaw + (2*math.pi if wrap else 0.)])
        row['robots']['r2']['pose'][1] += dx
        row['robots']['r2']['pose'][2] += dyaw
        return row
    cases = [('exact_goal', fixture(), True),
             ('xy_at_limit', fixture(.03), True),
             ('xy_outside', fixture(math.nextafter(.03, math.inf)), False),
             ('yaw_at_limit', fixture(dyaw=.06), True),
             ('yaw_outside', fixture(dyaw=math.nextafter(.06, math.inf)), False),
             ('yaw_wrap_2pi', fixture(wrap=True), True)]
    for name, row, expected in cases:
        got = GEOMETRY(row, roles)['alignment']
        assert got == expected, (name, got, expected)
        assert got == all(x['aligned'] for x in components(row, roles).values())
    CHECKS['known_pose_cases'] = len(cases)


def spans(rows, predicate):
    out, start = [], None
    for i, row in enumerate(rows):
        yes = predicate(row)
        if yes and start is None:
            start = i
        if start is not None and (not yes or i == len(rows)-1):
            stop = i if yes else i-1
            out.append(dict(first_t=rows[start]['t'], last_t=rows[stop]['t'],
                            samples=stop-start+1, observed_span_s=rows[stop]['t']-rows[start]['t'],
                            sampled_occupancy_s=(stop-start+1)*.1))
            start = None
    return out


def first_t(rows, predicate):
    return next((r['t'] for r in rows if predicate(r)), None)


def best_frame(rows):
    r = min(rows, key=lambda r:r['margin'])
    return {k:r[k] for k in ['t','margin','position_margin','yaw_margin','max_d_m','max_yaw_rad','robots']}


def summarize_margins(rows):
    return {key:quantiles(r[key] for r in rows) for key in
            ['margin','position_margin','yaw_margin','max_d_m','max_yaw_rad']}


def gt_bin(g):
    if g['aligned']:
        return 'xy_and_yaw_pass'
    if g['position_pass']:
        return 'xy_pass_yaw_fail'
    if g['yaw_pass']:
        return 'xy_fail_yaw_pass'
    return 'xy_and_yaw_fail'


def analyze_episode(arm, world, writer, reference):
    raw = BASE / ('arm-' + arm.lower()) / f'world-{world:03d}' / 'raw'
    original = '/home/ugrp/ugrp-sim/runs/baseline-resume-20261027T1936Z/' + f'arm-{arm.lower()}/world-{world:03d}/raw/'
    def expected(name):
        return reference[original + name]
    plan = read(raw/'plan.json', expected('plan.json'))
    result = read(raw/'result.json.zst', expected('result.json.zst'))
    roles = plan['roles']
    assert set(roles) == {'r1','r2'} and set(roles.values()) == {'teal','blue'}
    assert plan['seed'] == 8342000 + world
    assert result['status'] == 'complete'
    rows = []
    c = Counter()
    stage_counts, cond, gt_stages = Counter(), defaultdict(Counter), defaultdict(Counter)
    transitions = defaultdict(Counter)
    previous = {}
    previous_rgb = {}
    rgb_refs = set()
    gen_truth = lines(raw/'eval-only.jsonl.zst', expected('eval-only.jsonl.zst'))
    gen_log = lines(raw/'student-eval.jsonl.zst', expected('student-eval.jsonl.zst'))
    for truth, log in zip_longest(gen_truth, gen_log):
        assert truth is not None and log is not None
        assert truth['t'] == log['t'], ('time_mismatch',arm,world)
        t = truth['t']
        assert not rows or 0 < t-rows[-1]['t'] < .10000001
        parts = components(truth,roles)
        passed = GEOMETRY(truth, roles)
        joint = all(g['aligned'] for g in parts.values())
        assert passed['alignment'] == joint == log['eval_passed']['alignment']
        assert passed['approach'] == log['eval_passed']['approach']
        assert passed['grasp'] == log['eval_passed']['grasp']
        policy_ready = {rid:log['issued'][rid]['stage']=='ready' for rid in roles}
        ready = all(policy_ready.values())
        protocol_ready = all(log['ready'].values())
        assert protocol_ready == log['eval_passed']['READY']
        # Logged protocol-ready can include pending proposals; audit separately.
        c['policy_vs_protocol_ready_robot_mismatches'] += sum(policy_ready[r] != log['ready'][r] for r in roles)
        row = dict(t=t,robots=parts,margin=max(max(g['position_margin'],g['yaw_margin']) for g in parts.values()),
                   position_margin=max(g['position_margin'] for g in parts.values()),
                   yaw_margin=max(g['yaw_margin'] for g in parts.values()),
                   max_d_m=max(g['d_m'] for g in parts.values()),
                   max_yaw_rad=max(g['yaw_rad'] for g in parts.values()),
                   aligned=joint,joint_ready=ready,joint_protocol_ready=protocol_ready,approach=passed['approach'],
                   policy_ready=policy_ready,stages={r:log['issued'][r]['stage'] for r in roles})
        rows.append(row)
        c['frames'] += 1
        c['approach_frames'] += passed['approach']
        c['alignment_frames'] += joint
        c['joint_ready_frames'] += ready
        c['joint_protocol_ready_frames'] += protocol_ready
        c['joint_policy_vs_protocol_ready_mismatch_frames'] += ready != protocol_ready
        c['aligned_and_protocol_ready_frames'] += joint and protocol_ready
        c['aligned_and_ready_frames'] += joint and ready
        c['geometry_yes_ready_no'] += joint and not ready
        c['geometry_no_ready_yes'] += not joint and ready
        c['geometry_no_ready_no'] += not joint and not ready
        c['position_only_fail_frames'] += row['position_margin'] > 0 and row['yaw_margin'] <= 0
        c['yaw_only_fail_frames'] += row['position_margin'] <= 0 and row['yaw_margin'] > 0
        c['both_component_fail_frames'] += row['position_margin'] > 0 and row['yaw_margin'] > 0
        c['position_dominant_frames'] += row['position_margin'] > row['yaw_margin']
        c['yaw_dominant_frames'] += row['yaw_margin'] > row['position_margin']
        c['equal_component_frames'] += row['yaw_margin'] == row['position_margin']
        for rid, role in roles.items():
            issued, obs, g = log['issued'][rid], log['inputs'][rid], parts[rid]
            stage = issued['stage']
            assert stage in STAGES
            assert obs['t'] == t and obs['robot_id'] == rid and obs['role'] == role
            assert len(obs['issued']) == 16 and len(obs['rgb']) == 4
            previous_stage = previous[rid]['stage'] if rid in previous else 'episode_start'
            if rid in previous:
                assert obs['issued'][-1] == previous[rid]['command'], ('history_mismatch',arm,world,rid,t)
                transitions[previous[rid]['stage']][stage] += 1
            previous[rid] = issued
            rdy = policy_ready[rid]
            c['robot_ticks'] += 1
            c['ready_robot_ticks'] += rdy
            c['local_aligned_robot_ticks'] += g['aligned']
            c['local_geo_and_ready_robot_ticks'] += g['aligned'] and rdy
            c['premature_ready_local_geometry_n'] += rdy and not g['aligned']
            c['pre_local_geometry_robot_ticks'] += not g['aligned']
            c['ready_while_joint_geometry_n'] += rdy and joint
            c['robot_ticks_while_joint_geometry'] += joint
            c['nonzero_wheel_robot_ticks'] += any(v != 0 for v in issued['command']['wheels'])
            c['software_hold_robot_ticks'] += issued['software_hold']
            c['permit_robot_ticks'] += issued['permit']
            stage_counts[stage] += 1
            gt_stages[gt_bin(g)][stage] += 1
            last = obs['issued'][-1]
            previous_wheels = any(v != 0 for v in last['wheels'])
            history_wheels = any(v != 0 for cmd in obs['issued'] for v in cmd['wheels'])
            pwm_delta = {k:last['pwm'][k]-obs['issued'][-2]['pwm'][k] for k in last['pwm']}
            newest_rgb = obs['rgb'][-1]
            repeated_rgb = (newest_rgb['sha256'] == previous_rgb[rid]) if rid in previous_rgb else None
            previous_rgb[rid] = newest_rgb['sha256']
            input_conditions = [f'robot={rid}',f'role={role}',f'local_geometry={g["aligned"]}',
                f'joint_geometry={joint}',f'previous_policy={previous_stage}',
                f'last_issued_wheels_nonzero={previous_wheels}',f'history16_wheels_nonzero={history_wheels}',
                f'newest_own_rgb_sha_repeated={repeated_rgb}',
                f'eval_only_assigned_end_visible={truth["visibility"][rid]["visible"]}',
                f'last_gripper_delta={"negative" if pwm_delta["1"] < 0 else "positive" if pwm_delta["1"] > 0 else "zero"}',
                f'skill={obs["skill"]}',f'destination={obs["destination_zone"]}']
            for key in filter(None,input_conditions):
                cond[key]['N'] += 1
                cond[key]['READY'] += rdy
                cond[key][stage] += 1
            for ref in obs['rgb']:
                assert ref['robot_id'] == rid
                rgb_refs.add((rid,ref['path'],ref['sha256'],ref['t']))
            row['robots'][rid].update(stage=stage,policy_ready=rdy,protocol_ready=log['ready'][rid],
                wheel_nonzero=any(v != 0 for v in issued['command']['wheels']),
                software_hold=issued['software_hold'],permit=issued['permit'],
                previous_wheels_nonzero=previous_wheels,gripper_delta=pwm_delta['1'])
        writer.writerow([arm,world,plan['seed'],t,row['margin'],row['position_margin'],row['yaw_margin'],
            row['aligned'],row['joint_ready']]+[row['robots'][r][k] for r in ['r1','r2'] for k in
            ['d_m','yaw_rad','aligned','stage','policy_ready','protocol_ready','wheel_nonzero','software_hold','permit']])
    assert c['robot_ticks'] == sum(stage_counts.values())
    stored_metrics = result['student_eval']['treatment']['metrics']
    assert c['robot_ticks'] == sum(m['ticks'] for m in stored_metrics.values())
    stored_stage = Counter()
    for m in stored_metrics.values(): stored_stage.update(m['stage_counts'])
    assert stored_stage == stage_counts
    for key, stored in [('software_hold_robot_ticks','software_hold_ticks'),('nonzero_wheel_robot_ticks','nonzero_wheel_ticks')]:
        assert c[key] == sum(m[stored] for m in stored_metrics.values())
    CHECKS['exact_time_joined_frames'] += len(rows)
    CHECKS['geometry_vs_stored_frame_checks'] += 4 * len(rows)
    CHECKS['episode_stage_command_counts_match'] += 1
    geometry_spans = spans(rows,lambda r:r['aligned'])
    ready_spans = spans(rows,lambda r:r['joint_ready'])
    robot_summary = {}
    for rid in roles:
        gf = first_t(rows,lambda x:x['robots'][rid]['aligned'])
        rf = first_t(rows,lambda x:x['policy_ready'][rid])
        rr = [r for r in rows if r['policy_ready'][rid]]
        robot_summary[rid] = dict(role=roles[rid],first_geometry_t=gf,first_ready_t=rf,
            ready_minus_geometry_s=None if gf is None or rf is None else rf-gf,
            aligned_frames=sum(r['robots'][rid]['aligned'] for r in rows),
            ready_frames=len(rr),ready_local_geometry_frames=sum(r['robots'][rid]['aligned'] for r in rr),
            ready_before_first_geometry_frames=None if gf is None else sum(r['t']<gf for r in rr),
            ready_when_geometry_never_reached=len(rr) if gf is None else 0,
            geometry_spans=spans(rows,lambda r:r['robots'][rid]['aligned']),
            ready_spans=spans(rows,lambda r:r['policy_ready'][rid]),
            geometry_window_stage_counts=dict(Counter(r['stages'][rid] for r in rows if r['aligned'])),
            best_individual_margin=min(max(r['robots'][rid]['position_margin'],r['robots'][rid]['yaw_margin']) for r in rows))
    events = result['student_eval']['protocol_events']
    stage_events = result['student_eval'].get('barrier_events',{})
    event_counts = Counter(e['event'] for e in events)
    rejects = Counter(e.get('reason_category') or 'INVALID_EMPTY_REASON' for ev in stage_events.values() for e in ev if e.get('event')=='proposal_rejected')
    assert 'INVALID_EMPTY_REASON' not in rejects
    protocol_ready_events = []
    # Original protocol READY events are in sync events for some versions and
    # in barrier events for others; preserve both without conflating them.
    for origin, ev in [('protocol',events)] + [(rid,v) for rid,v in stage_events.items()]:
        for e in ev:
            if e['event'] in ['READY','GO','ACK','START']:
                match = next((r for r in rows if r['t']==e['t']),None)
                protocol_ready_events.append(dict(origin=origin,event=e,
                    same_time_geometry=match['aligned'] if match else None,
                    exact_time_matched=match is not None))
    independent_each_aligned = all(robot_summary[r]['aligned_frames']>0 for r in roles)
    best = best_frame(rows)
    ep = dict(arm=arm,world=world,seed=plan['seed'],original_raw_dir=original,local_raw_dir=str(raw),
        status=result['status'],physical_success=result['physical_success'],cap_end=result['cap_end'],
        raw_end_reason=result['end_reason'],
        termination=('cap_end' if result['cap_end'] else 'learned_finished_early'
                     if result['student_eval']['finished_t'] is not None else result['end_reason']),
        sim_s=result['sim_s'],
        first_t=rows[0]['t'],last_t=rows[-1]['t'],counts=dict(c),stage_counts=dict(stage_counts),
        min_joint_margin_frame=best,all_frame_distribution=summarize_margins(rows),
        min_position_margin_frame={k:min(rows,key=lambda r:r['position_margin'])[k] for k in ['t','position_margin','yaw_margin','robots']},
        min_yaw_margin_frame={k:min(rows,key=lambda r:r['yaw_margin'])[k] for k in ['t','position_margin','yaw_margin','robots']},
        min_margin_within_approach=best_frame([r for r in rows if r['approach']]) if c['approach_frames'] else None,
        first_joint_geometry_t=first_t(rows,lambda r:r['aligned']),first_joint_ready_t=first_t(rows,lambda r:r['joint_ready']),
        joint_geometry_spans=geometry_spans,joint_ready_spans=ready_spans,robots=robot_summary,
        each_robot_aligned_at_some_time=independent_each_aligned,
        individual_alignment_without_joint=independent_each_aligned and c['alignment_frames']==0,
        ready_conditions={k:dict(v) for k,v in cond.items()},geometry_by_policy_stage={k:dict(v) for k,v in gt_stages.items()},
        stage_transition_counts={k:dict(v) for k,v in transitions.items()},protocol_event_counts=dict(event_counts),
        proposal_rejection_categories=dict(rejects),protocol_events_geometry=protocol_ready_events,
        rgb_reference_unique_count=len(rgb_refs),
        unavailable=dict(true_stage_targets='not recorded on student visited states',
                         stage_logits='not recorded',ready_probabilities='not recorded',
                         registered_premature_ready=None,teacher_forced_transition_confusion=None))
    print(json.dumps(dict(arm=arm,world=world,frames=len(rows),min_margin=best['margin'],
                         alignment_frames=c['alignment_frames'],ready_frames=c['joint_ready_frames'])),flush=True)
    return ep,rows


def aggregate(arm, eps, frames):
    totals = Counter()
    labels = Counter()
    cond, trans, gt = defaultdict(Counter),defaultdict(Counter),defaultdict(Counter)
    ev,reject = Counter(),Counter()
    for ep in eps:
        totals.update(ep['counts']);labels.update(ep['stage_counts'])
        ev.update(ep['protocol_event_counts']);reject.update(ep['proposal_rejection_categories'])
        for source,target in [(ep['ready_conditions'],cond),(ep['stage_transition_counts'],trans),(ep['geometry_by_policy_stage'],gt)]:
            for k,v in source.items():target[k].update(v)
    bests = [e['min_joint_margin_frame'] for e in eps]
    return dict(arm=arm,N=len(eps),frames=totals['frames'],counts=dict(totals),stage_counts=dict(labels),
        geometry_episodes=sum(e['counts']['alignment_frames']>0 for e in eps),
        joint_ready_episodes=sum(e['counts']['joint_ready_frames']>0 for e in eps),
        aligned_and_ready_episodes=sum(e['counts']['aligned_and_ready_frames']>0 for e in eps),
        individual_aligned_robot_episodes=sum(v['aligned_frames']>0 for e in eps for v in e['robots'].values()),
        individual_ready_robot_episodes=sum(v['ready_frames']>0 for e in eps for v in e['robots'].values()),
        either_robot_ready_episodes=sum(any(v['ready_frames']>0 for v in e['robots'].values()) for e in eps),
        each_robot_aligned_at_some_time_episodes=sum(e['each_robot_aligned_at_some_time'] for e in eps),
        individual_alignment_without_joint_episodes=sum(e['individual_alignment_without_joint'] for e in eps),
        local_geometry_premature_ready_proxy=rate(totals['premature_ready_local_geometry_n'],totals['pre_local_geometry_robot_ticks']),
        ready_false_discovery_local_geometry=rate(totals['premature_ready_local_geometry_n'],totals['ready_robot_ticks']),
        registered_premature_ready=None,registered_transition_recall=None,
        all_frame_distributions=summarize_margins(frames),
        episode_minimum_margin_distribution=quantiles(e['margin'] for e in bests),
        episode_independent_minimum_position_distribution=quantiles(e['min_position_margin_frame']['position_margin'] for e in eps),
        episode_independent_minimum_yaw_distribution=quantiles(e['min_yaw_margin_frame']['yaw_margin'] for e in eps),
        at_joint_minimum_frame_distributions={key:quantiles(e[key] for e in bests) for key in ['position_margin','yaw_margin','max_d_m','max_yaw_rad']},
        joint_minimum_frame_limiting_component=dict(Counter('position' if b['position_margin']>b['yaw_margin'] else 'yaw' if b['yaw_margin']>b['position_margin'] else 'equal' for b in bests)),
        ready_conditions={k:dict(v,ready_rate=v['READY']/v['N']) for k,v in cond.items()},
        stage_transition_counts={k:dict(v) for k,v in trans.items()},
        stage_changed_transition_counts={k:{j:n for j,n in v.items() if j!=k} for k,v in trans.items()},
        geometry_by_policy_stage={k:dict(v) for k,v in gt.items()},protocol_event_counts=dict(ev),
        proposal_rejection_categories=dict(reject),
        episode_geometric_failure_partition=dict(
            neither_robot_ever_aligned=sum(all(v['aligned_frames']==0 for v in e['robots'].values()) for e in eps),
            only_one_robot_ever_aligned=sum(sum(v['aligned_frames']>0 for v in e['robots'].values())==1 for e in eps),
            both_ever_but_not_joint=sum(e['individual_alignment_without_joint'] for e in eps),
            joint_aligned_without_joint_ready=sum(e['counts']['alignment_frames']>0 and e['counts']['aligned_and_ready_frames']==0 for e in eps)))


def d0():
    candidates = [Path('/home/ugrp/ugrp-sim/runs/pairact-p5-eval-20261025/p5-teacher'),
                  Path('/home/ubuntu/ugrp-sim/runs/pairact-p5-eval-20261025/p5-teacher'),
                  Path('/home/ubuntu/ugrp-archive/runs/pairact-p5-eval-20261025/p5-teacher')]
    found = [p for p in candidates if p.is_dir()]
    # Do not substitute another teacher cohort, trajectory or summary for P5 truth.
    assert not found, ('teacher_available_implement_d0',found)
    prior = read(ROOT/'outputs/reports/2026-10-26-round2-recount-evidence/result-v2/recount.json')
    teacher = prior['aggregates']['teacher']
    obj = dict(status='UNAVAILABLE_ORIGINAL_TRAJECTORY',recomputed_alignment_pass_worlds=None,
        recomputed_alignment_margin_distribution=None,original_alignment_metric='UNRECORDED',
        checked_paths=[dict(path=str(p),exists=p.exists()) for p in candidates],
        accessible_student_archive=str(BASE),
        search_scope='local archive/runs, ugrp-sim, ugrp-audit, UGRP/outputs, ugrp-recovery with rg --files --hidden --no-ignore; no P5 eval-only trajectory found',
        search_limitations='unrelated old incoming archives had permission-denied paths; no stopped cloud disk mount/start/copy attempted',
        stop_point='Before applying geometry(): no accessible original P5 eval-only + plan pair; VM start forbidden',
        historical_teacher_recount_reference_only=teacher,
        historical_reference_scope='Prior recount JSON read for provenance only; no new teacher metric computed; success != alignment',
        no_zero_imputation=True)
    write('d0.json',obj)
    return obj


def main():
    geometry_check()
    start=datetime.now(timezone.utc).isoformat()
    d0_result=d0()
    refs={a:read(PRIOR/f'{a}-source-sha256-v1.json') for a in ['C','S']}
    eps=[]
    summaries={}
    with gzip.open(OUT/'frame-metrics.csv.gz','wt',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['arm','world','seed','t','m','m_position','m_yaw','joint_geometry','joint_policy_ready']+
            [r+'_'+k for r in ['r1','r2'] for k in ['d_m','yaw_rad','aligned','stage','policy_ready','protocol_ready','wheel_nonzero','software_hold','permit']])
        for arm in ['C','S']:
            group=[];frames=[]
            for world in range(20):
                ep,rr=analyze_episode(arm,world,writer,refs[arm]);group.append(ep);frames.extend(rr)
            eps.extend(group)
            summaries[arm]=aggregate(arm,group,frames)
            # Check prior aggregate funnel only AFTER independent recomputation.
            old=read(PRIOR/f'{arm}-funnel-v1.json')
            assert summaries[arm]['geometry_episodes']==old['candidate'][1]['passed_cumulative_N']
            assert summaries[arm]['counts']['alignment_frames']==old['frame']['alignment']['passed_cumulative']
    write('episodes.json',eps)
    write('summary.json',dict(schema='ugrp.d0d1d2.cpu_diagnostic.v1',started_utc=start,
        completed_utc=datetime.now(timezone.utc).isoformat(),D0=d0_result,arms=summaries,
        checks=dict(CHECKS),scope=dict(gpu_usage=0,vm_starts=0,new_arms=0,training_runs=0,
        threshold_changes=0,physics_steps=0,model_forwards=0,original_files_modified=0,
        analysis_host=platform.node(),platform=platform.platform(),python=sys.version,
        simulation_backend_of_originals='MJWarp; archive CPU arithmetic is not a CPU simulation cohort'),
        method=dict(geometry_source=str(RECOUNT),margin='max over both robots of d/0.03 and abs(wrapped yaw)/0.06 minus 1',
                    join='exact recorded floating point t; never nearest frame',
                    quantiles='linear interpolation at (n-1)*q',
                    stage_confusion_scope='observed previous->current stage counts and geometry-bin vs policy-stage; no true stage targets recorded',
                    premature_ready_proxy='P(policy stage ready | own geometry false); existing frozen geometry only; not original target-based premature_ready',
                    RGB_conditioning_scope='raw RGB reference identities retained in original inputs; no semantic visual classifier or policy probability inference')))
    record(Path(__file__))
    write('source-manifest.json',MANIFEST)
    print(json.dumps(dict(checks=dict(CHECKS),arms={a:dict(N=s['N'],frames=s['frames'],geometry_episodes=s['geometry_episodes'],
       margin_min=s['episode_minimum_margin_distribution'],partition=s['episode_geometric_failure_partition']) for a,s in summaries.items()}),indent=2))


if __name__=='__main__':
    main()
