"""GCP-only finalized cohort analysis; summary/manifest recovery, no control."""
import hashlib, json, pathlib, subprocess, sys, os
ROOT=pathlib.Path('/home/ugrp/ugrp-sim');OPS=ROOT/'ops-reviews/beampair7'
cfg=json.loads(pathlib.Path(sys.argv[1]).read_bytes());src=ROOT/'src'/cfg['source_sha']
batch=OPS/cfg.get('batch_name',f'beampair-{cfg["stage"]}-{cfg["source_sha"][:8]}')
done=json.loads((batch/'DONE.json').read_bytes())
input_root=OPS/f'input-{cfg["stage"]}-{cfg["round"]}';(input_root/'diagnostic').mkdir(parents=True,exist_ok=True)
host_errors=[]
for i,r in enumerate(done['completed']):
 p=pathlib.Path(r['raw']).parent
 if r['category']=='HOST_ERROR':host_errors.append(r)
 adapter=p/'adapter/beampair1-result.json'
 if not adapter.exists() and not pathlib.Path(str(adapter)+'.zst').exists():continue
 link=input_root/'diagnostic'/f'episode-{i:03d}'
 if not link.exists():link.symlink_to(p,target_is_directory=True)
(input_root/'batch-plan.json').write_text(json.dumps(dict(planned_N=len(cfg['runs']),source_sha=cfg['source_sha'],host='gcp2')))
out=OPS/f'analysis-{cfg["stage"]}-{cfg["round"]}';out.mkdir(exist_ok=True)
command=[str(ROOT/'ugrp/.venv-sim/bin/python'),str(src/'scripts/analyze_beampair1.py'),str(input_root),'--out',str(out)]
subprocess.run(command,cwd=src,check=True,env={**os.environ,"PYTHONPATH":str(src)})
report=json.loads((out/'summary.json').read_bytes())
report.update(HOST_ERROR_N=len(host_errors),host_errors=host_errors,supervisor=done,queue_path=sys.argv[1],queue_sha256=hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
if report['N']!=len(done['completed']):
 report.update(analysis_incomplete=True,unparsed_started_N=len(done['completed'])-report['N'])
quality=[];speeds=[]
for r in done['completed']:
 p=pathlib.Path(r['raw']);q=p/'scene-quality.json'
 if q.exists():
  d=json.loads(q.read_bytes());quality.append(dict(run=p.parent.name,scene_profile=d['scene_profile'],camera_quality=d['camera_quality'],all_min_gl_linear=all(t['min']==9729 for c in d['contexts'].values() for t in c['textures'])))
 f=p/'first30-speed.json'
 if f.exists():speeds.append(dict(seed=r['seed'],**json.loads(f.read_bytes())))
(out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
(out/'runtime-verification.json').write_text(json.dumps(dict(scene=quality,first30=speeds,source_sha=cfg['source_sha'],dependency_sha='26f84d0f0ada1c33473c83cca2d3415ce51bd247'),indent=2)+'\n')
print(json.dumps({k:report.get(k) for k in ('source_sha','planned_N','N','n','unstarted_N','cap_end_N','HOST_ERROR_N','invisible_measurements','held_world_reads','missing_rejection_audit_N')}))
