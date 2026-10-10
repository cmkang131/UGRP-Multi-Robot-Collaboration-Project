"""Saved egomap64 JSON arithmetic only; no controller replay or simulation."""
import json,math,statistics
from collections import Counter
from pathlib import Path
ROOT=Path('/Users/changmin/projects/ugrp/outputs/oracle-runs/egomap64-batch/data')
OUT=Path(__file__).resolve().parents[1]/'results/diagnosis.json'
def wrap(x):return math.atan2(math.sin(x),math.cos(x))
def stats(xs):
    xs=sorted(xs)
    return dict(n=len(xs),median=statistics.median(xs),p90=xs[int(.9*(len(xs)-1))],max=max(xs)) if xs else dict(n=0)
def geometry(h):
    plan=h['plan'];xy=plan['path_m'][0];path=plan['path_m'];yaw=plan['heading_rad']
    point=next((p for p in path if math.dist(xy,p)>=.035),path[-1])
    bearing=math.atan2(point[1]-xy[1],point[0]-xy[0])
    return xy,point,bearing,yaw,wrap(bearing-yaw)
def audit(p):
    result=json.loads((p/'result.json').read_text());start=result['start_sim_s']
    h=[r for r in json.loads((p/'heading-decisions.json').read_text()) if r['t']>=start]
    gt={round(r['t'],6):r for r in map(json.loads,(p/'eval_only/trajectory.jsonl').read_text().splitlines())}
    flips=[];allpairs=[];near=[];missing=0
    for a,b in zip(h,h[1:]):
        if b['t']-a['t']>.21:continue
        if not a['action'].get('turn'):continue
        xa,pa,ba,ya,ea=geometry(a);xb,pb,bb,yb,eb=geometry(b)
        dp=a['predicted_delta'][2];dy=wrap(yb-ya);db=wrap(bb-ba)
        innovation=wrap(dy-dp)
        row=dict(t=b['t'],heading_error_before=ea,heading_error_after=eb,
            target_bearing_change=db,estimated_yaw_change=dy,predicted_yaw=dp,yaw_innovation=innovation,
            waypoint_shift_m=math.dist(pa,pb),carrot_distance_m=math.dist(xa,pa))
        if round(a['t'],6) in gt and round(b['t'],6) in gt:
            gy=wrap(gt[round(b['t'],6)]['robot_yaw_rad']-gt[round(a['t'],6)]['robot_yaw_rad'])
            row.update(actual_yaw_change=gy,est_minus_actual_yaw_change=wrap(dy-gy))
        else:missing+=1
        # Exact local error change decomposes into target-bearing - predicted yaw - yaw innovation.
        row['dominant_error_change']=max({'target_bearing':abs(db),'predicted_pulse':abs(dp),'yaw_innovation':abs(innovation)},key=lambda k:{'target_bearing':abs(db),'predicted_pulse':abs(dp),'yaw_innovation':abs(innovation)}[k])
        allpairs.append(row)
        if b['action'].get('turn',0)*a['action']['turn']<0:flips.append(row)
        if abs(ea)<abs(dp):near.append(row)
    return dict(seed=result['seed'],profile=result['profile'],heading_decisions=len(h),successive_turn_feedback=len(allpairs),
        consecutive_heading_reversals=len(flips),dominant_reversal_components=dict(Counter(r['dominant_error_change'] for r in flips)),
        reversal_abs_target_delta_rad=stats([abs(r['target_bearing_change']) for r in flips]),
        reversal_abs_yaw_innovation_rad=stats([abs(r['yaw_innovation']) for r in flips]),
        reversal_abs_est_minus_actual_yaw_rad=stats([abs(r['est_minus_actual_yaw_change']) for r in flips if 'est_minus_actual_yaw_change' in r]),
        reversal_waypoint_shift_m=stats([r['waypoint_shift_m'] for r in flips]),
        reversal_carrot_distance_m=stats([r['carrot_distance_m'] for r in flips]),
        turn_error_smaller_than_one_pulse=len(near),min_pulse_rad=stats([abs(r['predicted_yaw']) for r in allpairs]),
        pulse_only_can_cross_opposite_deadband=sum(abs(wrap(r['heading_error_before']-r['predicted_yaw']))>.06 and r['heading_error_before']*wrap(r['heading_error_before']-r['predicted_yaw'])<0 for r in allpairs),
        missing_gt_pairs=missing,wall_per_sim=result['wall_s']/(result['total_sim_s']-start),examples=flips[:4])
def main():
    rows=[audit(p) for p in sorted(ROOT.glob('stage-*'))]
    out=dict(schema='egomap65.raw_heading_diagnosis.v1',rows=rows,limits='Exact algebraic attribution, not causal intervention; .2s consecutive host decisions only. Longer gaps/recovery turns excluded.',
             heading_deadband_rad=.06,deadband_full_width_rad=.12)
    OUT.write_text(json.dumps(out,indent=2)+'\n')
    for profile in ['baseline','a']:
        selected=[r for r in rows if r['profile']==profile];counts=Counter()
        for r in selected:counts.update(r['dominant_reversal_components'])
        print(profile,dict(pairs=sum(r['successive_turn_feedback'] for r in selected),reversals=sum(r['consecutive_heading_reversals'] for r in selected),dominant=dict(counts),pulse_only_cross=sum(r['pulse_only_can_cross_opposite_deadband'] for r in selected),wall_per_sim_max=max(r['wall_per_sim'] for r in selected)))
if __name__=='__main__':main()
