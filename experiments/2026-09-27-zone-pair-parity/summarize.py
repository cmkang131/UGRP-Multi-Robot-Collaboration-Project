"""Aggregate completed decision replays, then attach separate post-hoc GT scoring."""
import collections
import math
from pathlib import Path

import replay as r


def main():
    names=['dev-main.json','dev-grasp-v4.json','dev-grasp-v5.json','m2-shadow-main.json','m2-input-contracts.json']
    docs={n:r.read(r.OUT/n) for n in names}
    m=docs['m2-shadow-main.json']; robots=[v for run in m['runs'] for v in run['robots'].values()]
    closes=[v for run in docs['m2-input-contracts.json']['runs'] for rob in run['robots'].values() for v in rob['close_attempts']]
    results={'schema':'ugrp.zone_pair_parity_summary.v1','date':'2026-09-27','language':'ko',
       'scope':'saved-input decision replay, not new physical success or a full counterfactual rollout',
       'versions':{'worktree_head':r.git('rev-parse','HEAD'),'main_judge':r.MAIN,'grasp_v4':r.V4,'grasp_v5':r.V5,
                   'primary_head_observed':r.git('-C','/Users/changmin/projects/ugrp','rev-parse','HEAD')},
       'boundary':{'new_physics_steps':0,'new_model_calls':0,'renderer_calls':0,'gt_used_for_control':False,
                   'weld':False,'runner_files_modified':False,'git_commits':0,'raw_roots_read_only':True},
       'coordinator':r.read(r.OUT/'coordinator.json')['comments'][-1],
       'artifacts':{n:{'path':n,'sha256':r.sha(r.OUT/n),'bytes':(r.OUT/n).stat().st_size} for n in names},
       'counts':{'m2_success_runs':len(m['runs']),'m2_robot_traces':len(robots),'dev_failed_runs':6,
                 'm2_close_attempts':len(closes),'m2_close_fresh_and_matching_camera':sum(v['necessary_preclose_input_pass'] for v in closes),
                 'm2_shadow_verified_jpegs':sum(v['verified_jpegs'] for v in robots),
                 'm2_shadow_gate_reject_robot_traces':sum(v['first_shadow_postapproach_gate_reject'] is not None for v in robots),
                 'm2_shadow_geometry_reject_robot_traces':sum(v['first_shadow_geometry_reject'] is not None for v in robots),
                 'm2_static_plan_results':dict(collections.Counter(v['static_plan_admission'] for v in m['runs']))},
       'm2_close_frame_age_s':{'min':min(v['age_s'] for v in closes),'max':max(v['age_s'] for v in closes)},
       'exact_m2_cross_executor_stop_time':'insufficient_evidence: continuous original self PoseReport/yaw covariance and counterfactual fresh frames not saved',
       'm2_shadow_model':{'inputs':'only original own JPEG, issued PWM/base commands, frozen map/calibration',
           'seed':'original run seed for each robot','clock':'saved frame and rounded command events; same-tick control image precedes commands',
           'changes_from_original':'continuous shared pose feeding; no original PF resets, original controller predict grid or new-look frames reconstructed',
           'interpretation':'conditional predicate scan; continue original trace after a rejecting predicate to find independent later incompatibilities'},
       'dev_decisions':[], 'eval_only_posthoc':[],
       'findings':[
           {'rank':1,'id':'P1-1','classification':'integration_bug','difference':'shared PF vs separate M2 VO; no early align relook',
            'evidence':['dev05/06/08 own reports','dev-grasp-v5.json: v5_first_in_align_relook'],
            'recommendation':'one shared pose, bounded active relook before/during align; no VO covariance overwrite'},
           {'rank':2,'id':'P1-2','classification':'excess_or_bug','difference':'attached full beam before own RGB grasp confirmation',
            'evidence':['dev05 65-command prefix match; next batch main rejects, grasp v4/v5 accepts'],
            'recommendation':'phase-aware attachment plus independent stationary-beam clearance'},
           {'rank':3,'id':'P1-3','classification':'excess_or_missing_observation_contract','difference':'END_CLIPPED rejected unconditionally',
            'evidence':['dev07 same causal own RGB: grasp v4 false, v5 true; clearance +0.680877 m'],
            'recommendation':'bounded partial patch constraint with full anchor; never reset pose/age/sigma from partial PCA'},
           {'rank':4,'id':'P1-4','classification':'safety_function_needed_numeric_optimality_unresolved',
            'difference':'continuous loaded gate absent in M2; no-tag process noise and phase mismatch',
            'evidence':['dev06 yaw HIGH','dev08 XY HIGH','conditional M2 shadow 98/98 yaw HIGH'],
            'recommendation':'calibrate phase/no-tag uncertainty and bounded shared carry checkpoints; no blanket threshold/noise reduction'},
           {'rank':5,'id':'P1-5','classification':'scene_contract_bug_and_needed_admission_safety',
            'difference':'old dock clearance < fixed margin; fixed-time single submission',
            'evidence':['dev03/04 direct readiness and stored sweep receipts'],
            'recommendation':'versioned inset dock; bounded readiness-based submission design'},
           {'rank':6,'id':'P2-1','classification':'safety_needed','difference':'dual READY/GO and abort/silence interlocks',
            'recommendation':'retain; past successful nominal trajectories do not justify removing them'},
           {'rank':7,'id':'P2-2','classification':'supported_scope_difference','difference':'open-floor admission and B destination extension',
            'recommendation':'match task, map, spawn, route, source and observation contract before future parity comparison'}],
       'recommended_bundle':{'already_implemented_elsewhere_ref':r.V5,
           'include':['bounded active align shared-pose relook','own-RGB confirmed attachment only','full-anchor partial preclose',
                      'both partners close READY/GO','versioned dock with unchanged map/scene hash contract'],
           'expected_effect':'removes demonstrated dev05/07 predicate incompatibilities and requests earlier observations for dev08',
           'not_demonstrated':'new look success, joint grasp/lift/carry, new-seed success rate',
           'remaining_design':'loaded no-tag uncertainty, carry/wait timing and coordinated checkpoint budget',
           'risks':['look consumes align/close deadline','predicted tag visibility can be wrong','partial patch false positive',
                    'later loaded yaw HIGH remains possible']},
       'verification':{'existing_regressions_passed':37,'latest_v5_decision_regressions_passed':28,
                       'latest_v5_cli_registration_tests_deselected':9,'analysis_regressions_passed':6,'total_relevant_checks':71,
                       'test_harness_correction':'initial latest full-file overlay: 28 passed/9 failed because main CLI lacks PREREG_V5; final scope explicitly excludes CLI registration, not a full branch CI claim',
                       'OMP_NUM_THREADS':1,'basetemp':'./.pytest_tmp','temporary_pytest_directory_removed':not (r.ROOT/'.pytest_tmp').exists()},
       'limitations':['No new RGB after a changed look trajectory; no full physics counterfactual.',
                      'M2 shadow PF is conditional and not the saved original estimator. Do not interpret 98/98 as failure probability.',
                      'v5 dev09/dev10 completed result files not present at inspection; no polling or completion claim.',
                      'Shared TensorBoard publication and GUI verification require access outside this workspace.'],
       'tensorboard':{'shared_root':'/Users/changmin/projects/ugrp/outputs/tensorboard','dashboard_url':'http://127.0.0.1:6006',
                     'shared_publication':'blocked_by_workspace_write_scope','gui_verified':False,
                     'temporary_snapshot_receipt':r.read(r.OUT/'tensorboard.json')},
       'git':{'fetch':'failed: shared FETCH_HEAD write denied','live_issue_read':'GitHub connector succeeded at canonical renamed repository',
              'open_prs_read':True,'comments_posted':False,'committed':False,'pushed':False,'merged':False,'primary_modified':False}}
    for run in docs['dev-main.json']['runs']:
        latest=next(x for x in docs['dev-grasp-v5.json']['runs'] if x['id']==run['id'])
        info={'id':run['id'],'source_sha':run['source_sha'],'robots':{}}
        for rid,rob in run['robots'].items():
            li=latest['robots'][rid]
            info['robots'][rid]={'admission':rob['replayed_admission']['state'],
                'actual_stops':[{k:e[k] for k in ('sim_s','job_kind','detail')} for e in rob['actual_stops']],
                'first_pose_gate_reject':rob['first_postapproach_gate_reject'],
                'm2_local_predicate':rob['m2_at_actual_stop'],
                'v5_first_align_entry_relook_s':li.get('v5_first_align_entry_relook_s'),
                'v5_first_in_align_relook':li.get('v5_first_in_align_relook'),
                'v5_preclose_pass':li.get('preclose_replay',{}).get('accepted')}
        results['dev_decisions'].append(info)
        if run['id'] not in ('dev05','dev06','dev07','dev08'):continue
        root=Path(run['raw_root']); trace=root/'eval_only/trace.jsonl'
        assert r.sha(trace)==r.read(root/'artifacts.sha256.json')['eval_only/trace.jsonl']['sha256']
        truth=r.rows(trace); frames=r.read(root/'robots.json')
        er={'id':run['id'],'scope':'post-hoc scoring only; never passed to replay or recommendations as runtime input',
            'source':str(trace),'sha256':r.sha(trace),'robots':{}}
        for rid,rob in run['robots'].items():
            st=rob['m2_at_actual_stop']; t=st['last_causal_frame_s']
            f=min(frames[rid]['frames'],key=lambda x:abs(x['t']-t))
            gt=min(truth,key=lambda x:abs(x['t']-t))
            assert abs(gt['t']-t)<.001
            xy=f['report']['xyyaw'][:2]; actual=gt['robots'][rid][:2]
            er['robots'][rid]={'sim_s':t,'self_xy_error_m':math.dist(xy,actual),
                               'reported_sigma_xy_m':f['report']['std_xy_m'],'finger_n':gt['finger_n'][rid]}
        results['eval_only_posthoc'].append(er)
    results['source_hashes']={str(p.relative_to(r.ROOT)):r.sha(p) for p in [r.OUT/'replay.py',r.OUT/'trace_contracts.py',r.OUT/'summarize.py',
        r.ROOT/'harness/owncam_localizer.py',r.ROOT/'harness/owncam_pose_source.py',r.ROOT/'harness/zone_own_guards.py',r.ROOT/'scripts/run_m2_pair.py']}
    r.write(r.OUT/'results.json',results)
    lines=['# M2 성공 실행별 재판정','',
       'S = 저장 RGB·발행 명령의 별도 PF 재구성. 원본 PF의 정확한 중단시각이 아니다. G = 상시 gate의 최초 거부, C = 현재 형상 여유의 최초 음수(복구 결과가 아님).',
       '초기 C 뒤에도 원본 trace를 계속 읽어 G를 별도 측정했다. 정적 계획 거부는 열린 바닥/지원 범위 차이다. 시간은 원본 절대 SIM s.','',
       '| 실행 | 계획 | r1 S: G / C | r2 S: G / C |', '|---|---|---|---|']
    for run in m['runs']:
        cols=[]
        for rid in ('r1','r2'):
            rr=run['robots'][rid];parts=[]
            for key in ('first_shadow_postapproach_gate_reject','first_shadow_geometry_reject'):
                d=rr[key];parts.append(f"{d['sim_s']:.3f} {d['phase']}" if d else '미검출')
            cols.append(' / '.join(parts))
        lines.append(f"| `{run['id']}` | {'통과' if run['static_plan_admission']=='pass' else '범위 밖'} | {' | '.join(cols)} |")
    (r.OUT/'m2-runs.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__': main()
