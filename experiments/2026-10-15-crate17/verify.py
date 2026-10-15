"""Saved-input counterfactuals and issued-odometry feedback. No dynamics/render/remote."""
import argparse
import hashlib
import json
import math
import random
import subprocess
import sys
import time
from collections import Counter
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE.parent/'2026-10-15-crate15'))
import replay as saved_replay
from replay import replay, js, rows, read, RAW, forbidden
# The historical replay helper memoizes IK/lift. Remove those wrappers for this
# measurement: ordinary runner calls (prepare + step), no hidden offline cache.
for module in list(sys.modules.values()):
    for attr, cached, original in (('solve_grip_site_ik', saved_replay.cached_ik, saved_replay._original_ik),
                                    ('plan_lift', saved_replay.cached_lift, saved_replay._original_lift)):
        if getattr(module, attr, None) is cached:
            setattr(module, attr, original)
import mujoco
for name in ('mj_step', 'mj_step1', 'mj_step2', 'mj_forward', 'mj_inverse', 'Renderer', 'mjr_render'):
    setattr(mujoco, name, forbidden)
from harness.grasp_act_visible_world import command_delta
from sim.crate_grasp_teacher import CrateGraspTeacher
from sim.crate_motion_v17 import MODE, NO_CLEARANCE, Navigation, advance
from sim.cargo_teacher_profile import CRATE
from scripts.run_crate_teacher import make_grasp_teacher

