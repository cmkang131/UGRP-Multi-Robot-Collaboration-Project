import json,hashlib,math,time
from urllib.error import HTTPError
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
import numpy as np
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
from scripts.tensorboard_tools.offline_audit import convert
ROOT=Path('/Users/changmin/projects/ugrp/outputs/s2-active-observation-v58-20261009')
SHARED=ROOT.parent/'tensorboard';NAME='1009-s2-active-v58-r2'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
result=read(ROOT/'physical-result-v2.json');snapshot=SHARED/NAME;snapshot.mkdir(exist_ok=False);specs={}
for r in result['runs']:
 seed=r['seed'];source=ROOT/'views-v2'/f's{seed}-active';source.mkdir(parents=True,exist_ok=False)
 raw=read(ROOT/f'physical-s{seed}.json');s=raw['summary']
 scalars={k:s.get(k) for k in ('success','carry_rmse_m','unflagged_gt_25cm','near_truth_support_fraction','near_truth_median_mass',
  'active_count','active_added_s','active_added_fraction','active_episode_updates','B_distance_m','max_fix_gap_s')}
 scalars.update(nees_rate=s['nees_exceed_fraction'],start_error_m=s['convergence']['actual_xy_error_m'] if s.get('convergence') else None)
 scalars={'offline/'+k:float(v) for k,v in scalars.items() if v is not None}
 trace=source/'series.jsonl';trace.write_text(''.join(json.dumps(dict(t=q['t'],mass=q['mass'],support=int(q['mass']>0),active_count=sum(e['t']<=q['t'] for e in raw['active_events'])))+'\n' for q in raw['particle_series']))
 spec=dict(schema='ugrp.offline_audit_view.v1',derived_view_only=True,offline_source=dict(path=str(ROOT/'physical-result-v2.json'),sha256=sha(ROOT/'physical-result-v2.json')),
  offline_scalar_scope='Posthoc evaluation of completed S2 DEV physics; no hardware or formal E2E claim. Active success and fresh-seed denominator remain separate.',offline_scalars=scalars,
  offline_series=dict(source=dict(path=str(trace),sha256=sha(trace)),format='jsonl',sim_time_field='t',tags=[dict(tag='trace/'+k,path=[k]) for k in ('mass','support','active_count')]),
  family='S2',condition='v140-no-prior-active',policy='discriminating_views_v1',seed=seed,source_sha=s['source_sha'],model_calls=0,sim_s=s['sim_s'],wall_s=s['wall_s'],
  hparam_metrics=list(scalars),texts={'result/scope':result['scope'],'result/would_stop':s['would_stop'],'result/options':s['options']})
 (source/'result.json').write_text(json.dumps(spec,indent=2)+'\n');convert(source,snapshot/f's{seed}-active');specs[f'{NAME}/s{seed}-active']=spec
(snapshot/'collection.json').write_text(json.dumps(dict(sources=[str(ROOT/'views-v2'/f's{s["seed"]}-active') for s in result['runs']],complete=True))+'\n')
verified=[]
for name,spec in specs.items():
 ea=EventAccumulator(str(SHARED/name),size_guidance={'scalars':0});ea.Reload();total=0
 for tag in ea.Tags()['scalars']:
  events=ea.Scalars(tag)
  for attempt in range(10):
   try:
    with urlopen('http://127.0.0.1:6006/data/plugin/scalars/scalars?'+urlencode(dict(run=name,tag=tag)),timeout=15) as response:live=json.load(response)
   except HTTPError as exc:
    if exc.code!=404:raise
    live=[]
   if len(live)==len(events):break
   time.sleep(3)
  assert len(live)==len(events),(name,tag,len(live),len(events))
  assert np.allclose([q[2] for q in live],[e.value for e in events],rtol=1e-6,atol=1e-8)
  if tag in spec['offline_scalars']:assert np.isclose(events[-1].value,spec['offline_scalars'][tag],rtol=1e-6,atol=1e-8)
  total+=len(events)
 verified.append(dict(run=name,tags=len(ea.Tags()['scalars']),values=total))
pins=['offline/success','offline/carry_rmse_m','offline/nees_rate','offline/active_count','offline/active_added_fraction','result/wall_s','result/model_calls']
pattern='^(?:'+NAME+'/s.*-active|1008-s2-unknown-start-v54-r2/s.*-unknown-start)'
url='http://127.0.0.1:6006/?'+urlencode(dict(runFilter=pattern,smoothing=0,pinnedCards=json.dumps([dict(plugin='scalars',tag=t) for t in pins])))+'#timeseries'
delivery=dict(snapshot=str(snapshot),baseline_reconverted=False,baseline_snapshot=str(SHARED/'1008-s2-unknown-start-v54-r2'),url=url,verified=verified,total_values=sum(q['values'] for q in verified),ui='pending')
(ROOT/'delivery.json').write_text(json.dumps(delivery,indent=2)+'\n')
path=SHARED.parent/'tensorboard-view.json';view=read(path);view['s2_active_observation_v58_20261009']=dict(snapshot=str(snapshot),url=url,pinned_metrics=pins,default_runs=[NAME+'/s1060-active','1008-s2-unknown-start-v54-r2/s1060-unknown-start'],hparams_visible_columns=['seed'],scope=result['scope']);path.write_text(json.dumps(view,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(delivery))
