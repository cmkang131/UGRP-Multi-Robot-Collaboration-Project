"""GCP-only saved carry yaw audit. Truth is evaluation output only."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scripts.analyze_reloc11_selfmap import rows
from sim.solo_carry_pose import CommandPose


def wrap(a):
    return (a+math.pi) % (2*math.pi)-math.pi


def analyze(folder):
    raw = folder/'raw'
    commands = rows(raw/'teacher-commands.jsonl')
    truth = {round(r['t'], 5): r for r in rows(raw/'eval-only.jsonl')
             if 'map_pose_error_yaw_rad' in r}
    if not commands or not commands[0].get('map_pose'):
        return dict(run=folder.name, status='missing_map_pose', intervals=[])
    first = commands[0]['map_pose']
    loc = CommandPose(first['task_start'], now=commands[0]['t'],
        drive_model_deadband_v1=first.get('drive_model_deadband_v1', False),
        reloc9_rotation_calibration_v1=first.get('reloc9_rotation_calibration_v1', False),
        reloc10_rotation_calibration_v1=first.get('reloc10_rotation_calibration_v1', False))
    unsafe_t={a['t'] for a,b in zip(commands,commands[1:])
        if a.get('map_pose',{}).get('rgb_fixes') != b.get('map_pose',{}).get('rgb_fixes')}
    # The evaluator may see a relook correction issued after map_pose logging.
    # Exclude both adjacent intervals, including a terminal corrected row when
    # its evaluator-only post-step estimate differs from the logged estimate.
    for r in commands:
        e=truth.get(round(r['t'],5),{});post=e.get('lookaround_estimate_xy')
        if post is not None and not np.array_equal(post,r['map_pose']['pose_estimate'][:2]):
            unsafe_t.add(r['t'])
    groups = defaultdict(list)
    intervals = []
    excluded = defaultdict(int)
    for old, current in zip(commands, commands[1:]):
        dt = current['t']-old['t']
        loc.now = old['t']
        loc.issue(old['command'], dt)
        delta = loc.last_delta
        a, b = truth.get(round(old['t'], 5)), truth.get(round(current['t'], 5))
        if not a or not b or a['map_pose_error_yaw_rad'] is None or b['map_pose_error_yaw_rad'] is None:
            excluded['missing_truth'] += 1
            continue
        ma, mb = old['map_pose'], current['map_pose']
        # Eval yaw errors are scored after teacher.step; a same-t relook may
        # change the estimate after map_pose was captured. Exclude BOTH sides
        # of fix-count changes from this saved-log reconstruction.
        if old['t'] in unsafe_t or current['t'] in unsafe_t or ma['rgb_fixes'] != mb['rgb_fixes']:
            excluded['fix_boundary'] += 1
            continue
        ya = ma['pose_estimate'][2]-a['map_pose_error_yaw_rad']
        yb = mb['pose_estimate'][2]-b['map_pose_error_yaw_rad']
        actual = wrap(yb-ya)
        w = np.asarray(old['command']['wheels'])*np.minimum(dt, old['command']['duration_s'])
        # Algebraic mecanum components: classification uses issued commands,
        # not a learned tolerance or the truth. Exact zero: command schema.
        forward, left, turn = w@np.array([[1,-1,-1], [1,1,1], [1,1,-1], [1,-1,1]])/4
        trans = forward != 0 or left != 0
        mode = 'mixed' if trans and turn != 0 else 'translation' if trans else 'rotation' if turn != 0 else 'idle'
        held = bool(a.get('finger_contacts') and a['min_z'] > a.get('support_z', 0))
        command_closed = old['command']['pwm']['1'] <= 1600
        # Pure translation's ~1e-17 model yaw is floating cancellation. The
        # error bound is machine epsilon times the sum of the four terms;
        # this is arithmetic precision, not a motion acceptance threshold.
        predicted_yaw=delta[2]
        if abs(predicted_yaw) <= np.finfo(float).eps*sum(abs(w)):
            predicted_yaw=0.
        r = dict(t0=old['t'], t1=current['t'], phase=old['phase'], held_eval=held,
            command_closed=command_closed, mode=mode, command_yaw_rad=predicted_yaw,
            actual_yaw_rad=actual, command_distance_m=math.hypot(*delta[:2]),
            min_z_m=a['min_z'], finger_contacts=a.get('finger_contacts'),
            finger_force_N=a['finger_forces'], actual_xy_m=math.dist(a['base_xyz'][:2], b['base_xyz'][:2]))
        intervals.append(r)
        groups[(held, mode)].append(r)
    summaries=[]
    for (held, mode), es in sorted(groups.items()):
        c=np.array([e['command_yaw_rad'] for e in es]); y=np.array([e['actual_yaw_rad'] for e in es])
        summaries.append(dict(held_eval=held, command_mode=mode, N=len(es), sim_s=sum(e['t1']-e['t0'] for e in es),
            command_abs_yaw_deg=float(np.degrees(abs(c).sum())), actual_abs_yaw_deg=float(np.degrees(abs(y).sum())),
            actual_net_yaw_deg=float(np.degrees(y.sum())),
            actual_over_command_abs=float(abs(y).sum()/abs(c).sum()) if abs(c).sum() else None,
            ratio_status='defined' if abs(c).sum() else 'undefined_zero_command_yaw',
            zero_command_actual_abs_yaw_deg=float(np.degrees(abs(y[c == 0]).sum())),
            residual_abs_yaw_p50_p95_max_deg=np.degrees(np.quantile(abs(y-c), [.5,.95,1])).tolist(),
            command_distance_m=sum(e['command_distance_m'] for e in es),
            actual_xy_m=sum(e['actual_xy_m'] for e in es),
            min_cargo_z_m=min(e['min_z_m'] for e in es)))
    observed={(g['held_eval'],g['command_mode']) for g in summaries}
    for held in (False,True):
        for mode in ('idle','translation','rotation','mixed'):
            if (held,mode) not in observed:
                summaries.append(dict(held_eval=held,command_mode=mode,N=0,sim_s=0.,
                    command_abs_yaw_deg=0.,actual_abs_yaw_deg=0.,actual_net_yaw_deg=0.,
                    actual_over_command_abs=None,ratio_status='no_samples',
                    zero_command_actual_abs_yaw_deg=0.,residual_abs_yaw_p50_p95_max_deg=None,
                    command_distance_m=0.,actual_xy_m=0.,min_cargo_z_m=None))
    summaries.sort(key=lambda g:(g['held_eval'],g['command_mode']))
    high=max((r for r in commands if r.get('map_pose') and round(r['t'],5) in truth and
        truth[round(r['t'],5)].get('map_pose_error_yaw_rad') is not None),
        key=lambda r:abs(truth[round(r['t'],5)]['map_pose_error_yaw_rad']),default=None)
    return dict(run=folder.name, raw=str(raw), status='scored', groups=summaries,
        excluded=dict(excluded), intervals=intervals,
        max_error=None if high is None else dict(t=high['t'],phase=high['phase'],
            error_yaw_deg=math.degrees(truth[round(high['t'],5)]['map_pose_error_yaw_rad']),
            command_since_fix=high['map_pose']['issued_turn_since_fix_rad'],
            distance_since_fix=high['map_pose']['issued_distance_since_fix_m'],
            last_fix_t=high['map_pose']['last_rgb_fix_t']),
        sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in raw.glob('*.jsonl*')})


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--pattern',default='reloc*-carry*');a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    results=[analyze(f) for f in sorted(a.root.glob(a.pattern))]
    full=dict(schema='ugrp.reloc15.carry_yaw.v1',analysis_host='gcp1',truth_scope='offline evaluation only',runs=results,
        input_pattern=a.pattern,command_yaw_definition='calibrated issued-command drive model; zero raw duty yaw may retain a modeled stop tail; command classes use integrated wheel duties',held_definition='finger_contacts and cargo min_z above support; issued closure recorded separately',
        limitation='saved error reconstruction excludes fix boundaries; exact physical replay required for causal contact attribution')
    (a.out/'carry-yaw-full.json').write_text(json.dumps(full,indent=2)+'\n')
    summary={**full,'runs':[{k:v for k,v in r.items() if k!='intervals'} for r in results]}
    (a.out/'carry-yaw.json').write_text(json.dumps(summary,indent=2)+'\n')
    fmt=lambda x: f'{x:.5f}' if x is not None else 'n/a'
    lines=['# reloc15 수정 전 운반 yaw 분포', '', '정답은 GCP 오프라인 평가에만 사용. 0 명령 yaw의 비는 정의하지 않음.', '',
        '|원본|held 평가|명령|N|명령 abs °|실제 abs °|실제/명령|순회전 °|최소 화물 z m|',
        '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for r in results:
        for g in r.get('groups',[]):
            ratio=g['actual_over_command_abs'];ratio=f'{ratio:.3f}' if ratio is not None else g['ratio_status']
            lines.append(f"|{r['run']}|{g['held_eval']}|{g['command_mode']}|{g['N']}|{g['command_abs_yaw_deg']:.3f}|{g['actual_abs_yaw_deg']:.3f}|{ratio}|{g['actual_net_yaw_deg']:.3f}|{fmt(g['min_cargo_z_m'])}|")
    (a.out/'carry-yaw.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(runs=len(results),scored=sum(r['status']=='scored' for r in results),maxima=[(r['run'],r.get('max_error')) for r in results])))


if __name__=='__main__':main()
