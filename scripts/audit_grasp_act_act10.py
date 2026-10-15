"""Offline ACT9 ledger replay; truth is read only by bearing-error evaluation.

Replayed commands/visibility are fixed ACT9 evidence. Counterfactual search
commands do not predict new visibility or establish physical recovery.
"""
import argparse
from copy import deepcopy
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
from types import SimpleNamespace

import numpy as np

from harness.grasp_act_data import read_json, read_rows, sha256, write_json
from harness.grasp_act_dart import recovery_hooks
from harness.grasp_act_perturb import RecoveryPerturb, PERTURB_MODE, recovery_statistics
from harness.grasp_act_search import CommandSearch
from scripts.grasp_act_training_guard import ROOT
from scripts.run_grasp_act_recovery import dependency_modules


def angle_error(point, base, cargo):
    """Evaluator only. The estimate has already been computed without truth."""
    expected = math.atan2(point[1], point[0])
    actual = math.atan2(cargo[1]-base['base_xyz'][1], cargo[0]-base['base_xyz'][0])-base['base_rpy'][2]
    return abs(math.degrees(math.atan2(math.sin(expected-actual), math.cos(expected-actual))))


def adapter_replay(rows, hooks, model, seed):
    """Replay the adapter with saved clean teacher decisions, no new policy."""
    class Teacher:
        def __init__(self):
            self.phase = rows[0]['phase_before']; self.holding = False
            self.target = self.seen_t = self.stable_t = self.previous = None
            self.sink = SimpleNamespace(pwm={}); self.arm = SimpleNamespace(commanded={})
        def _reset_alignment(self):pass
        def remember_applied(self, value):self.previous = deepcopy(value)
        def step(self, now, **kwargs):
            self.phase = current['phase_after']
            return deepcopy(current['clean_teacher_command']), False
    tm = SimpleNamespace(SoloTeacher=Teacher); rm = SimpleNamespace(SoloRecorder=object)
    stream = io.StringIO(); generated = []
    with hooks(tm, rm, RecoveryPerturb(model, seed=seed), stream):
        teacher = tm.SoloTeacher()
        for current in rows:
            teacher.phase = current['phase_before']
            teacher.holding = current['phase_before'] not in ('start','fold','approach','align','relook')
            value, _ = teacher.step(current['t'], measurement={} if current['target_visible'] else None)
            generated.append(value)
    return generated, stream.getvalue()


