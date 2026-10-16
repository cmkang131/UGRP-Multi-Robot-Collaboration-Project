"""Own-only prefix prediction, seal, then separate GT-only route audit."""
from pathlib import Path
from collections import Counter
import argparse,hashlib,json,math,os,subprocess,sys
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/own-traversal-return-v1')
BASE=Path('/Users/changmin/projects/ugrp/outputs/own-map-return-repeat-v1')
from harness.own_traversal_graph import TraversalGraph,TraversalReturn,own_sample
from harness.self_pose_graph import compose,wrap
from harness.public_navigation.costmap import HALF


def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(s) for s in p.open()]
def dump(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def predict(seed):
    ep=BASE/f'seed{seed}';out=RAW/str(seed)
    assert not (out/'prediction.json').exists(),'ONE_REPLAY_ONLY'
    assert os.getpriority(os.PRIO_PROCESS,0)==0,'NICE_MUST_BE_ZERO'
    cov_file='prefix-poses.json' if (ep/'prefix-poses.json').exists() else 'frontend-covariances.jsonl'
    manifest=load(ep/'artifacts.sha256.json');names=['own-controller.jsonl','own-contacts.jsonl',cov_file,'navigation.json','robots/r3/frames.jsonl']
    hashes={p:sha(ep/p) for p in names}
    for p,h in hashes.items():
        if p in manifest:assert h==manifest[p]
    trace=rows(ep/'own-controller.jsonl');prefix={r['frame_id']:r for r in trace if r.get('stage')=='explore' and r.get('pose') is not None}
    suffix=next((r for r in trace if r.get('stage')=='return'),None)
    frame={r['frame_id']:r for r in rows(ep/'robots/r3/frames.jsonl')}
    covariance_rows=load(ep/cov_file) if cov_file.endswith('.json') else rows(ep/cov_file)
    cov={r['frame_id']:r['covariance'] for r in covariance_rows}
    nav=load(ep/'navigation.json');bad=[e for e in nav if e['reason'] in ('controller_no_progress','navigation_action_aborted')]
    g=TraversalGraph('r3');query=None;counts=Counter();rgb_hashes={}
    for line in (ep/'own-contacts.jsonl').open():
        o=json.loads(line);fid=o['frame_id'];r=prefix.get(fid)
        if r is not None:
            f=frame[fid];path=ep/f['path'];h=sha(path);assert h==f['sha256'];rgb_hashes[f['path']]=h
            image=cv2.cvtColor(cv2.imread(str(path)),cv2.COLOR_BGR2RGB)
            reason=next((e['reason'] for e in bad if r['t']-.200001<=e['t']<=r['t']+1e-8),None)
            s=own_sample(r,o,rgb=image,frame_sha256=h,covariance=cov[fid],excluded_reason=reason)
            g.observe(s,r.get('remembered_B'));counts[r['status']]+=1
        elif suffix is not None and fid==suffix['frame_id']:
            query=dict(t=o['t'],frame_id=fid,pose=suffix['local_pose'],covariance=suffix['belief']['covariance'],segments=o['segments'],camera=o['camera'])
    g.seal();route=g.route(g.anchor);policy=TraversalReturn(g)
    match=policy.localize(query) if query is not None else None
    controls=dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True,cwd=ROOT).strip(),seed=seed,
        inputs=hashes,rgb_hashes=rgb_hashes,graph=g.snapshot(),route=route,query=query,match=match,matched_route=policy.route,
        status_counts=dict(counts),control_evidence='own RGB/estimated pose/commands only; no evaluation file opened',nice=os.getpriority(os.PRIO_PROCESS,0))
    dump(out/'prediction.json',controls);dump(out/'seal.json',dict(sha256=sha(out/'prediction.json')))
    print(seed,'sealed',len(g.nodes),len(g.edges),'B',g.goal_node,'route',route is not None,'match',None if match is None else match['reason'],flush=True)


def line_hits(a,b,rects):
    """Exact continuous segment / axis-aligned wall intersection, no grid rounding."""
    a,b=np.asarray(a),np.asarray(b);d=b-a;low=rects[:,:2]-rects[:,2:];high=rects[:,:2]+rects[:,2:]
    t0=np.zeros(len(rects));t1=np.ones(len(rects));ok=np.ones(len(rects),bool)
    for j in range(2):
        if abs(d[j])<1e-12:ok&=(a[j]>=low[:,j])&(a[j]<=high[:,j])
        else:
            x=(low[:,j]-a[j])/d[j];y=(high[:,j]-a[j])/d[j]
            t0=np.maximum(t0,np.minimum(x,y));t1=np.minimum(t1,np.maximum(x,y))
    return bool(np.any(ok&(t0<=t1)))


def footprint_hits(p,rects):
    c,s=math.cos(p[2]),math.sin(p[2]);u=np.array([c,s]);v=np.array([-s,c]);d=rects[:,:2]-p[:2];h=rects[:,2:]
    ok=np.ones(len(rects),bool)
    for axis in (np.array([1.,0]),np.array([0.,1.]),u,v):
        robot=HALF[0]*abs(axis@u)+HALF[1]*abs(axis@v)
        wall=h@abs(axis);ok&=abs(d@axis)<=robot+wall
    return bool(np.any(ok))


