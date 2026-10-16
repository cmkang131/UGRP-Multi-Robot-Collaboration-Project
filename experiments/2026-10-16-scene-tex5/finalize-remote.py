"""Gather verified finite static evidence on gcp2; no renderer, no source edits."""
from pathlib import Path
import ast,datetime,hashlib,json,platform,subprocess
from collections import Counter
from scripts.summarize_scene_tex3 import read,write,sha

base=Path('/home/ugrp/ugrp-sim/runs')
out=base/'scenetex5-final-v2'
assert platform.node().startswith('ugrp-sim-gcp2')
assert not out.exists()
out.mkdir()
rounds=[]
for n,c in [(1,'scenetex5-r1-colour-audit'),(2,'scenetex5-r2-colour-audit-b'),(3,'scenetex5-r3-colour-audit')]:
    p=base/f'scenetex5-r{n}-analysis'
    s=read(p/'summary.json');col=read(base/c/'summary.json')
    extra={(r['material'],r['quality']):r for r in col['reports']}
    candidates=[]
    for r in s['reports']:
        if not r['material'].startswith('walls_floor_contrast_v5_'):continue
        x=extra[(r['material'],r['quality'])]
        def d(v):return {q:v[q] for q in ('median','p10','p95')}
        enc={}
        for e,v in r['encodings'].items():
            enc[e]={'box_dark_beam_equal':v['detector_equal'],'extended_existing_equal':x['equal'][e],
                'columns':d(v['boundary_columns']['candidate']),'v1_columns':d(v['boundary_columns']['v1']),
                'error_px':d(v['boundary_error_px']['candidate']),'v1_error_px':d(v['boundary_error_px']['v1']),
                'floor_features_pass':all(vv['pass'] for vv in v['floor_features'].values()),
                'floor_matches_pass':all(vv['pass'] for vv in v['floor_matches'].values()),
                'floor_orb20':d(v['floor_features']['orb20']['candidate']),'v1_floor_orb20':d(v['floor_features']['orb20']['v1']),
                'floor_match20':d(v['floor_matches']['floor20']['candidate']),'v1_floor_match20':d(v['floor_matches']['floor20']['v1']),
                'LK':{k:{'candidate':d(vv['candidate']),'v1':d(vv['v1']),'pass':vv['pass']} for k,vv in v['LK'].items()},
                'iou':{k:d(vv) for k,vv in v['iou'].items()},
                'delta_L':d(v['colour_separation']['delta_L']),'delta_E76_opencv8':d(v['colour_separation']['delta_E76_opencv8']),
                'wall_range_new_intrusion_poses':v['wall_range_new_intrusion_poses'],
                'drive_floor_orb20':d(v['drive_floor_orb20']),'false_columns':v['false_columns'],'v1_false_columns':v['v1_false_columns']}
        gates={**r['gates'],'extended_existing_colour_outputs':x['pass']}
        # This is a distribution admission of a candidate's whole 88-pose set.
        # Exact semantic changed cases are rejected individually first.
        alive=88;stages=[]
        merged_changes=set()
        for e in r['encodings']:
            merged_changes|={v['case'] for v in r['encodings'][e]['semantic_changes']}
            merged_changes|={v['case'] for v in x['changes'][e]}
        checks=[('same88_pose_physics_camera',r['gates']['same88_pose_physics_camera']),
                ('existing_colour_semantic_counts',len(merged_changes)==0),
                ('boundary_distribution',r['gates']['boundary_distribution_all_encodings']),
                ('floor_feature_matching_distribution',r['gates']['floor_feature_matching_distribution_all_encodings']),
                ('LK_distribution',r['gates']['LK_distribution_all_encodings'])]
        for stage,ok in checks:
            before=alive
            if stage=='existing_colour_semantic_counts':alive=max(0,alive-len(merged_changes))
            elif not ok:alive=0
            stages.append({'stage':stage,'input_n':before,'cumulative_pass_n':alive,'rejected_n':before-alive,'independent_pass':bool(ok),
                'category':stage.upper(),'blocking_object':'wall/floor material, RGB occlusion or existing colour extraction','minimum_gap_m':None,
                'minimum_gap_reason':'static image distribution, not a physical clearance gate',
                'reason':'requested candidate-level distribution comparison; exact semantic changes listed' if not ok else 'passed',
                'changed_cases':sorted(merged_changes) if stage=='existing_colour_semantic_counts' else []})
        candidates.append({'material':r['material'],'quality':r['quality'],'ready':all(gates.values()),'gates':gates,'encodings':enc,'stages':stages,
            'wall_occluded_scene_limit':r['wall_occluded_scene_limit']})
    rounds.append({'round':n,'analysis':str(p),'analysis_summary_sha256':sha(p/'summary.json.zst'),'extended_colour_analysis':str(base/c),
        'analysis_source_sha256':s['analysis_sha256'],'sources':s['sources'],'candidates':candidates})
