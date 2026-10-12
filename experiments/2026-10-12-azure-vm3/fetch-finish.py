"""Finite Mac fetch-lite completion and VM3 retrieval; no controller feedback."""
from pathlib import Path
import subprocess,json,time,sys,os,signal,hashlib
out=Path(__file__).parent;names=[f'e2e15-{g}-s{s}' for s in range(61001,61004) for g in ('a','b')]
deadline=time.time()+28000;done={};notified=set()
def ssh(c):return subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','azure3',c],capture_output=True,text=True,timeout=90)
while len(done)<len(names) and time.time()<deadline:
 for name in names:
  if name in done:continue
  p=ssh(f'cat ~/ugrp-sim/e2e15-finished/{name}.json')
  if p.returncode:continue
  arc=json.loads(p.stdout);assert arc['proof']['verified'];(out/(name+'-archive.json')).write_text(p.stdout)
  q=ssh(f'cat ~/ugrp-sim/runs/{name}/LITE_IMAGE_EXCLUSIONS.txt');q.check_returncode()
  ep=out/(name+'-exclusions.txt');ep.write_text('\n'.join(x+y for x in q.stdout.splitlines() if x for y in ('','.zst'))+'\n')
  dest=out/'fetch-lite'/name;dest.mkdir(parents=True,exist_ok=True)
  flags=['--exclude='+x for x in ('*.png','*.jpg','*.jpeg','*.mp4','*.gif','*.npz','*.npy','/raw/eval_only/','/raw/robots/*/ownmap.jsonl*','/raw/*-ownmap-final.json*')]+['--exclude-from='+str(ep)]
  subprocess.run(['rsync','-aL',*flags,f'azure3:~/ugrp-sim/runs/{name}/',str(dest)+'/'],check=True,timeout=600)
  diff=subprocess.check_output(['rsync','-ancL','--out-format=%n',*flags,f'azure3:~/ugrp-sim/runs/{name}/',str(dest)+'/'],text=True,timeout=180)
  assert not diff.strip(),diff
  def obj(p):return json.loads(p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst']))
  final=obj(dest/'final-health.json');result=final['result']
  record=dict(run=name,path=str(dest),checksum_verified=True,files=sum(p.is_file() for p in dest.rglob('*')),bytes=sum(p.stat().st_size for p in dest.rglob('*') if p.is_file()),finished_unix=time.time(),archive=arc,final_health=final)
  (out/(name+'-fetch.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');done[name]=record
  print(json.dumps(dict(run=name,verified=True,E2E_success=result.get('E2E_success'))),flush=True)
  if False:
   body=out/(name+'-success.md');body.write_text(f'14차 첫 종료조건 3개 동시 달성: `{name}` (source `{result["source_sha"]}`).\nLLM·자기 지도·시작→끝 운반 모두 true; SIM {result["sim_s"]:.2f}초, wall {result["wall_s"]:.1f}초.\nARM 원본 전체 해시 검증 및 Mac 경량 회수 완료; 나머지 짝 비교는 고정 구성으로 계속합니다.\n')
   subprocess.run(['gh','pr','comment','446','--body-file',str(body)],check=True);notified.add(name)
 if len(done)<len(names):time.sleep(15)
if len(done)!=len(names):raise SystemExit('INCOMPLETE_RETRIEVAL; guest eight-hour guard remains active')
(out/'retrieval.json').write_text(json.dumps({n:{k:v for k,v in x.items() if k!='final_health'} for n,x in done.items()},indent=2)+'\n')
# All archive receipts count every file and full hash; an independent ARM verifier is run by the caller.
(out/'ALL_RETRIEVED.json').write_text(json.dumps(dict(unix=time.time(),n=len(done),N=len(names))))
