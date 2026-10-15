"""Saved physical carry diagnostics on GCP; evaluator truth only for errors."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from scripts.analyze_reloc11_selfmap import rows, obj
from scripts.analyze_reloc13 import distribution


def analyze(folder):
    raw=folder/'raw'; trace=rows(raw/'teacher-commands.jsonl'); evaluation=rows(raw/'eval-only.jsonl')
    result=obj(raw/'result.json'); phases=Counter(r['phase'] for r in trace)
    transitions=[]; previous=None
    for r in trace:
        if r['phase']!=previous:
            transitions.append(dict(t=r['t'],phase=r['phase'],map_pose=r.get('map_pose')))
        previous=r['phase']
    # A run-level funnel uses first ordered entry; repeat/recovery events stay separate.
    stages=[('pickup_seen', ('approach','align')), ('aligned',('close','grip','lift')),
            ('lifted_controller',('carry_prepare','carry_to_zone','zone_place_view')),
            ('zone_place_view',('zone_place_view',)), ('release',('zone_lower','zone_open','zone_release','release','open'))]
    cursor=0; funnel={}; earlier=True
    for label, names in stages:
        found=next((i for i in range(cursor,len(trace)) if trace[i]['phase'] in names),None) if earlier else None
        earlier=found is not None
        funnel[label]=int(earlier)
        if found is not None: cursor=found
    teacher=result.get('teacher',{}); carry=teacher.get('carry',{})
    reasons=Counter()
    for e in carry.get('recovery_events',[]):reasons[str(e.get('reason') or 'unknown_requires_review')]+=1
    truth={round(e['t'],5):e for e in evaluation}; budget=[]
    for r in trace:
        m=r.get('map_pose',{});e=truth.get(round(r['t'],5),{});sigma=m.get('sigma_m_m_rad')
        if not sigma or e.get('map_pose_error_yaw_rad') is None:continue
        trueyaw=abs(math.degrees(e['map_pose_error_yaw_rad']));xy=e['map_pose_error_xy_m']
        budget.append(dict(t=r['t'],phase=r['phase'],xy_m=xy,yaw_deg=trueyaw,
            sigma_xy=max(sigma[:2]),sigma_yaw_deg=math.degrees(sigma[2]),
            trigger=max(sigma[:2])>=.5 or sigma[2]>=math.radians(41)))
    positives=[b for b in budget if b['yaw_deg']>=20]
    views=result.get('lookaround',{}).get('evaluation',{}).get('views',[])
    return dict(run=folder.name,raw=str(raw),source_sha=result.get('source_sha'),
        status=result.get('status'),termination_category=result.get('termination_category'),termination_reason=result.get('termination_reason') or result.get('error'),
        sim_s=result.get('sim_s'),wall_s=result.get('wall_s'),first30=obj(raw/'first30.json'),
        physical_success=result.get('physical_success'),physical_lifted=result.get('lifted'),
        physical_evaluation={k:v for k,v in result.items() if k in ('delivered','inside','release_success','placed','transport_success','stable_seconds')},
        funnel=funnel,phase_frames=dict(phases),phase_transitions=transitions,
        rejections=[dict(category=k,N=n,blocked_object='pose_uncertainty_budget' if k=='pose_budget' else 'see_carry_recovery_context',minimum_gap_m=None,
                        gap_status='not_applicable_localization_gate' if k=='pose_budget' else 'see_original') for k,n in reasons.most_common()],
        carry=carry,teacher_result=teacher.get('command_result'),teacher_events=teacher.get('events'),
        input_audit=result.get('input_audit'),visibility=result.get('visibility'),
        pose_error=dict(N=len(budget),xy_m=distribution([b['xy_m'] for b in budget]),yaw_deg=distribution([b['yaw_deg'] for b in budget]),
            true_yaw_over20_N=len(positives),trigger_recall=sum(b['trigger'] for b in positives)/len(positives) if positives else None,
            max_untriggered_yaw_deg=max((b['yaw_deg'] for b in budget if not b['trigger']),default=None)),
        views=views,
        sha256={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                (raw/'result.json',raw/'teacher-commands.jsonl.zst',raw/'eval-only.jsonl.zst',folder/'EXIT') if p.exists()})


def main():
    p=argparse.ArgumentParser();p.add_argument('folders',nargs='+',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    data=[analyze(f) for f in a.folders]
    a.output.write_text(json.dumps(dict(schema='ugrp.reloc13.carry_funnel.v1',analysis_host='gcp1',
        reproduce='PYTHONPATH=. .venv-sim/bin/python scripts/analyze_reloc13_carry.py <folders> --output <file>',runs=data),indent=2)+'\n')
    for r in data:print(json.dumps({k:r[k] for k in ('run','status','funnel','phase_frames','physical_success','termination_category','pose_error')}))


if __name__=='__main__':main()
