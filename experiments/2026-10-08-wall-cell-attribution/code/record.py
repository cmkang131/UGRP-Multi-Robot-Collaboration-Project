"""Post-evaluation figure examples, accounting verification and artifact manifest."""
from diagnose import *
import cv2
from collections import defaultdict
COLORS={'detector':(0,0,255),'pose':(255,100,0),'range_projection':(0,150,255),'object':(255,0,255),'cell_boundary':(0,200,0),'unresolved':(0,255,255)}
ims=[]
for seed,frames in [('31001',[325,471,106]),('32002',[52,191,810])]:
    ep=EPISODES[seed];labels=Labels(ep)
    by=defaultdict(list)
    for cell in load(RAW/f'{seed}-false-cells.json'):
        for s in cell['sources']:by[s['frame_id']].append(s)
    for frame in frames:
        row=labels.frames[frame]
        und=modules()[0].undistort(cv2.imread(str(ep/row['path'])))
        for s in by[frame]:
            u,v=s['uv']
            if 0<=u<640 and 0<=v<480:cv2.circle(und,(round(u),round(v)),3,COLORS[s['category']],-1)
        und=cv2.resize(und,(480,360));cv2.rectangle(und,(0,0),(480,27),(250,250,250),-1)
        cv2.putText(und,f'seed {seed} / frame {frame} / t={row["sim_time"]:.1f}s',(8,19),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1)
        ims.append(und)
canvas=np.vstack([np.hstack(ims[:3]),np.hstack(ims[3:]),np.full((32,1440,3),255,np.uint8)])
cv2.putText(canvas,'Red: false contact/link | Blue: pose | Orange: projection | Green: cell boundary',(8,743),cv2.FONT_HERSHEY_SIMPLEX,.6,(10,10,10),1)
cv2.imwrite(str(EXP/'figures/contact-examples.jpg'),canvas,[cv2.IMWRITE_JPEG_QUALITY,85])
verified={}
for seed,ep in EPISODES.items():
    results=load(EXP/f'results/{seed}-comparison.json');diag=load(EXP/f'results/{seed}-diagnosis.json')
    p=RAW/'predictions'/seed;seal=load(p/'seal.json')
    for name,digest in seal['files'].items():assert sha(p/name)==digest
    assert (p/'off.json').read_bytes()==(ep/'grid.json').read_bytes()
    off,on=load(p/'off.json'),load(p/'on.json')
    assert [c for c in off['cells'] if c[2]<=0]==[c for c in on['cells'] if c[2]<=0]
    values={tuple(c[:2]):c[2] for c in off['cells']}
    assert all(values[tuple(c[:2])]==c[2] for c in on['cells'])
    assert all(off[k]==on[k] for k in off if k!='cells')
    false=load(RAW/f'{seed}-false-cells.json')
    assert len(false)==diag['false_cells']
    assert sum(v['cells'] for v in diag['categories'].values())==len(false)
    assert all(abs(sum(c['fractions'].values())-1)<1e-10 for c in false)
    decisions=load(ep/'decisions.json')
    counts=dict(Counter(d['reason'] for d in decisions))
    assert results['inserted_frames']==len(load(ep/'graph.json')['ledger'])
    ledger_frames={r['frame_id'] for r in load(ep/'graph.json')['ledger']}
    assert all(s['frame_id'] in ledger_frames for c in false for s in c['sources'])
    verified[seed]=dict(off_bytes_identical=True,free_cells_exact=True,retained_log_odds_exact=True,
        all_pose_metadata_unchanged=True,false_cell_accounting_exact=True,
        rgb=results['rgb_frames'],inserted_frames=results['inserted_frames'],decision_frames=len(decisions),reasons=counts,
        source_sha=seal['source_sha'],raw_false_cell_sha256=sha(RAW/f'{seed}-false-cells.json'),
        absolute_gate=results['conditions']['on']['absolute_gate'])
for f in (EXP/'figures').glob('*'):assert f.stat().st_size<=1024*1024
raw_files={str(f.relative_to(RAW)):dict(sha256=sha(f),bytes=f.stat().st_size) for f in sorted(RAW.rglob('*')) if f.is_file() and f.name!='artifacts.sha256.json' and f.suffix!='.log'}
dump(RAW/'artifacts.sha256.json',raw_files)
dump(EXP/'results/verification.json',dict(records=verified,physics=0,models=0,lock_acquired=False,tests=10,
    note='Two sealed predictions, fixed thresholds. Earlier unsealed JSON failure retained. Map figure extent expanded only; no metric change.',
    raw_manifest_sha256=sha(RAW/'artifacts.sha256.json'),raw_path=str(RAW),
    figures={f.name:dict(sha256=sha(f),bytes=f.stat().st_size) for f in (EXP/'figures').glob('*')}))
print(json.dumps(verified,indent=2))
