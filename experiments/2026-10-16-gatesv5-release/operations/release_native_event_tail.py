"""Review exact original 10 SIM seconds before the release failure event."""
from pathlib import Path
import json,subprocess,os
R=Path('/home/ugrp/ugrp-sim');OPS=R/'ops-reviews/gatesv5';run='gv5-release-gate-current_A-110633-a41781dd-retry1'
original=OPS/'derived-release-replay'/run;target=OPS/'derived-release-event-tail'/run;raw=target/'raw';raw.mkdir(parents=True,exist_ok=False)
def lines(p):return [json.loads(x) for x in subprocess.check_output(['zstd','-qdc',str(p)+'.zst']).splitlines()]
ring=json.loads((original/'adapter/failure-tail/manifest.json').read_text());lo=min(x['t'] for x in ring['frames']);hi=max(x['t'] for x in ring['frames'])
rows=lines(original/'raw/eval-only.jsonl');indices=[i for i,x in enumerate(rows) if lo-1e-6<=x['t']<=hi+1e-6]
for name in ['scene.xml','camera-runtime.json','plan.json']:(raw/name).symlink_to(original/'raw'/name)
for name in ['eval-only','teacher-r1','teacher-r2']:
 data=rows if name=='eval-only' else lines(original/'raw'/(name+'.jsonl'))
 (raw/(name+'.jsonl')).write_text(''.join(json.dumps(data[i])+'\n' for i in indices))
(target/'adapter').symlink_to(original/'adapter',target_is_directory=True)
out=OPS/'playback/release-failure-event-native-tail'
env={**os.environ,'MUJOCO_GL':'osmesa','PYTHONPATH':str(R/'src/0b5faa4cfdc52f87df0fdf49e7b254bafc5b8bc0'),'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','LP_NUM_THREADS':'1'}
subprocess.run([str(R/'ugrp/.venv-sim/bin/python'),str(OPS/'review_beampair_gatesv5_fisheye.py'),'--raw',str(raw),'--out',str(out)],cwd=R/'src/a41781dd122b1e20b8eec7e43c553e779e6cfc30',env=env,check=True)
info=dict(original_run=run,native_world_t=[lo,hi],snapshots=len(indices),native_frames=len(ring['frames']),scope='Exact native failure-event ring, excluding subsequent 2.4SIMs evaluator settling. Labels in this clip are relative to ring start. Overview evaluator-only; both own images are original native RGB.',reproduce=str(Path(__file__).resolve()))
(out/'event-tail-provenance.json').write_text(json.dumps(info,indent=2)+'\n');print(json.dumps(info))
