"""VM-only raw result recount and failed own-RGB montage; no replay/physics.

Run on gcp1. Copy only summary.json, montages and selected failed frames to Mac.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import subprocess


def read(path):
    if path.exists():return path.read_bytes()
    if Path(str(path)+'.gz').exists():return gzip.decompress(Path(str(path)+'.gz').read_bytes())
    if Path(str(path)+'.zst').exists():return subprocess.check_output(['zstd','-q','-dc',str(path)+'.zst'])
    return None


def analyze(root,out):
    from PIL import Image,ImageDraw
    out.mkdir(parents=True,exist_ok=True);rows=[];totals=Counter();artifacts=[]
    for p in sorted(root.glob('diagnostic*/episode-*')):
        raw=p/'raw';data=read(raw/'result.json');d=json.loads(data) if data else {}
        plan=json.loads(read(raw/'plan.json') or b'{}')
        complete=d.get('status')=='complete';success=complete and d.get('physical_success') is True
        reasons=Counter();categories=Counter();blocks=Counter();grids=Counter();budget=Counter();bad_ledgers=0
        for t in d.get('teachers',{}).values():
            for e in t.get('search22_log',[]):
                for c in e.get('candidates',[]):
                    reason=c.get('reason') or 'missing_reason';reasons[reason]+=1
                    category=c.get('rejection_category') or reason;categories[category]+=1
                    if c.get('blocked_object'):blocks[c['blocked_object']]+=1
                    if d.get('search24_irm','off')!='off' and (not c.get('blocked_object') or 'min_gap_m' not in c):bad_ledgers+=1
            for e in t.get('search23_log',[]):
                if e.get('event')=='grid_plan':grids[e['status']]+=1
        for rid in plan.get('roles',{}):
            ledger=read(raw/f'teacher-{rid}.jsonl')
            for line in (ledger or b'').splitlines():
                x=json.loads(line);b=x.get('planning_compute',{})
                if b:budget['ticks']+=1;budget['exhausted']+=int(b.get('budget_exhausted',False))
        sim=d.get('sim_s');cap_end=d.get('cap_end',sim is not None and sim>=60-1e-8)
        row={'episode':p.name,'seed':plan.get('seed'),'scene':plan.get('cargo_scene','off'),
            'status':d.get('status','missing'),'success':success,'sim_s':sim,'wall_s':d.get('wall_s'),
            'cap_end':cap_end,'end_reason':d.get('end_reason','cap_end' if cap_end else 'teacher_terminal' if complete else 'HOST_ERROR'),
            'outcomes':{r:t.get('outcome') for r,t in d.get('teachers',{}).items()},
            'input_audit':d.get('input_audit'),'first30_speed':d.get('first30_speed'),
            'rejections':dict(categories),'reasons':dict(reasons),'blockers':dict(blocks),'grid_status':dict(grids),
            'planning_compute':dict(budget),'missing_rejection_evidence':bad_ledgers,
            'decoded_result_sha256':hashlib.sha256(data).hexdigest() if data else None}
        totals.update(categories)
        if not success and complete:
            frames=[]
            for rid in plan.get('roles',{}):
                files=sorted((raw/'eval-own'/rid).glob('*.jpg'))
                indices=sorted({round((len(files)-1)*u/5) for u in range(6)}) if files else []
                for i in indices:
                    src=files[i];target=out/'failed-frames'/p.name/rid/src.name
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(src.read_bytes())
                    artifacts.append({'path':str(target.relative_to(out)),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
                    frames.append((src,rid))
            if frames:
                canvas=Image.new('RGB',(640,270*((len(frames)+1)//2)),(20,20,20));draw=ImageDraw.Draw(canvas)
                for i,(src,rid) in enumerate(frames):
                    x=(i%2)*320;y=(i//2)*270
                    with Image.open(src) as im:canvas.paste(im.resize((320,240)),(x,y))
                    draw.text((x+3,y+243),f'{p.name} {rid} {src.stem}',fill='white')
                target=out/(p.name+'-montage.jpg');canvas.save(target,quality=92)
                artifacts.append({'path':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
        rows.append(row)
    source=(root/'SOURCE_SHA').read_text().strip()
    manifest=root/'SHA256SUMS'
    verified=(manifest.exists() and (root/'EXIT').exists() and
              subprocess.run(['sha256sum','-c','--quiet',str(manifest)],cwd=root).returncode==0)
    result={'source_sha':source,'run':root.name,'raw':str(root),'n':sum(r['success'] for r in rows),'N':6,
        'completed':sum(r['status']=='complete' for r in rows),'host_error_N':sum(r['status'] in ('HOST_ERROR','interrupted','missing') or ((root/'EXIT').exists() and r['status']=='running') for r in rows),
        'running_N':sum(r['status']=='running' and not (root/'EXIT').exists() for r in rows),
        'rejections':dict(totals),'rows':rows,'artifacts':artifacts,
        'scope':'raw result recount on gcp1; no control replay; selected failed own RGB only',
        'remote_full_manifest_verified':verified,
        'raw_manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.exists() else None,
        'source_sha_matches_run_meta':json.loads((root/'RUN_META.json').read_text()).get('sha')==source}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('source_sha','run','n','N','completed','host_error_N','rejections')}))
    for r in rows:print(json.dumps({k:r[k] for k in ('episode','seed','status','success','sim_s','cap_end','outcomes','rejections')}))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    analyze(a.root,a.out)
