"""s2v59 evaluation only. Independent judge copied unchanged from PR393 audit.py."""
import argparse,hashlib,itertools,json,math,sys
from pathlib import Path
import numpy as np

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def vertices(row):
    r, c, h = row['cyan_rotation'], row['cyan_xyz_m'], row['box_half_m']
    return [[c[i] + sum(r[3*i+j]*sign[j]*h[j] for j in range(3)) for i in range(3)]
            for sign in itertools.product((-1, 1), repeat=3)]

def independent(rows, region):
    if not rows:
        return {'valid': False, 'success': None, 'reason': 'NO_TRAJECTORY'}
    times = [r['t'] for r in rows]
    gaps = [b-a for a,b in zip(times, times[1:])]
    finite = all(math.isfinite(v) for r in rows for k in
                 ('cyan_xyz_m', 'cyan_rotation', 'box_half_m') for v in r[k])
    valid = (finite and all(math.isfinite(t) for t in times)
             and bool(gaps) and min(gaps) > 0 and max(gaps) <= .050001)
    tail = [r for r in rows if r['t'] >= times[-1]-2.-1e-8]
    corner_rows = [vertices(r) for r in tail]
    cx, cy = region['center_m']
    hx, hy = region['half_extents_m']
    inside = all(cx-hx <= v[0] <= cx+hx and cy-hy <= v[1] <= cy+hy
                 for vs in corner_rows for v in vs)
    floor = all(abs(min(v[2] for v in vs)) < .008 and r['cyan_xyz_m'][2] < .04
                for vs,r in zip(corner_rows, tail))
    displacement = max(math.dist(r['cyan_xyz_m'], rows[-1]['cyan_xyz_m']) for r in tail)
    stable = displacement <= .008
    lifted = any(r['cyan_xyz_m'][2] > .06 for r in rows)
    duration = tail[-1]['t']-tail[0]['t']
    success = lifted and inside and floor and stable and duration >= 1.95
    return dict(valid=valid, success=bool(success) if valid else None, lifted=lifted,
                inside=inside, floor=floor, stable=stable, settled_s=duration,
                final_xyz_m=rows[-1]['cyan_xyz_m'], rows=len(rows), max_gap_s=max(gaps, default=None),
                max_tail_displacement_m=displacement)

def evaluate(raw):
 r=read(raw/'result.json');b=read(raw/'bundle.json');student=read(raw/'student_record.json')
 truth=[json.loads(q) for q in (raw/'eval_only/trajectory.jsonl').read_text().splitlines()]
 static=read(raw/'inputs/static_map.json');judge=independent(truth,static['regions']['zone_B'])
 report=r.get('evaluation',{});mismatch=judge['valid'] and report.get('success')!=judge['success']
 manifest=read(raw/'artifacts.sha256.json')
 bad=[p for p,h in manifest.items() if not (raw/p).exists() or sha(raw/p)!=h]
 pe=r.get('posthoc_evaluation',{});unknown=r.get('unknown_start_evaluation',{});resources=read(raw/'resources.json')
 timestamps=np.array([q['t'] for q in truth]);yaw=np.unwrap([q['robot_yaw_rad'] for q in truth]);events=[]
 for e in student.get('active_localization',{}).get('events',[]):
  end=e.get('completed_t',truth[-1]['t']);inside=(timestamps>=e['t']-1e-8)&(timestamps<=end+1e-8)
  y0=np.interp(e['t'],timestamps,yaw)
  angle=float(np.degrees(np.max(abs(yaw[inside]-y0))))
  events.append(dict(t=e['t'],end=end,name=e['action']['name'],actual_max_abs_deg=angle,added_s=end-e['t'],
   stopped=e.get('rotation_guard_stop'),max_planned_deg=float(np.degrees(abs(e['action']['delta'][2])))))
 sim=r.get('check_sim_s',0);added=sum(q['added_s'] for q in events)
 success=bool(judge['valid'] and judge['success'] and report.get('success') and not bad and r['status']=='STAGE_REACHED_UNQUALIFIED')
 failure=r.get('failure')
 if success:category=None
 elif r['status']=='HOST_ERROR':category='HOST_ERROR'
 elif r['status']=='PHYSICAL_FAILURE':category='PHYSICAL_FAILURE'
 elif not judge['valid'] or bad:category='EVIDENCE_INVALID'
 elif mismatch:category='JUDGE_MISMATCH'
 elif not judge.get('lifted'):category='NOT_LIFTED'
 elif not judge.get('inside'):category='B_OUTSIDE'
 elif not judge.get('floor') or not judge.get('stable'):category='NOT_STABLY_SET_DOWN'
 else:category='CONTROLLER_NOT_COMPLETE'
 wall=resources['wall_s'];cpu=resources['cpu_self_and_reaped_children_s']
 out=dict(seed=b['task']['seed'],slot=b['task']['pickup_slot'],raw=str(raw),source_sha=b['source_sha'],bundle=b['execution_bundle_id'],options=b['options'],
  graduation_sample_success=success,evaluation=report,independent=judge,false_positive=bool(mismatch and report.get('success')),false_negative=bool(mismatch and not report.get('success')),
  false_stage_success=bool(r.get('stage_reached') and not judge.get('success')),failure_category=category,failure=failure,status=r['status'],
  sim_s=sim,wall_s=r['wall_s'],wall_per_sim=r['wall_per_sim'],wrapper_wall_s=wall,cpu_s=cpu,cpu_per_sim=cpu/sim if sim else None,
  active_count=len(events),active_added_s=added,active_added_fraction=added/sim if sim else None,
  max_actual_active_rotation_deg=max((q['actual_max_abs_deg'] for q in events),default=0.),
  active_rotation_violations=sum(q['actual_max_abs_deg']>90 for q in events),active_events=events,
  nees=unknown.get('nees_all_reported_covariances'),unflagged_gt_25cm=unknown.get('unflagged_gt_25cm'),
  first_convergence=unknown.get('first_convergence'),would_stop=r.get('conservative_stops'),
  carry_rmse_m=pe.get('carry_xy_rmse_m'),carry_updates=pe.get('visual_updates'),max_fix_gap_s=pe.get('max_update_gap_sim_s'),
  B_center_m=pe.get('cargo_distance_to_B_center_m'),B_remaining_m=pe.get('cargo_remaining_to_B_region_m'),wall_visibility=pe.get('actual_visibility'),
  resources=resources,artifact_files_verified=len(manifest),artifact_mismatches=bad,
  lock=read(raw/'lock.json'),gt='posthoc only, no runtime control input',
  hashes={p:sha(raw/p) for p in ['result.json','bundle.json','student_record.json','resources.json','eval_only/trajectory.jsonl']})
 return out