rawnames=['scenetex5-r1-v1-native','scenetex5-r1-v1-no_mip']+[f'scenetex5-r1b-violet{v}' for v in (150,175,195)]+[
    'scenetex5-r2-indigo100','scenetex5-r2-indigo85','scenetex5-r2-indigo100_flat','scenetex5-r3-indigo110_s80','scenetex5-r3-indigo125_s65']
failed=[f'scenetex5-r1-violet{v}' for v in (150,175,195)]
reference={r['map']:r for r in read(base/'scenetex5-r1-v1-native/models.json')}
preservation=[];parity=0;model_n=0
(out/'raw-manifests').mkdir()
for name in rawnames+failed:
    root=base/name;s=read(root/'summary.json');h=read(root/'SHA256SUMS.json')
    bad=[f for f,digest in h.items() if not (root/f).is_file() or sha(root/f)!=digest]
    assert not bad,(name,bad)
    current={p.name:sha(p) for p in root.iterdir() if p.is_file()}
    write(out/'raw-manifests'/(name+'.json'),current)
    for m in read(root/'models.json'):
        model_n+=1
        parity+=int((m['physics_sha256'],m['camera_sha256'])==(reference[m['map']]['physics_sha256'],reference[m['map']]['camera_sha256']))
    preservation.append({'root':str(root),'source_sha':s['source_sha'],'status':s['status'],'frames':s['frames'],'verified_original_files':len(h),
        'original_manifest_sha256':sha(root/'SHA256SUMS.json' if (root/'SHA256SUMS.json').exists() else root/'SHA256SUMS.json.zst'),'current_files':len(current),'bytes':sum(p.stat().st_size for p in root.iterdir() if p.is_file()),
        'original_mismatches':bad,'errors':s.get('errors',[]),'cap_end':s.get('cap_end',False)})
