"""Build new disabled queues from reloc12 evidence, never inherit old approvals."""
import argparse,json,copy
from statistics import median
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FLAGS=('approved','enabled','execute','submitted')


def admission(reports):
    events=[e for r in reports for e in r['registration_events']]
    audit=all(r.get('invisible_measurements')==r.get('held_world_reads')==0 and
        r.get('input_audit',{}).get('top_rgb_frames')==0 for r in reports)
    speeds=[r.get('first30',{}).get('wall_per_sim') for r in reports]
    frames=sum(r.get('registered_frame_errors',{}).get('N',0) for r in reports)
    false_frames=sum(r.get('registered_frame_errors',{}).get('false_N',0) for r in reports)
    low_false=frames>0 and false_frames/frames<=.05
    speed_ok=bool(speeds) and all(v is not None for v in speeds) and median(speeds)<=6
    complete=bool(reports) and all(r.get('status')=='RECORDED' for r in reports)
    ready=bool(reports) and complete and bool(events) and low_false and all(e['within_10cm_5deg'] for e in events) and audit and speed_ok
    reasons=[]
    if not events:reasons.append('no_static_registration')
    if any(not e['within_10cm_5deg'] for e in events):reasons.append('false_registration_10cm_5deg')
    if not low_false:reasons.append('registered_frame_false_fraction_over_5pct_or_absent')
    if not audit:reasons.append('input_audit_incomplete_or_nonzero')
    if not speed_ok:reasons.append('first30_speed_incomplete_or_median_over_6')
    if not complete:reasons.append('HOST_ERROR_or_unfinished_run')
    return dict(ready=ready,reasons=reasons,registration_event_N=len(events),registered_frame_N=frames,false_frame_N=false_frames,
                max_false_frame_fraction=.05,first30_wall_per_sim_median=median(speeds) if speeds and all(v is not None for v in speeds) else None,false_event_N=sum(not e['within_10cm_5deg'] for e in events),
                requirement='all installation events within 10cm/5deg and registered-frame error fraction <=5%; conservative reloc12 DEV admission, not general localization success')


def queues(sha,reports,source_worktree):
    gate=admission(reports)
    common=dict(schema='ugrp.reloc12.queue.v1',source_sha=sha,sha=sha,source_worktree=str(source_worktree),host='gcp1',
        project='ugrp-act-train-1014',machine_type='n4-highcpu-64',pr=506,max_parallel=16,aggregate_max_parallel=40,
        vm_max_run_duration_s=86400,idle_timeout_s=1200,budget_stop_required=True,
        render_profile='floor_light_textured_v1',pool_with_previous_results=False,runs_enabled=False,
        ready=gate['ready'],status='PREPARED_NOT_SUBMITTED' if gate['ready'] else 'BLOCKED',admission=gate,
        previous_queues_reused=False,training_approved=False,automatic_promotion=False,**{f:False for f in FLAGS})
    selfmap=copy.deepcopy(common);carry=copy.deepcopy(common)
    selfmap.update(queue='reloc12-selfmap',candidate='raw_cov_plus_ransac',runs=[])
    for seed in [93571,93600,93601,93602,93603]:
        name=f'reloc12-selfmap-{seed}-{sha[:8]}'
        command=['.venv-sim/bin/python','-m','scripts.run_self_map_diagnostic','--output',f'/home/ugrp/ugrp-sim/runs/{name}/raw',
            '--expected-source-sha',sha,'--seed',str(seed),'--cap-s','90','--execution-host','gcp1','--project','ugrp-act-train-1014',
            '--self-map-executor','frontier_drive_v1','--bootstrap','command_prior_v1','--initial-sweep','required_360_v1',
            '--recovery-profile','selfmap4_recovery_v1','--revision-gate','selfmap4_revision_gate_v2',
            '--multiframe-registration','selfmap4_multiframe_registration_v1','--render-profile','floor_light_textured_v1',
            '--correction-safety','selfmap6_correction_safety_v1','--active-relocalization','reloc8_active_vision_v1',
            '--reloc10-settle-v1','--reloc10-registration-v1','--reloc11-timing-v1','--reloc11-half-rate-v1',
            '--reloc11-low-contrast-v1','--reloc12-raw-cov-gate-v1','--reloc12-ransac-hypotheses-v1']
        selfmap['runs'].append(dict(name=name,seed=seed,source_sha=sha,command=command,ready=gate['ready'],**{f:False for f in FLAGS}))
    plan=json.loads((ROOT/'experiments/2026-10-15-reloc12/carry-texture-plan.json').read_text())
    carry.update(queue='reloc12-carry-texture',runs=[],plan_path='experiments/2026-10-15-reloc12/carry-texture-plan.json',
        carry_physics_verified=False,first_stage='93266 reproduction; stop on confirmed recurrence',
        candidates=['rotation','rotation_wall_search'],pool_candidates=False)
    order=sorted(range(len(plan['episodes'])),key=lambda i:(plan['episodes'][i]['seed']!=93266,i))
    for i in order:
        e=plan['episodes'][i];candidate=e.get('reloc10_candidate',e.get('reloc9_candidate','rotation'))
        name=f'reloc12-carry-{e["seed"]}-{candidate}-{sha[:8]}'
        command=['.venv-sim/bin/python','-m','scripts.run_solo_grasp_act_teacher','--plan',carry['plan_path'],'--episode',str(i),
            '--out',f'/home/ugrp/ugrp-sim/runs/{name}/raw','--execution-host','gcp1','--teacher-profile','solo_visible_only_v1',
            '--held-object-hidden-v1','--setdown-lookaround-v1','--teacher-stability','align_relook_v1','--reach-mode','pad_window_v2',
            '--rgb-lift-mode','solo_lift_lookback_v1','--solo-lift-lookback-margin-v1','--solo-truth-free-lookaround-v1',
            '--solo-carry-to-zone-v1','--cap-s','300']
        carry['runs'].append(dict(name=name,seed=e['seed'],candidate=candidate,source_sha=sha,command=command,ready=gate['ready'],**{f:False for f in FLAGS}))
    for q in (selfmap,carry):
        q['run_count']=len(q['runs'])
    selfmap['execution_stages']=[dict(name='failure_seed_first',indices=[0]),dict(name='fresh_four',indices=[1,2,3,4],requires='first run original review and operator admission')]
    carry['execution_stages']=[dict(name='93266_first',indices=[0,1]),dict(name='other_reproductions',indices=list(range(2,6)),requires='93266 original review'),dict(name='fresh',indices=list(range(6,22)),requires='reproduction review')]
    return selfmap,carry


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-sha',required=True);p.add_argument('--reports',type=Path,required=True)
    p.add_argument('--source-worktree',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    reports=json.loads(a.reports.read_text());a.output_dir.mkdir(parents=True,exist_ok=True)
    for label,q in zip(('selfmap','carry-texture'),queues(a.source_sha,reports,a.source_worktree)):
        target=a.output_dir/f'20261015-reloc12-{label}-{a.source_sha[:8]}.json'
        with target.open('x') as f:json.dump(q,f,indent=2);f.write('\n')
        print(json.dumps(dict(path=str(target),status=q['status'],runs=len(q['runs']))))


if __name__=='__main__':main()
