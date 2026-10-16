"""gcp2 terminal equality evidence: reloc20 R3 vs reloc21 R1 off."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess

R=Path('/home/ugrp/ugrp-sim/runs')
def read(p):return p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'])
def obj(p):return json.loads(read(p))


def main():
    assert platform.node().startswith('ugrp-sim-gcp2') and (R/'reloc21-round1/DONE').exists()
    old=obj(R/'reloc20-round3/queue.json')['runs'];new=obj(R/'reloc21-round1/queue.json')['runs'];records=[]
    for task in new:
        if task['kind']=='carry' and task['condition']!='baseline':continue
        prior=next(x for x in old if x['seed']==task['seed'] and (x['kind']!='carry' or x['condition']=='candidate'))
        a=Path(prior['raw']);b=Path(task['raw']);ar=obj(a/'result.json');br=obj(b/'result.json')
        files=['teacher-commands.jsonl'] if task['kind']=='carry' else [f'robots/r{i}/commands.jsonl' for i in (1,2,3)]
        commands=[]
        for name in files:
            x,y=read(a/name),read(b/name);commands.append(dict(file=name,before_decoded_sha256=hashlib.sha256(x).hexdigest(),after_decoded_sha256=hashlib.sha256(y).hexdigest(),before_rows=len(x.splitlines()),after_rows=len(y.splitlines()),equal=x==y))
        if task['kind']=='carry':
            am=obj(a/'playback/manifest.json')['frames'];bm=obj(b/'playback/manifest.json')['frames'];images=[]
            for x,y in zip(am,bm):
                for camera in ('overview','r1','r2','r3'):
                    pa=a/'playback'/x['files'][camera];pb=b/'playback'/y['files'][camera]
                    images.append(x['t']==y['t'] and hashlib.sha256(pa.read_bytes()).digest()==hashlib.sha256(pb.read_bytes()).digest())
            image_result=dict(compared=len(images),equal=sum(images),before_frames=len(am),after_frames=len(bm),all_equal=all(images) and len(am)==len(bm))
        else:
            am=obj(a/'artifacts.sha256.json');bm=obj(b/'artifacts.sha256.json')
            images=[p for p in am if p.endswith(('.jpg','.jpeg','.png')) and p.startswith('robots/')]
            def h(v):return v if isinstance(v,str) else v['sha256']
            match=sum(p in bm and h(am[p])==h(bm[p]) for p in images)
            image_result=dict(compared=len(images),equal=match,all_equal=bool(images) and match==len(images),scope='both raw manifests independently verified by round analyzer')
        records.append(dict(before=prior['name'],after=task['name'],raw_before=str(a),raw_after=str(b),
            status_before=ar['status'],status_after=br['status'],
            sim_before=ar.get('sim_s',ar.get('elapsed_sim_s')),sim_after=br.get('sim_s',br.get('elapsed_sim_s')),
            commands=commands,images=image_result))
    report=dict(reproduce=f'python {__file__}',script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),runs=records,
        scope='frozen gcp2 runtime only; off-default control trace/frame equality is distinct from candidate success')
    (R/'reloc21-round1/off-replay.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