RUNS = [f'crate16-reproduction-{s}-221755a5' for s in (77990, 79314)]
OLD_RUNS = ('crate-reproduction-77990-8007db00', 'crate-reproduction-79314-8007db00',
            'crate-reproduction-79317-8007db00', 'crate-diag-79450-8007db00', 'crate-diag-79451-8007db00')


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def distribution(v):
    v = sorted(v)
    return {'n': len(v), 'min': v[0] if v else None, 'p50': v[len(v)//2] if v else None,
            'p95': v[min(len(v)-1, int(len(v)*.95))] if v else None, 'max': v[-1] if v else None}


def teacher(case, mode=MODE):
    t = make_grasp_teacher(case['robot'], case['end'], {int(k): v for k, v in case['proposal']['pwm'].items()},
        teacher_stability='align_relook_v1', teacher_search='search_reacquire_v1',
        approach_goal_set='approach_goal_set_v1', crate_lift_pose='crate_antipodal_grasp_v1',
        crate_approach_recovery='crate_approach_recovery_v1', crate_wall_footprint='crate_footprint_v1',
        crate_stances='crate_stances_v1', crate_pulse_safety='crate_no_closer_v1',
        crate_candidate_recovery='crate_candidates_v1', crate_alignment='crate_alignment_v14', crate_motion=mode)
    t.phase = case['phase']; t.folded_ready = case['folded_ready']
    t.path = deepcopy(case['path']); t.path_goal = tuple(case['path_goal']) if case['path_goal'] else None
    t.approach_choice = tuple(case['choice']); t.approach_plan_valid = True
    t.next_plan = case['world']['t']+1.
    return t


def closed_loop(case, mode=MODE, ticks=12):
    w = deepcopy(case['world']); t = teacher(case, mode); trace = []
    start = tuple(w['robots'][t.rid]['pose'])
    for i in range(ticks):
        now = case['world']['t']+i*.1; w['t'] = now
        # No invented reobservations: keep the saved dynamic geometry only as
        # memory for this 1.2s loop, below the unchanged 5.2s horizon.
        if i:
            w['visibility'][t.rid].update(visible_probes=0, objects=[], peers=[])
        pose, _, heading, goal = t._geometry(w)
        proposed = t._route(w, goal, heading, now)
        actual = t._check_navigation_pulse(w, proposed, now)
        nav = t._navigation(w)
        assert nav.pulse_safe(actual)
        delta = command_delta(actual, .1)
        w['robots'][t.rid]['pose'] = list(advance(pose, actual))
        trace.append({'t': now, 'delta': delta, 'wheels': actual['wheels'], 'duration_s': actual['duration_s'],
                      'escape': t.crate_recovery_log[-1] if t.crate_recovery_log else None})
    return {'run': case['run'], 'robot': t.rid, 'start_t': case['world']['t'], 'mode': mode,
            'translation_ticks': sum(math.hypot(*r['delta'][:2]) >= .0005 for r in trace),
            'net_xy_mm': math.dist(start[:2], w['robots'][t.rid]['pose'][:2])*1000, 'trace': trace}


def capture():
    cases = []; rejected = []; origins = {}
    original = CrateGraspTeacher._check_navigation_pulse
    for run in RUNS:
        raw = RAW/run/'raw'
        for filename in ('result.json', 'eval-only.jsonl', 'teacher-r1.jsonl', 'teacher-r2.jsonl'):
            p = raw/filename
            if not p.exists(): p = Path(str(p)+'.zst')
            origins[str(p)] = digest(p)
        def check(self, w, value, now):
            nav = self._navigation(w)
            reject = (self.phase in ('approach', 'align', 'ready', 'search', 'relook')
                      and any(value['wheels']) and not nav.pulse_safe(value))
            if reject:
                case = {'run': run, 'robot': self.rid, 'end': self.end, 'world': deepcopy(dict(w)),
                        'phase': self.phase, 'folded_ready': self.folded_ready, 'proposal': deepcopy(value),
                        'path': deepcopy(self.path), 'path_goal': self.path_goal, 'choice': self.approach_choice}
                rejected.append(case)
                if self.rid == 'r2' and 13.9-1e-8 <= now <= 15.+1e-8:
                    cases.append(case)
            return original(self, w, value, now)
        CrateGraspTeacher._check_navigation_pulse = check
        try:
            r = replay(run, options={'crate_motion': 'crate_motion_v16'})
        finally:
            CrateGraspTeacher._check_navigation_pulse = original
        assert r['matched'] == r['total'], (run, r['matched'], r['total'], r['mismatch'])
        print(json.dumps({'capture': run, 'matched': r['matched'], 'total': r['total']}), flush=True)
    return cases, rejected, origins


def write_zst(p, value):
    data = json.dumps(value, separators=(',', ':')).encode()
    compressed = subprocess.check_output(['zstd', '-q', '-c'], input=data)
    assert subprocess.check_output(['zstd', '-q', '-d', '-c'], input=compressed) == data
    p.write_bytes(compressed)


def timed_replay(run, mode):
    durations = {}; prepared = {}; ticks = []
    original = CrateGraspTeacher.prepare_signal
    def prepare(self, w, now):
        at = time.perf_counter(); result = original(self, w, now)
        prepared[(self.rid,now)] = time.perf_counter()-at
        return result
    def hook(stage, i, now, rid, t, *rest):
        if stage == 'pre':
            durations[(rid,i)] = time.perf_counter()
        else:
            step = time.perf_counter()-durations[(rid,i)]
            ticks.append({'run':run,'mode':mode,'robot':rid,'t':now,
                'teacher_prepare_s':prepared[(rid,now)],'teacher_step_s':step,
                'teacher_compute_s':prepared[(rid,now)]+step,'navigation_stats':t.navigation_stats()})
    CrateGraspTeacher.prepare_signal = prepare
    try:
        r = replay(run, hook=hook, options={'crate_motion':mode})
    finally:
        CrateGraspTeacher.prepare_signal = original
    assert r['audit']['held_world_reads'] == 0 and r['audit']['invisible_measurements'] == 0
    return ticks, r['audit']


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--capture-fixtures', action='store_true'); a = ap.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    cases, rejected, origins = capture()
    if a.capture_fixtures:
        write_zst(HERE/'closed-loop-fixtures.json.zst', {'source_sha256': origins, 'cases': cases})
    baseline = []
    for name in OLD_RUNS:
        raw = RAW/name/'raw'
        for filename in ('result.json', 'eval-only.jsonl', 'teacher-r1.jsonl', 'teacher-r2.jsonl'):
            p = raw/filename
            if not p.exists(): p = Path(str(p)+'.zst')
            origins[str(p)] = digest(p)
        r = replay(name, options={'crate_motion': 'off'}); r.pop('teachers')
        assert r['matched'] == r['total']
        baseline.append(r)
        print(json.dumps({'off': name, 'matched': r['matched'], 'total': r['total']}), flush=True)
    assert sum(r['total'] for r in baseline) == 1424
    comparisons = []
    for mode in (MODE, NO_CLEARANCE):
        for case in rejected:
            t = teacher(case, mode); now = case['world']['t']; before = time.perf_counter()
            value = t._check_navigation_pulse(case['world'], case['proposal'], now)
            elapsed = time.perf_counter()-before
            delta = command_delta(value, .1)
            assert t._navigation(case['world']).pulse_safe(value)
            comparisons.append({'run': case['run'], 'robot': t.rid, 't': now, 'mode': mode,
                'kind': t.crate_recovery_log[-1].get('kind', 'hold') if t.crate_recovery_log else 'unchanged',
                'predicted_xy_mm': math.hypot(*delta[:2])*1000, 'predicted_yaw_deg': math.degrees(delta[2]),
                'wheels': value['wheels'], 'duration_s': value['duration_s'], 'check_s': elapsed})
    loops = [closed_loop(c, mode) for mode in (MODE, NO_CLEARANCE) for c in cases]
    assert loops and all(r['translation_ticks'] > 0 for r in loops)
    write_zst(a.output/'rejected-ticks.json.zst', comparisons)
    write_zst(a.output/'closed-loop.json.zst', loops)
    timed = []; audits = []
    for mode in ('crate_motion_v16', MODE, NO_CLEARANCE):
        for run in RUNS:
            tick_rows, audit = timed_replay(run, mode)
            timed.extend(tick_rows); audits.append({'run':run,'mode':mode,'audit':audit})
            print(json.dumps({'timed':run,'mode':mode,
                'compute_s':distribution([r['teacher_compute_s'] for r in tick_rows])}), flush=True)
    write_zst(a.output/'teacher-ticks.json.zst', timed)
    grouped = []
    for mode in (MODE, NO_CLEARANCE):
        for run in RUNS:
            for rid in ('r1', 'r2'):
                rs = [r for r in comparisons if r['mode'] == mode and r['run'] == run and r['robot'] == rid]
                if rs:
                    grouped.append({'mode': mode, 'run': run, 'robot': rid, 'rejected_ticks': len(rs),
                        'translation_ticks': sum(r['predicted_xy_mm'] >= .5 for r in rs),
                        'kind': dict(Counter(r['kind'] for r in rs)),
                        'predicted_xy_mm': distribution([r['predicted_xy_mm'] for r in rs])})
    actual = [r['teacher_compute_s'] for run in RUNS for rid in ('r1', 'r2')
              for r in rows(RAW/run/'raw'/f'teacher-{rid}.jsonl')]
    summary = {'scope': 'stored visible inputs; counterfactual pulses and issued-odometry feedback only; physical success unverified',
        'baseline_matched': sum(r['matched'] for r in baseline), 'baseline_total': 1424,
        'baseline': baseline, 'rejected_ticks': grouped,
        'closed_loop': {'cases': len(cases), 'candidate_cases': len(loops),
            'all_issue_translation': all(r['translation_ticks'] > 0 for r in loops),
            'net_xy_mm': distribution([r['net_xy_mm'] for r in loops])},
        'original_gcp_teacher_compute_s': distribution(actual), 'source_sha256': origins,
        'local_runner_calls_no_ik_cache_s': {mode: distribution([r['teacher_compute_s'] for r in timed if r['mode']==mode])
                                           for mode in ('crate_motion_v16', MODE, NO_CLEARANCE)},
        'input_audits': audits,
        'timing_limit': 'local saved-input runner calls, no MuJoCo; GCP candidate wall time remains unmeasured',
        'detail_sha256': {str(p): digest(p) for p in a.output.glob('*.zst')},
        'physical_runs': 0, 'render_calls': 0, 'remote_connections': 0, 'model_calls': 0}
    (a.output/'verification.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