def geometry(poses,rects):
    poses=np.asarray(poses,float).reshape(-1,3)
    center=sum(line_hits(a[:2],b[:2],rects) for a,b in zip(poses,poses[1:]))
    hits=0;sample_count=0
    for a,b in zip(poses,poses[1:]):
        dyaw=float(wrap(b[2]-a[2]));steps=max(1,math.ceil(math.dist(a[:2],b[:2])/.025),math.ceil(abs(dyaw)/math.radians(5)))
        for t in np.linspace(0,1,steps+1):
            hits+=footprint_hits(np.r_[a[:2]+t*(b[:2]-a[:2]),a[2]+t*dyaw],rects);sample_count+=1
    return dict(center_crossing_segments=int(center),center_segments=max(0,len(poses)-1),footprint_overlap_samples=int(hits),footprint_samples=sample_count)


def score(seed):
    ep=BASE/f'seed{seed}';out=RAW/str(seed);seal=load(out/'seal.json');assert sha(out/'prediction.json')==seal['sha256']
    p=load(out/'prediction.json');g=p['graph'];truth=rows(ep/'eval_only/trajectory.jsonl')
    times=np.array([r['t'] for r in truth]);xyyaw=np.array([[*r['robot_xyz_m'][:2],r['robot_yaw_rad']] for r in truth]);origin=xyyaw[0]
    static=load(ep/'inputs/static_map.json');rects=np.array([r['center_m']+r['half_extents_m'] for r in static['obstacles'] if r.get('kind')=='wall'])
    def audit(samples):
        times_s=np.array([s['t'] for s in samples]);idx=np.abs(times_s[:,None]-times[None,:]).argmin(1) if len(samples) else []
        assert not len(samples) or np.max(abs(times[idx]-times_s))<.101
        estimate=compose(origin,np.array([s['pose'] for s in samples]).reshape(-1,3))
        return dict(estimated=geometry(estimate,rects),actual=geometry(xyyaw[idx],rects))
    edges=[]
    for e in g['edges']:edges.append(dict(a=e['a'],b=e['b'],**audit(e['samples'])))
    selected=audit(p['route']['samples']) if p['route'] is not None else None
    matched=audit(p['matched_route']['samples']) if p['matched_route'] is not None else None
    component={n['id']:n['id'] for n in g['nodes']}
    for e in g['edges']:
        a,b=component[e['a']],component[e['b']]
        for k in component:
            if component[k]==b:component[k]=a
    sizes=Counter(component.values());target=g['goal_node'];last=g['last_node']
    result=dict(seed=seed,frames=g['frames'],nodes=len(g['nodes']),edges=len(g['edges']),components=len(sizes),
        breaks=len(g['breaks']),break_reasons=dict(Counter(b['reason'] for b in g['breaks'])),
        B_observed=target is not None,B_node=target,B_component_size=None if target is None else sizes[component[target]],
        last_component_size=None if last is None else sizes[component[last]],route_exists=p['route'] is not None,
        route_length_m=None if p['route'] is None else p['route']['length_m'],selected_route=selected,matched_route=matched,
        match=p['match'],edges_audit=edges,seal=seal,
        prefix_before_query=p['query'] is None or max(n['t'] for n in g['nodes'])<p['query']['t'],
        qualification='fixed recorded motion, no new physical execution or return success claim')
    dump(EXP/'results'/f'{seed}.json',result)
    print(seed,'scored',result['components'],'components',flush=True)


def gate():
    data=[load(EXP/'results'/f'{s}.json') for s in range(49001,49007)];eligible=[r for r in data if r['B_observed']]
    checks=dict(causal_prefixes=len(data)==6 and all(r['prefix_before_query'] and r['nodes']>0 for r in data),
        B_routes=bool(eligible) and all(r['route_exists'] for r in eligible),
        zero_route_wall_crossings=bool(eligible) and all(r['selected_route'] is not None and r['selected_route']['estimated']['center_crossing_segments']==0 and r['selected_route']['estimated']['footprint_overlap_samples']==0 for r in eligible),
        local_match_and_route=bool(eligible) and all(r['match'] is not None and r['match']['status']=='accepted' and r['matched_route'] is not None for r in eligible))
    result=dict(passed=all(checks.values()),checks=checks,n=6,B_observed=len(eligible),routes=sum(r['route_exists'] for r in data),
        accepted_matches=sum(r['match'] is not None and r['match']['status']=='accepted' for r in data),prereg_commit='570f8127')
    dump(EXP/'results/gate.json',result);print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['predict','score','gate']);p.add_argument('--seed',type=int,choices=range(49001,49007));a=p.parse_args()
    if a.mode=='predict':predict(a.seed)
    elif a.mode=='score':score(a.seed)
    else:gate()
