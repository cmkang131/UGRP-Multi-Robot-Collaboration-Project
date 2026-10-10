"""Run after the whole frozen batch ends; hash raw and check old-heading prefix."""
from pathlib import Path
import hashlib,json,sys

def read(p):return json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def verify(batch,smoke,recovery=None):
    jobs=read(batch/'batch-status.json')
    if len(jobs)!=24 or any(j['status'] in ('RUNNING','QUEUED') for j in jobs):raise ValueError('WAIT_ALL_24_TERMINAL')
    if recovery and any(j['status'] in ('RUNNING','QUEUED') for j in read(recovery/'batch-status.json')):raise ValueError('WAIT_RECOVERY_TERMINAL')
    count=total=0;missing=[];bad=[]
    for root in (batch,smoke,*([recovery] if recovery else [])):
        for manifest in root.rglob('artifacts.sha256.json'):
            for name,digest in read(manifest).items():
                path=manifest.parent/name
                if not path.exists():missing.append(str(path));continue
                count+=1;total+=path.stat().st_size
                if sha(path)!=digest:bad.append(str(path))
    prefixes=[];oldroot=batch.parent.parent/'egomap64-batch/data'
    for j in jobs:
        if j['heading_stability']!='off':continue
        current=Path(j['output']);old=oldroot/f"stage-{j['seed']}-{j['profile']}"
        if not (current/'own-controller.jsonl').exists() or not (old/'own-controller.jsonl').exists():continue
        start=read(old/'result.json')['start_sim_s']
        a=[line for line in (old/'own-controller.jsonl').read_text().splitlines() if start<=json.loads(line)['t']<start+60]
        b=[line for line in (current/'own-controller.jsonl').read_text().splitlines() if start<=json.loads(line)['t']<start+60]
        prefixes.append(dict(seed=j['seed'],profile=j['profile'],old_frames=len(a),new_frames=len(b),identical=sum(x==y for x,y in zip(a,b)),all_identical=a==b))
    result=dict(server='oracle-x86',files_verified=count,total_bytes=total,missing=missing,mismatches=bad,
        old_heading_first60s_prefix=prefixes,controller_source_sha=read(batch/'batch-plan.json')['source_sha'])
    (batch/'server-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if missing or bad:raise ValueError('SERVER_ARTIFACT_HASH_MISMATCH')
if __name__=='__main__':verify(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]) if len(sys.argv)>3 else None)
