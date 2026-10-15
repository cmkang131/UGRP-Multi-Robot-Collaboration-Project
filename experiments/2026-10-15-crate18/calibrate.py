"""Offline pairing only: evaluation poses NEVER enter the runtime controller."""
import collections, hashlib, json, math, statistics, subprocess
from pathlib import Path
BASE = Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
HERE = Path(__file__).parent

def read(p):
    if not p.exists(): p = p.with_suffix(p.suffix+'.zst')
    b = subprocess.check_output(['zstd','-dc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
    return b, {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(), 'decoded_sha256':hashlib.sha256(b).hexdigest()}

def main():
    bins=collections.defaultdict(list); sources=[]; records=[]
    selected = list(BASE.glob('crate17-*/raw'))+list(BASE.glob('crate16-*/raw'))+list(BASE.glob('crate-reproduction-*-8007db00/raw'))+list(BASE.glob('crate-diag-*-8007db00/raw'))+list(BASE.glob('crate-diag-*-727de2af/raw'))
    for raw in sorted(selected):
        b, src=read(raw/'result.json');result=json.loads(b)
        if result['cargo_scene_version']!='crate_mass_025_v1':continue
        sources.append(src)
        b,src=read(raw/'eval-only.jsonl');sources.append(src)
        ev={round(r['t'],3):r for r in map(json.loads,b.splitlines())}
        for rid in ('r1','r2'):
            b,src=read(raw/f'teacher-{rid}.jsonl');sources.append(src)
            for t in map(json.loads,b.splitlines()):
                v=ev.get(round(t['t'],3));n=ev.get(round(t['t']+.1,3));c=t.get('applied_command',{})
                if not v or not n or not any(c.get('wheels',[])):continue
                w=c['wheels'];d=c['duration_s']
                # Isolate pure equal-width +/-0.35 pulses; mixed navigation cannot identify a quantum.
                if max(w)-min(w)==0:axis='forward'
                elif w==[-w[1],w[1],-w[1],w[1]]:axis='yaw'
                elif w==[-w[1],w[1],w[1],-w[1]]:axis='lateral'
                else:continue
                if max(d)-min(d)>1e-6 or abs(abs(w[0])-.35)>1e-6:continue
                a=v['robots'][rid]['pose'];p=n['robots'][rid]['pose'];dx=p[0]-a[0];dy=p[1]-a[1]
                movement=abs(math.atan2(math.sin(p[2]-a[2]),math.cos(p[2]-a[2]))) if axis=='yaw' else abs(dx*math.cos(a[2])+dy*math.sin(a[2])) if axis=='forward' else abs(-dx*math.sin(a[2])+dy*math.cos(a[2]))
                state='held' if v.get('held_s',0)>0 or any(x in ('lift','complete') for x in v.get('phases',{}).values()) else 'unladen'
                width=round(max(d),3);bins[(state,axis,width)].append(movement)
                records.append(dict(run=raw.parent.name,rid=rid,t=t['t'],state=state,axis=axis,width_s=width,movement=movement))
    table=[]
    for (state,axis,width),v in sorted(bins.items()):
        table.append(dict(state=state,axis=axis,width_s=width,n=len(v),median=statistics.median(v),minimum=min(v),maximum=max(v)))
    pairs=Path('outputs/crate18/calibration-pairs.json');pairs.parent.mkdir(parents=True,exist_ok=True)
    pairs.write_text(json.dumps(records,separators=(',',':'))+'\n')
    out=dict(scope='offline calibration, GCP n4-highcpu-64, mass025; eval truth only here',sources=sources,table=table,
        pairs=dict(path=str(pairs.resolve()),sha256=hashlib.sha256(pairs.read_bytes()).hexdigest(),n=len(records)),
        policy=dict(state_models={'unladen':{'minimum_duration_s':[.025,.025,.018],'delta':[.001321,.000824,.012432]},'held':{'status':'unavailable','n':0,'runtime_use':False}},
        selection='minimum sampled duration with N>=20 and >=75% absolute motion >0.5mm (translation)/0.005rad (yaw); aggregate phase/contact mix, not an isolated bench',
        unladen_only='crate18 pre-grasp alignment only; carrying/release path unchanged'))
    (HERE/'calibration.json').write_text(json.dumps(out,indent=2)+'\n')
    for axis in ('yaw','forward','lateral'):
        print(axis,[(r['width_s'],r['n'],round(r['median'],6)) for r in table if r['axis']==axis and r['n']>=3])
    print('held_samples',sum(r['state']=='held' for r in records),'sources',len(sources))
if __name__=='__main__':main()
