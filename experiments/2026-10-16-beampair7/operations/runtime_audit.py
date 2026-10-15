"""GCP finalized raw input/recording checks, without physics or control imports."""
from pathlib import Path
from collections import Counter
import json,sys,subprocess,hashlib
ROOT=Path('/home/ugrp/ugrp-sim');OPS=ROOT/'ops-reviews/beampair7'
cfg=json.loads(Path(sys.argv[1]).read_bytes());src=ROOT/'src'/cfg['source_sha'];sys.path.insert(0,str(src))
from scripts.audit_beampair1 import read,read_bytes
batch=OPS/cfg.get('batch_name',f'beampair-{cfg["stage"]}-{cfg["source_sha"][:8]}');done=read(batch/'DONE.json')
runs=[]
for e in done['completed']:
 raw=Path(e['raw']);r=read(raw/'result.json');a=read(raw.parent/'adapter/beampair1-result.json')
 labels={rid:[json.loads(x) for x in read_bytes(raw/f'teacher-{rid}.jsonl')[0].splitlines() if x] for rid in ('r1','r2')}
 first=[x for ls in labels.values() for x in ls[:300]]
 computes=[x.get('planning_compute') or {} for x in first]
 tail=read(raw.parent/'adapter/failure-tail/manifest.json')
 anchors=[p for t in r.get('teachers',{}).values() for p in t.get('peer_yield_connector_log',[])]
 quality=read(raw/'scene-quality.json')
 runs.append(dict(seed=e['seed'],category=e['category'],raw=str(raw),adapter_sha=a['source_sha'],dependency_sha=a['dependency_sha'],peer_yield=a.get('peer_yield'),input_audit=r.get('input_audit'),held_world_reads=a['held_world_reads'],hidden_measurement_ticks=a['hidden_measurement_ticks'],first_close_t=a['first_close_t'],weld=r.get('weld'),training_rgb=a['training_rgb'],student_execution=r.get('student_execution'),self_pose_source=r.get('self_pose_source'),first30_command_rows=len(first),first30_coverage='full300ticks' if all(len(v)>=300 for v in labels.values()) else 'success_before30SIM',planning_budget_kinds=dict(Counter(x.get('budget_kind','missing') for x in computes)),wall_planning_budget_N=sum(x.get('max_wall_s') is not None for x in computes),planning_budget_exhausted_N=sum(bool(x.get('budget_exhausted')) for x in computes),recording=dict(hz=tail['hz'],window_sim_s=tail['window_sim_s'],captured_N=tail['total_captured_frames'],stored_bytes=tail['stored_bytes'],peak_buffer_bytes=tail['peak_buffer_bytes'],controller_input=tail['controller_input']),anchor_queries=len(anchors),anchor_grid_max_N=max((x['grid_population_N'] for x in anchors),default=0),anchor_checked_N=sum(x['checked_N'] for x in anchors),native_continuation_found_N=sum(x['rest_path_found'] for x in anchors),scene_profile=quality['scene_profile'],camera_quality=quality['camera_quality'],all_min_gl_linear=all(t['min']==9729 for c in quality['contexts'].values() for t in c['textures']),scene_xml_sha256=hashlib.sha256((raw/'scene.xml').read_bytes()).hexdigest()))
report=dict(source_sha=cfg['source_sha'],source_clean=not bool(subprocess.check_output(['git','status','--porcelain'],cwd=src)),controller_sha256={p:hashlib.sha256((src/p).read_bytes()).hexdigest() for p in ('harness/beampair_peer_yield.py','scripts/run_beampair1.py','harness/beampair_approach.py','harness/grasp_act_peer_rendezvous.py','sim/gatesv5_scene.py')},runs=runs,source_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scope='Saved own-issued labels and finalized input/recording ledgers only. New anchor bound<=961 lattice points plus at most two original40000-node A* calls; node expansions not independently counted. No replayed physics or model calls.')
report['all_input_clean']=all(x['input_audit']['enabled'] and all(x['input_audit'].get(k)==0 for k in ('invisible_measurements','held_world_reads')) and x['held_world_reads']==0 for x in runs)
report['all_weld_training_student_off']=all(x['weld'] in (False,'off') and not x['training_rgb'] and not x['student_execution'] for x in runs)
report['all_recording_10hz_last10']=all(x['recording']['hz']==10 and x['recording']['window_sim_s']==10 and x['recording']['captured_N']>0 and x['recording']['controller_input'] is False for x in runs)
report['all_planning_checks']=all(set(x['planning_budget_kinds'])=={'checks'} and x['wall_planning_budget_N']==0 for x in runs)
report['all_scene_bound']=all(x['scene_profile']=='walls_floor_contrast_v5_indigo110_s80' and x['camera_quality']=='no_mip_v1' and x['all_min_gl_linear'] for x in runs)
(OPS/f'runtime-audit-{cfg["stage"]}-{cfg["round"]}.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if isinstance(v,bool)}))
