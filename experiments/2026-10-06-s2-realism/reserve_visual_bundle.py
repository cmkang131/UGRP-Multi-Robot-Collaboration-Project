import subprocess,json,re,pathlib
root=pathlib.Path('/Users/changmin/projects/ugrp-wt/drive-friction')
def cmd(a):
 r=subprocess.run(a,cwd=root,text=True,capture_output=True);assert r.returncode in (0,1),r.stderr;return r.stdout
prs=json.loads(cmd(['gh','pr','list','--state','open','--json','number,headRefName']))
refs=['origin/main']+['origin/'+p['headRefName'] for p in prs];rows=[]
for ref in refs:
 ids=cmd(['git','grep','-h','-E','(RUNNABLE_ID|BUNDLE_ID|execution_bundle_id).*v[0-9]+',ref,'--','harness','configs'])
 nums=[int(x) for x in re.findall(r'(?:zone[-_a-z0-9]*-v|RUNNABLE_ID[^\n]*?v)(\d+)',ids)]
 wf=cmd(['git','grep','-h','-E','"version": "7\.[0-9]+\.',ref,'--','configs'])
 seed=subprocess.run(['git','grep','-n','-E','("seed"[[:space:]]*:[[:space:]]*1047([^0-9]|$)|s1047([^0-9]|$))',ref,'--','harness','configs','experiments'],cwd=root,capture_output=True,text=True)
 rows.append(dict(ref=ref,sha=cmd(['git','rev-parse',ref]).strip(),max_bundle=max(nums),workflow_versions=sorted(set(re.findall(r'7\.\d+\.\d+',wf))),seed1047_hits=seed.stdout.splitlines()))
assert max(x['max_bundle'] for x in rows)==122
assert not any(x['seed1047_hits'] for x in rows)
raw=list(pathlib.Path('/Users/changmin/projects/ugrp/outputs').glob('*s1047*'));assert not raw
out=dict(schema='ugrp.reservation_scan.v1',refs=rows,selected_bundle='zone-s2-realism-v123',selected_workflow='7.16.0',selected_seed=1047,raw_matches=[])
(root/'experiments/2026-10-06-s2-realism/reservation-scan-v123.json').write_text(json.dumps(out,indent=2)+'\n')
print([(r['ref'],r['max_bundle']) for r in rows])