def report(cohort,dest):
 if dest.exists():raise ValueError('preserve existing report')
 dest.mkdir(parents=True)
 groups=read(cohort/'groups.json');plan=read(cohort/'registration.json')
 mapped={q['seed']:Path(q['output']) for group in groups if not group['serial_check'] for q in group['runs']}
 runs=[]
 for seed in plan['seeds']:
  if seed not in mapped or not (mapped[seed]/'result.json').exists():
   runs.append(dict(seed=seed,graduation_sample_success=False,failure_category='UNEXECUTED_OR_HOST_ERROR'));continue
  value=evaluate(mapped[seed]);runs.append(value)
  (dest/f's{seed}.json').write_text(json.dumps(value,indent=2)+'\n')
 benchmark={};repeat=next((g for g in groups if g['serial_check']),None)
 if repeat:
  raw=Path(repeat['runs'][0]['output']);extra=evaluate(raw);(dest/'serial-check.json').write_text(json.dumps(extra,indent=2)+'\n')
  original=mapped[plan['concurrency']['serial_check_seed']]
  compare={p:sha(original/p)==sha(raw/p) for p in ['eval_only/trajectory.jsonl','robots/r3/commands.jsonl']}
  compare['evaluation']=json.dumps(read(original/'result.json')['evaluation'],sort_keys=True).encode()==json.dumps(read(raw/'result.json')['evaluation'],sort_keys=True).encode()
  pair=groups[2];pair_sim=sum(q['sim_s'] for q in runs if q['seed'] in pair['seeds'])
  serial=[g for g in groups if not g['serial_check'] and len(g['seeds'])==1]
  serial_sim=sum(q['sim_s'] for q in runs if q['seed'] not in pair['seeds'])
  solo_rate=serial_sim/sum(q['wall_s'] for q in serial);pair_rate=pair_sim/pair['wall_s']
  ratio=pair_rate/solo_rate
  benchmark=dict(pair_seeds=pair['seeds'],serial_fresh_runs=len(serial),repeat_seed=extra['seed'],exact=compare,
   pair_sim_sum=pair_sim,pair_wall_s=pair['wall_s'],serial_sim_sum=serial_sim,serial_wall_sum_s=sum(q['wall_s'] for q in serial),
   pair_sim_per_wall=pair_rate,serial_sim_per_wall=solo_rate,ratio=ratio,effective=ratio>=1.3 and all(compare.values()),
   repeat_in_graduation_denominator=False,scope='one pair vs four different-seed/slot serial runs, one matched seed A/A; small n, no universal speedup claim')
 failures={}
 for q in runs:
  if not q['graduation_sample_success']:failures[q['failure_category']]=failures.get(q['failure_category'],0)+1
 result=dict(schema='ugrp.s2.graduation59.result.v1',registration_sha256=sha(cohort/'registration.json'),cohort=str(cohort),
  denominator=6,successes=sum(q['graduation_sample_success'] for q in runs),failure_counts=failures,
  false_positives=sum(q.get('false_positive',False) for q in runs),false_negatives=sum(q.get('false_negative',False) for q in runs),
  max_actual_active_rotation_deg=max(q.get('max_actual_active_rotation_deg',0) for q in runs),
  rotation_violations=sum(q.get('active_rotation_violations',0) for q in runs),runs=runs,benchmark=benchmark,
  overall_graduation_claim=False,scope='Six fresh no-prior solo DEV samples, freeze ON; not formal E2E, three-robot smoke or hardware validation; prior cohorts never pooled.')
 (dest/'result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k!='runs'},ensure_ascii=False))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('cohort',type=Path);p.add_argument('output',type=Path)
 a=p.parse_args();report(a.cohort,a.output)
