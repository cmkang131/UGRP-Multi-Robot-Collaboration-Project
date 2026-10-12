"""Finite verified archival, fetch-lite, VM4 deallocation and PR450 record."""
from pathlib import Path
import json,subprocess,time,sys,shlex
out=Path(__file__).resolve().parent;repo=out.parents[1]
sub='88b7ee7f-f2f3-4a0d-a0ce-cf7306943676';vm='ugrp-sim-azure4'
names=[f'e2e-usstall-{g}-s{s}' for s in range(61001,61004) for g in ('a','b')]
deadline=1791787441+28200
while time.time()<deadline:
 if (out/'ALL_RETRIEVED.json').exists():break
 time.sleep(15)
else:raise SystemExit('RETRIEVAL_INCOMPLETE: VM-local 8-hour cost guard remains active')
code='''from pathlib import Path
import json,sys,hashlib
p=json.load(sys.stdin);root=Path(p['native_verification']['native_arm_path']);n=0
assert root.name.startswith('native-e2e-usstall-')
for name,expected in p['inventory'].items():
 f=root/name
 with f.open('rb') as s:h=hashlib.file_digest(s,'sha256').hexdigest()
 assert f.stat().st_size==expected['bytes'] and h==expected['sha256'],name
 n+=1
print(json.dumps(dict(path=str(root),files=n,hash_matches=n)))
'''
checks=[]
for name in names:
 proof=json.loads((out/(name+'-archive.json')).read_text())['proof'];assert proof['verified']
 r=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','oracle-codex','python3 -c '+shlex.quote(code)],input=json.dumps(proof),text=True,capture_output=True,check=True,timeout=600)
 checks.append(json.loads(r.stdout));print(name,'independent ARM hash match',flush=True)
(out/'arm-all-verified.json').write_text(json.dumps(checks,indent=2)+'\n')
# Record final guest state before the explicitly authorized deallocation.
p=subprocess.run(['ssh','azure4','python3 -'],input=(out/'poll-remote.py').read_text(),capture_output=True,text=True,check=True,timeout=120)
(out/'live.json').write_text(p.stdout)
d=json.loads(p.stdout);assert len(d['runs'])==6 and all(r['exit'] is not None and r['archive'] for r in d['runs'])
subprocess.run(['az','vm','deallocate','--subscription',sub,'-g','UGRP-SIM-RG','-n',vm,'--only-show-errors'],check=True,timeout=600)
r=subprocess.run(['az','vm','get-instance-view','--subscription',sub,'-g','UGRP-SIM-RG','-n',vm,'--query','instanceView.statuses','-o','json','--only-show-errors'],text=True,capture_output=True,check=True)
assert any(s['code']=='PowerState/deallocated' for s in json.loads(r.stdout))
(out/'deallocated.json').write_text(r.stdout)
subprocess.run([sys.executable,str(out/'sync-summary.py')],check=True)
wt=Path('/Users/changmin/projects/ugrp-wt/e2e-usstall');rel='experiments/2026-10-12-e2e-usstall/run-summary.json'
assert subprocess.check_output(['git','-C',str(wt),'branch','--show-current'],text=True).strip()=='codex/e2e-usstall'
subprocess.run(['git','-C',str(wt),'add','--',rel],check=True)
subprocess.run(['git','-C',str(wt),'commit','--only','-m','Record completed E2E16 VM4 paired results and verified archival','--',rel],check=True)
subprocess.run(['git','-C',str(wt),'push','origin','codex/e2e-usstall'],check=True)
x=json.loads((out/'summary.json').read_text());comment=out/'completion-comment.md'
comment.write_text(f"16차 VM4 완료: {x['exited']}/6 EXIT, 종료조건3개 {x['three_condition_success']}/6. LLM/지도/운반 {x['condition_counts']}.\nZUPT 적용 {x['zupt_applied']}회, 실행 오류 {x['execution_errors']}회. 모든 원본 ARM 독립 전체 SHA-256 확인·Mac 경량 회수 완료; VM4 deallocated 재조회.\n근거: experiments/2026-10-12-e2e-usstall/run-summary.json.\n")
subprocess.run(['gh','pr','comment','450','--body-file',str(comment)],cwd=repo,check=True)
for name in ('relay','watch','fetch-finish'):
 subprocess.run([sys.executable,'scripts/ugrp_session.py','stop','azure4-e2e16-'+name],cwd=repo,check=False)
(out/'COMPLETE.json').write_text(json.dumps(dict(unix=time.time(),status='COMPLETE',vm='deallocated',runs=6))+'\n')
