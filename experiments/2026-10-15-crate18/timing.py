"""First30 SIM timing from own RGB mtimes and corresponding issued-label clocks."""
import bisect,json,pathlib,statistics,subprocess,sys
folder=pathlib.Path(sys.argv[1]);root=pathlib.Path(__file__).resolve().parents[2]
plans=json.loads((folder/'plan.json').read_text())
code='''import pathlib,json
b=pathlib.Path.home()/'ugrp-sim/runs';out={}
for name in NAMES:
 p=b/name/'raw/eval-own/r1';out[name]=[dict(name=f.name,mtime=f.stat().st_mtime) for f in sorted(p.glob('*.jpg'))]
print(json.dumps(out))
'''.replace('NAMES',repr([r['name'] for r in plans]))
r=subprocess.run(['ssh','-o','BatchMode=yes','gcp1','python3 -'],input=code,text=True,capture_output=True,check=True);meta=json.loads(r.stdout);out=[]
for p in plans:
 raw=root/'outputs/gcp1-runs'/p['name']/'raw/teacher-r1.jsonl'
 b=subprocess.check_output(['zstd','-dc',str(raw)+'.zst']) if not raw.exists() else raw.read_bytes()
 rows=[json.loads(l) for l in b.splitlines()];gr=[x for x in rows if 'applied_command' in x];rr=[x for x in rows if x['skill']=='release'];origin=gr[0]['t'];times=[]
 for f in meta[p['name']]:
  i=int(f['name'].split('-')[0]);seq=rr if '-release-' in f['name'] else gr
  if i<len(seq):times.append((seq[i]['t']-origin,f['mtime']))
 times.sort();base=times[0][1];i=bisect.bisect_left([v[0] for v in times],30.)
 if i<len(times):
  a,b=times[max(0,i-1)],times[i];mtime=a[1]+(30-a[0])/(b[0]-a[0])*(b[1]-a[1]);speed=(mtime-base)/30
 else:speed=None
 out.append(dict(run=p['name'],first30=speed,method='own RGB mtime matched to grasp/release label clocks; interpolation at30 SIMs; initialization excluded',samples=times))
(folder/'speed.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(dict(N=sum(r['first30'] is not None for r in out),median=statistics.median(r['first30'] for r in out if r['first30'] is not None))))