def replay(runs_root, evidence_root, dependency_root, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    # The old adapter is loaded as pure source, never its simulation runner.
    old_source = subprocess.check_output(['git','show','ec0bd628:harness/grasp_act_dart.py'],cwd=ROOT,text=True)
    namespace = {}; exec(compile(old_source,'ec0bd628:grasp_act_dart','exec'), namespace)
    old_hooks = namespace['recovery_hooks']
    model = read_json(ROOT/'experiments/2026-10-15-act-train/act9-noise.json')
    with dependency_modules(dependency_root):
        from sim.grasp_act_visible_gaze import gaze_pose
        from sim.grasp_act_gaze import slew, camera_extrinsics
    runs = []
    for seed in (8316900,8316901,8316902):
        name = f'act9-gate-{seed}-ec0bd628'; root = Path(runs_root)/name
        paths = {k:root/v for k,v in {'result':'raw/result.json','commands':'recovery-commands.jsonl.zst',
            'teacher':'raw/teacher-commands.jsonl.zst','base_evaluation':'recovery-eval-only.jsonl.zst',
            'cargo_evaluation':'raw/eval-only.jsonl.zst'}.items()}
        paths = {k:(p if p.exists() else Path(str(p)+'.zst')) for k,p in paths.items()}
        result = read_json(paths['result']); rows = read_rows(paths['commands'])
        decoded = subprocess.check_output(['zstd','-dc',str(paths['commands'])])
        if hashlib.sha256(decoded).hexdigest() != result['recovery']['sha256']:
            raise ValueError('command decoded hash mismatch')
        decoded_eval = subprocess.check_output(['zstd','-dc',str(paths['base_evaluation'])])
        if hashlib.sha256(decoded_eval).hexdigest() != result['recovery']['evaluation_only']['sha256']:
            raise ValueError('evaluation decoded hash mismatch')
        teachers = read_rows(paths['teacher']); bases = read_rows(paths['base_evaluation'])
        cargos = [r for r in read_rows(paths['cargo_evaluation']) if 'cargo_xyz' in r]
        if len({len(rows),len(teachers),len(bases),len(cargos)}) != 1:
            raise ValueError('ledger length mismatch')
        retrieval = Path(evidence_root)/(name+'-retrieval.json')
        collection = read_json(Path(evidence_root)/(name+'-analysis.json'))
        if sha256(paths['result']) != collection['result_sha256']:
            raise ValueError('retrieved result hash mismatch')
        legacy, legacy_text = adapter_replay(rows, old_hooks, model, seed)
        current, current_text = adapter_replay(rows, recovery_hooks, model, seed)
        if legacy != current or legacy_text != current_text or current != [r['applied_command'] for r in rows]:
            raise ValueError('search-disabled legacy adapter changed')
        search = CommandSearch(); previous = None; predictions = []
        for row, teacher in zip(rows, teachers):
            if row['t'] != teacher['t']:raise ValueError('teacher clock mismatch')
            eligible = row['phase_before'] in ('start','fold','approach','align','relook')
            search.observe(row['t'], teacher['visible_target'], previous, holding=not eligible, eligible=eligible)
            # Do not give the controller any evaluator object or coordinate.
            predictions.append({'t':row['t'], 'visible':row['target_visible'], 'xyz':deepcopy(search.point)})
            previous = row['applied_command']
        errors = []
        for pred, row, base, cargo in zip(predictions, rows, bases, cargos):
            if not pred['t'] == row['t'] == base['t'] == cargo['t']:raise ValueError('evaluation clock mismatch')
            if pred['xyz'] is not None and not pred['visible']:
                errors.append({**pred,'error_deg':angle_error(pred['xyz'],base,cargo['cargo_xyz'])})
        audit = recovery_statistics(rows)
        entry = {'seed':seed, 'physical_success':result['physical_success'], 'command_ticks':len(rows),
            'input_audit':result['input_audit'], 'recovery_audit':audit,
            'search_disabled_commands_equal':True, 'search_disabled_ledger_equal':True,
            'off_comparison_scope':'ec0bd628 vs current adapter; saved clean teacher decisions/visibility, not a world rerun',
            'raw':{k:{'path':str(p), 'sha256':sha256(p)} for k,p in paths.items()},
            'retrieval':{'path':str(retrieval),'sha256':sha256(retrieval)},
            'hidden_bearing':{'N':len(errors), **({
                'median_deg':float(np.median([e['error_deg'] for e in errors])),
                'p95_deg':float(np.percentile([e['error_deg'] for e in errors],95)),
                'max_deg':max(e['error_deg'] for e in errors), 'first':errors[0], 'last':errors[-1]} if errors else {})}}
        if seed == 8316902:
            last = max(i for i,r in enumerate(rows) if r['target_visible'])
            search = CommandSearch(); search.observe(rows[last]['t'],teachers[last]['visible_target'],None)
            pose = rows[last]['applied_command']['pwm']; previous = rows[last]['applied_command']
            generated = []; now = rows[last]['t']
            # Actual remaining perturb commands are integrated first.
            for i in range(last+1,len(rows)):
                now = rows[i]['t']; search.observe(now,None,previous)
                if rows[i]['perturbation_interval']:
                    previous = rows[i]['applied_command']; continue
                break
            start = now
            while True:
                value, exhausted, diagnostic = search.action(now,
                    {'t':now,'wheels':[0.]*4,'duration_s':[0.]*4,'pwm':pose},gaze_pose,slew)
                generated.append({'t':now,'command':value,'exhausted':exhausted,'search':diagnostic})
                if exhausted:break
                previous=value; pose=value['pwm']; now+=.1
                search.observe(now,None,previous)
            path=output/'8316902-counterfactual-search.jsonl'
            path.write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in generated))
            pose0={int(k):v for k,v in rows[last]['applied_command']['pwm'].items()}
            distance=math.hypot(*teachers[last]['visible_target']['xyz'][:2])
            chosen=gaze_pose([distance,0.,teachers[last]['visible_target']['xyz'][2]],pose0)
            origin, axes=camera_extrinsics(chosen)
            baseline12=min(rows,key=lambda r:abs(r['t']-12.))
            _, baseline_axes=camera_extrinsics({int(k):v for k,v in baseline12['applied_command']['pwm'].items()})
            entry['counterfactual_search']={'path':str(path),'sha256':sha256(path),
                'search_s':now-start,'commanded_body_scan_deg':math.degrees(search.scan_yaw),
                'stages':sorted({r['search']['stage'] for r in generated}),
                'range_m':distance,'range_matched_pwm':chosen,
                'optical_axis_elevation_deg':math.degrees(math.asin(float(axes[2,2]))),
                'baseline12_optical_axis_elevation_deg':math.degrees(math.asin(float(baseline_axes[2,2]))),
                'scope':'command/FK only, fixed no-visibility input; not executed or a recovery success'}
        trace=output/f'{seed}-bearing-eval.jsonl'
        trace.write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in errors))
        entry['bearing_trace']={'path':str(trace),'sha256':sha256(trace)}
        runs.append(entry)
    report={'schema':'ugrp.act10.offline.v1','baseline_source':'ec0bd628',
        'training_rgb':False,'data_admitted':False,'simulation_executed':False,'runs':runs,
        'scope':'saved ledger/FK replay; evaluator truth only for bearing error; no new physical gate result'}
    write_json(output/'summary.json',report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runs-root','evidence-root','dependency-root','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args(); report=replay(a.runs_root,a.evidence_root,a.dependency_root,a.output)
    print(json.dumps([{'seed':r['seed'],'ticks':r['command_ticks'],'off_equal':r['search_disabled_commands_equal'],
        'bearing':r['hidden_bearing']} for r in report['runs']],allow_nan=False))


if __name__=='__main__':main()
