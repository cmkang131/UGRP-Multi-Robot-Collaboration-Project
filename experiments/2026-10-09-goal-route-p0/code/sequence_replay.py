"""Frozen CS M results + own past color transitions; GT scoring only after seal."""
from map_replay import *
from harness.self_pose_graph import between,wrap

def predict_sequence():
 dest=OUT/'sequence';dest.mkdir(parents=True,exist_ok=False)
 for seed in range(49001,49007):
  original=BASE/'traversal-reconnection-v1'/str(seed)/'prediction.json';data=load(original);g=data['graph']
  own=source(seed)/'own-inputs.json';features=load(own)
  sequences={n['id'] if 'id' in n else i:adapter.color_sequence(features,n['t']) for i,n in enumerate(g['nodes'])}
  results=[dict(original=e,on=adapter.gate_match(e,sequences[e['a']],sequences[e['b']],place_gate=adapter.SEQUENCE)) for e in g['reconnections']]
  dump(dest/f'{seed}.json',dict(seed=seed,results=results,original_sha256=sha(original),own_features_sha256=sha(own),gt_inputs=False))
 dump(dest/'seal.json',{str(seed):sha(dest/f'{seed}.json') for seed in range(49001,49007)})
 print('sequence SEALED',flush=True)

def evaluate_sequence():
 from collections import Counter
 dest=OUT/'sequence';seal=load(dest/'seal.json');reports=[]
 for seed in range(49001,49007):
  assert sha(dest/f'{seed}.json')==seal[str(seed)]
  p=load(dest/f'{seed}.json');g=load(BASE/'traversal-reconnection-v1'/str(seed)/'prediction.json')['graph']
  truth=rows(source(seed)/'eval_only/trajectory.jsonl');times=np.array([r['t'] for r in truth]);poses=np.array([[*r['robot_xyz_m'][:2],r['robot_yaw_rad']] for r in truth])
  for r in p['results']:
   e=r['original'];err=None
   if e['accepted']:
    nodes=[g['nodes'][e[k]] for k in ['a','b']];idx=[np.argmin(abs(times-n['t'])) for n in nodes]
    assert max(abs(times[i]-n['t']) for i,n in zip(idx,nodes))<.101
    actual=between(poses[idx[0]],poses[idx[1]]);estimate=np.array(e['relative_pose'])
    err=dict(xy_m=float(np.linalg.norm(estimate[:2]-actual[:2])),yaw_deg=abs(float(wrap(estimate[2]-actual[2])))*180/math.pi)
   reports.append(dict(seed=seed,kind=e['kind'],a=e['a'],b=e['b'],off=e['accepted'],on=r['on']['accepted'],reason=r['on']['reason'],error=err))
 summary={}
 for kind in ['place_recognition','recovery_bridge']:
  selected=[r for r in reports if r['kind']==kind];summary[kind]=dict(attempts=len(selected),reasons=dict(Counter(r['reason'] for r in selected)))
  for mode in ['off','on']:
   err=[r['error'] for r in selected if r[mode]]
   summary[kind][mode]=dict(accepted=len(err),false_accepts=sum(e['xy_m']>.25 or e['yaw_deg']>15 for e in err),xy_median_m=float(np.median([e['xy_m'] for e in err])) if err else None,xy_max_m=max([e['xy_m'] for e in err],default=None))
 a,b=summary['place_recognition']['off'],summary['place_recognition']['on'];summary['passed']=bool(b['accepted'] and b['false_accepts']==0 and b['xy_median_m']<a['xy_median_m'])
 dump(OUT/'sequence/evaluation.json',reports);dump(EXP/'results/sequence.json',summary);print(summary,flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['predict','evaluate']);a=p.parse_args();(predict_sequence if a.mode=='predict' else evaluate_sequence)()
