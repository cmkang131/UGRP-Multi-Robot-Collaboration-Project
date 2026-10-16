"""gcp2 evaluator-only route coverage and issued pulse distributions."""
import hashlib,json,math,platform,subprocess
from pathlib import Path
import numpy as np
R=Path('/home/ugrp/ugrp-sim/runs')
def read(p):return p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'])
def main():
 assert platform.node().startswith('ugrp-sim-gcp2')
 records=[]
 for n in (1,2,3):
  for task in json.loads(read(R/f'reloc20-round{n}/queue.json'))['runs']:
   if task['kind']!='carry':continue
   raw=Path(task['raw']);result=json.loads(read(raw/'result.json'))
   if result['status']=='HOST_ERROR':continue
   c=[json.loads(x) for x in read(raw/'teacher-commands.jsonl').splitlines()]
   by={round(x['t'],5):x for x in [json.loads(s) for s in read(raw/'eval-only.jsonl').splitlines()]}
   pairs=[(x,by[round(x['t'],5)]) for x in c if round(x['t'],5) in by and x.get('phase_before',x['phase'])=='carry_to_zone']
   xy=np.array([e['base_xyz'][:2] for x,e in pairs]);pulse=[]
   for x,e in pairs:
    w=x['command']['wheels'];d=x['command']['duration_s']
    if abs(w[0])>1e-9 and abs(w[0]+w[1])+abs(w[0]-w[2])+abs(w[1]-w[3])<1e-9 and max(d)-min(d)<1e-9:pulse.append(d[0]*1000)
   records.append(dict(run=task['name'],raw=str(raw),source_sha=task['source_sha'],carry_frames=len(pairs),
     carry_range_sim=[pairs[0][0]['t'],pairs[-1][0]['t']] if pairs else None,
     max_displacement_from_first_carry_m=float(np.linalg.norm(xy-xy[0],axis=1).max()) if pairs else None,
     issued_pure_turn_pulse_ms=dict(N=len(pulse),**{str(p):float(np.percentile(pulse,p)) for p in (0,50,95,100)}) if pulse else dict(N=0),
     command_decoded_sha256=hashlib.sha256(read(raw/'teacher-commands.jsonl')).hexdigest(),
     evaluation_decoded_sha256=hashlib.sha256(read(raw/'eval-only.jsonl')).hexdigest()))
 p=R/'reloc20-delivery/coverage.json';p.write_text(json.dumps(dict(scope='evaluator-only coverage; max displacement is not path completion or independent odometry accuracy',analysis_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),runs=records),indent=2)+'\n');print(json.dumps(records))
if __name__=='__main__':main()