write(out/'preservation.json',{'runs':preservation,'raw_frames_complete':sum(v['frames'] for v in preservation if v['status']=='MEASURED'),
    'encoded_RGB_complete':3*sum(v['frames'] for v in preservation if v['status']=='MEASURED'),'physics_camera_parity':{'matched':parity,'models':model_n},
    'original_manifest_mismatches':0,'pooling':'no pooling across scene, detector source or host; raw R1 baseline and R2 indigo100 reused only with hashes',
    'host':'gcp2 n4-highcpu-64','project':'ugrp-sim-b-1014','account':'changmin5781@gmail.com','timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat()})
summary={'schema':'ugrp.scenetex5.delivery.v1','decision':'READY' if any(r['ready'] for r in rounds[-1]['candidates']) else 'NOT_READY',
    'round_budget':{'used':3,'maximum':3},'rounds':rounds,'representative_not_adopted':'walls_floor_contrast_v5_indigo110_s80',
    'render_source_round3':'a68106fd86c314d7c1d10cd321475b0c86c93310','boundary_core_source':'a68106fd86c314d7c1d10cd321475b0c86c93310',
    'shared_binding_source':'63f14fda073c051b454a71877770e2a6654cf5af','shared_binding_check':read(base/'scenetex5-binding/summary.json'),
    'tests':{'passed':56,'seconds':4.23,'scope':'XML/PNG, synthetic boundary, default-off frozen RGB ABI; no Mac renderer or physics'},
    'physics_steps':0,'model_calls':0,'Mac_render':0,'Mac_GUI':0,'cap_end':0,'default':'off','new_runs_submittable':False,
    'scope':'same88-pose exploratory SIM0 camera fixtures plus atan(1/fx) synthetic yaw pair; no motion/localization/ACT/transport/physical success',
    'qualification':'56 boundary/LK camera-qualified,32 HIGH/unknown-load not qualified; colour component counts over88; geometric goal/B checks retain32 unknowns, not negative detections',
    'calibration_scope':'same88 x3 encodings exploratory colour percentiles; no independent holdout; eval masks used only in offline calibration/scoring',
    'work_budget':'96 columns x480rows; finite deterministic two-point model enumeration, <=24*96*95/2 pairs; no wall-clock branch',
    'rejection_table':'/Users/changmin/projects/ugrp-wt/scene-tex2/experiments/2026-10-16-scene-tex5/rejection-table.json',
    'pr':'https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/527'}
write(out/'rounds.json',rounds)
summary['final_candidates']=[{**r,'encodings':{e:{k:v for k,v in x.items() if k!='wall_range_new_intrusion_poses'} for e,x in r['encodings'].items()}} for r in rounds[-1]['candidates']]
summary['rounds']=[{'round':r['round'],'analysis':r['analysis'],'extended_colour_analysis':r['extended_colour_analysis'],'candidates':[{'material':x['material'],'ready':x['ready']} for x in r['candidates']]} for r in rounds]
summary['full_distributions_and_wall_range_counts']='rounds.json (zstd if >64KiB)'
lines=['# scenetex5 누적 관문과 거부표','',
       '같은88자세 분포를 수용하는 후보 관문이다. 색 출력 변화만 자세별로 제거하며, 분포 관문 실패는 남은 후보 세트 전체를 거부한다. 독립 원인은 summary/rounds에 별도로 남긴다.','',
       '| 라운드/후보 | 같은 자세·물리 | 기존 색 출력 | 경계 분포 | 바닥 특징·매칭 | LK |',
       '|---|---:|---:|---:|---:|---:|']
for r in rounds:
    for c in r['candidates']:
        lines.append('| '+str(r['round'])+'/'+c['material'].replace('walls_floor_contrast_v5_','')+' | '+' | '.join(str(x['cumulative_pass_n'])+' (-'+str(x['rejected_n'])+')' for x in c['stages'])+' |')
lines+=['','괄호는 직전 관문 이후 거부 수다. 원본 위치·재현 명령·사유 category/object/minimum_gap(null, 정적 RGB 관문)은 rejection-table.json에 있다.',
        'R3 indigo100은 R2의 동일 해시 RGB를 새 경계 단계로 다시 채점했다. 렌더를 추가하거나 서로 다른 장면/알고리즘의 분모를 합치지 않았다.']
(out/'rejection-table.md').write_text('\n'.join(lines)+'\n')
write(out/'rejection-table.json',{'decision':summary['decision'],'round_budget':summary['round_budget'],'rounds':[
    {'round':r['round'],'analysis':r['analysis'],'extended_colour_analysis':r['extended_colour_analysis'],'sources':r['sources'],
     'candidates':[{'material':x['material'],'quality':x['quality'],'ready':x['ready'],'stages':x['stages'],'independent_gates':x['gates']} for x in r['candidates']]} for r in rounds],
    'raw_sources':preservation,'reproduction':'probe_scene_tex5, score_scene_tex5, audit_scene_tex5_colours; full argv in raw meta/analysis rejection tables',
    'threshold_basis':'user2026-10-16: columns median/p10 >=v1; error median/p95 <=v1; floor and LK median/p10 >=v1; exact old semantic kind/count parity. IoU and HSV intrusions record-only.'})
if not (out/'rejection-table.json').exists():summary['rejection_table']+='.zst'
write(out/'summary.json',summary)
write(out/'RUN_META.json',{'class':'dev','pr':527,'batch':'scenetex5-final','keep':['summary.json','rejection-table.json','preservation.json','raw-manifests'],
    'sha':'63f14fda073c051b454a71877770e2a6654cf5af'})
(out/'EXIT').write_text('0\n')
write(out/'SHA256SUMS.json',{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()})
files=[p for p in out.rglob('*') if p.is_file()]
(out/'retrieval-manifest.json').write_text(json.dumps({'remote_root':str(out),'files':{p.relative_to(out).as_posix():sha(p) for p in files},
    'total_bytes':sum(p.stat().st_size for p in files)},indent=2))
(out/'FETCH_LITE.txt').write_text('\n'.join([p.relative_to(out).as_posix() for p in files]+['retrieval-manifest.json','FETCH_LITE.txt'])+'\n')
print('FINAL',summary['decision'],'raw',summary['round_budget'],'models',parity,model_n,'fetch_bytes',sum(p.stat().st_size for p in files),flush=True)
