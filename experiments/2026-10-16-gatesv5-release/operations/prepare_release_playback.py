"""gcp2 evaluation-only replay proxy from original recorder snapshots."""
from pathlib import Path
import bisect,hashlib,json,os,subprocess,sys
R=Path('/home/ugrp/ugrp-sim');OPS=R/'ops-reviews/gatesv5'
def rawbytes(p):
 if p.exists():return p.read_bytes()
 return subprocess.check_output(['zstd','-qdc',str(p)+'.zst'])
def read(p):return json.loads(rawbytes(p))
def prepare(runname):
 original=R/'runs'/runname/'raw';plan=read(original/'plan.json');saved=[json.loads(x) for x in rawbytes(original/'evaluator-snapshots.jsonl').splitlines()];unique={round(x['t'],7):x for x in saved};saved=sorted(unique.values(),key=lambda x:x['t'])
 ev=[json.loads(x) for x in rawbytes(original/'eval-only.jsonl').splitlines()];ev=[x for x in ev if 'phase' in x and 'robots' in x];times=[x['t'] for x in ev];release_origin=times[0]-.1
 target=OPS/'derived-release-replay'/runname/'raw';target.mkdir(parents=True,exist_ok=False)
 (target/'scene.xml').symlink_to(original/'scene.xml');camera=read(original/'camera-runtime-evaluator.json');cal={}
 for rid in plan['roles']:cal[rid]=camera[rid+'__robot_cam']
 (target/'camera-runtime.json').write_text(json.dumps(dict(cameras=cal)))
 plan.setdefault('assignment_source','original release24 authored plan');(target/'plan.json').write_text(json.dumps(plan))
 data=[];labels={rid:[] for rid in plan['roles']}
 for x in saved:
  row={**x['truth'],'joints':x['qpos']};data.append(row);idx=bisect.bisect_right(times,x['t']+1e-7)-1;phase=ev[idx]['phase'] if idx>=0 else 'prefix'
  for rid in labels:labels[rid].append(dict(teacher_phase=phase))
 for name,rows in [('eval-only',data),*((f'teacher-{rid}',v) for rid,v in labels.items())]:
  p=target/(name+'.jsonl');p.write_text(''.join(json.dumps(x)+'\n' for x in rows));before=hashlib.sha256(p.read_bytes()).hexdigest();subprocess.run(['zstd','-q','-f','-k',str(p)],check=True);assert hashlib.sha256(subprocess.check_output(['zstd','-qdc',str(p)+'.zst'])).hexdigest()==before;p.unlink()
 ring=target.parent/'adapter/failure-tail';ring.mkdir(parents=True);frames=[]
 for rid in plan['roles']:
  for p in sorted((original/'failure-rgb'/rid).glob('*.jpg')):
   dest=ring/rid/p.name;dest.parent.mkdir(exist_ok=True);dest.symlink_to(p);frames.append(dict(t=release_origin+float(p.stem),robot=rid,path=str(dest.relative_to(ring)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
 (ring/'manifest.json').write_text(json.dumps(dict(frames=frames)))
 provenance=dict(original_raw=str(original),saved_rows=len(saved),release_origin_world_t=release_origin,original_native_failure_tail_frames=len(frames),max_snapshot_gap_sim_s=max(b['t']-a['t'] for a,b in zip(saved,saved[1:])),scope='evaluation-only derived proxy. qpos and camera calibration copied from original evaluator recording; phase labels from original eval-only global phase. No controller/physics rerun; any missing temporal samples remain missing.',sources={str(original/n):hashlib.sha256(rawbytes(original/n)).hexdigest() for n in ['scene.xml','plan.json','camera-runtime-evaluator.json','eval-only.jsonl','evaluator-snapshots.jsonl']})
 (target.parent/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
 cfg=read(OPS/'release-gate-config.json');src=R/'src'/cfg['source_sha'];beam_src=R/'src/0b5faa4cfdc52f87df0fdf49e7b254bafc5b8bc0';log=(OPS/(runname+'-playback.log')).open('w');env={**os.environ,'MUJOCO_GL':'osmesa','PYTHONPATH':str(beam_src),'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','LP_NUM_THREADS':'1'}
 out=OPS/'playback'/('release-'+runname);p=subprocess.Popen([str(R/'ugrp/.venv-sim/bin/python'),str(OPS/'review_beampair_gatesv5_fisheye.py'),'--raw',str(target),'--out',str(out)],cwd=src,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);print(json.dumps(dict(run=runname,proxy=str(target),out=str(out),PID=p.pid,provenance=provenance)))
if __name__=='__main__':prepare(sys.argv[1])
