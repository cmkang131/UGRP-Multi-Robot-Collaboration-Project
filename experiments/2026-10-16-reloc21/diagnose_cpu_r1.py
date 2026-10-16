"""Terminal root-cause ledger on gcp2; evaluation never feeds control."""
import collections
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
R=Path('/home/ugrp/ugrp-sim/runs');B=R/'reloc21-round1'
def read(p):return p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'])
def obj(p):return json.loads(read(p))


def main():
    assert platform.node().startswith('ugrp-sim-gcp2') and (B/'ANALYSIS_DONE').exists()
    reports=[]
    for t in obj(B/'queue.json')['runs']:
        if t['kind']!='carry':continue
        raw=Path(t['raw']);d=obj(raw/'result.json');carry=d['teacher']['carry']
        c=[json.loads(x) for x in read(raw/'teacher-commands.jsonl').splitlines()];ev={round(x['t'],5):x for x in [json.loads(z) for z in read(raw/'eval-only.jsonl').splitlines()]};headings={}
        for x in c:
            h=x['map_pose'].get('reloc15_heading',{});at=h.get('exposure_sim_t')
            if h.get('status')!='accepted' or at is None or at in headings:continue
            e=ev.get(round(at,5))
            if e is None:continue
            delta=h['observed_yaw_rad']-e['base_yaw_rad'];error=abs(math.degrees(math.atan2(math.sin(delta),math.cos(delta))))
            headings[at]=dict(t=at,observed_yaw_rad=h['observed_yaw_rad'],eval_yaw_rad=e['base_yaw_rad'],error_deg=error,
                innovation=h.get('reloc18_innovation'),scope='evaluation only; never sent to controller')
        control=[dict(t=x['t'],phase=x.get('phase_before',x['phase']),command=x['command']) for x in c]
        body=json.dumps(control,sort_keys=True,separators=(',',':')).encode()
        nav=carry.get('reloc21_progress') or {};rows=[]
        motion=carry.get('reloc20_motion') or {};route=motion.get('footprint') or {}
        for key,N in collections.Counter(e['event'] for e in nav.get('events',[])).items():rows.append(dict(category='progress_event',reason=key,N=N,blocked_object='route_or_own_rgb',minimum_gap_m=None,gap_scope='see_original_events_for_physical_context'))
        bad=[v for v in headings.values() if v['error_deg']>5]
        reports.append(dict(run=t['name'],condition=t['condition'],seed=t['seed'],raw=str(raw),
            command_rows=len(control),control_decoded_sha256=hashlib.sha256(body).hexdigest(),
            route_plan_funnel=route.get('plan_funnel'),route_rejections=route.get('rejections'),
            heading=dict(accepted=len(headings),eval_error_over5=len(bad),first_bad=bad[0] if bad else None,bad_examples=bad[:4]),
            final_pose_estimate=carry['self_pose']['pose_estimate'],goal=carry.get('stand_off_xy'),
            final_remaining_estimate_m=math.dist(carry['self_pose']['pose_estimate'][:2],carry['stand_off_xy']),
            final_plan_selection=nav.get('selection'),events=rows,
            destination=carry.get('destination_visual_acquire'),
            result_decoded_sha256=hashlib.sha256(read(raw/'result.json')).hexdigest()))
    duplicate=[]
    for seed in (93266,93315):
        a=next(x for x in reports if x['seed']==seed and x['condition']=='progress');b=next(x for x in reports if x['seed']==seed and x['condition']=='complete')
        duplicate.append(dict(seed=seed,progress_complete_same_actuator_trajectory=a['control_decoded_sha256']==b['control_decoded_sha256'],sha256=a['control_decoded_sha256']))
    out=dict(analysis_host=platform.node(),reproduce=f'python {__file__}',script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='CPU diagnostic only. Wrong accepted headings are evaluator findings, not independent causal fractions; same seed repeated trajectories not pooled.',duplicates=duplicate,runs=reports)
    (B/'root-cause-evidence.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(dict(duplicates=duplicate,heading=[dict(run=x['run'],heading=x['heading']) for x in reports]),indent=2))


if __name__=='__main__':main()
