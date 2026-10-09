import hashlib,json,math,urllib.request,urllib.parse
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
BASE=Path('/Users/changmin/projects/ugrp/outputs')
NAME='1009-simspeed-core-725f45b1'
SNAP=BASE/'tensorboard'/NAME
VIEWS=BASE/'simspeed-core-20261009-views'
read=lambda p:json.loads(p.read_text())
get=lambda route:json.load(urllib.request.urlopen('http://127.0.0.1:6006'+route))
tags=get('/data/plugin/scalars/tags')
verified=[]
for source in sorted(VIEWS.iterdir()):
    v=read(source/'result.json'); run=NAME+'/'+source.name
    m=read(SNAP/source.name/'manifest.json');assert m['complete'] and not m['warnings']
    for filename,sf in m['source_files'].items():
        assert hashlib.sha256((source/filename).read_bytes()).hexdigest()==sf['sha256']
    expected=dict(v['offline_scalars'])
    expected.update({'result/'+k:v[k] for k in ('wall_s','sim_s','commands','model_calls') if k in v})
    if 'success' in v:expected['evaluation/reported_success']=int(v['success'])
    ea=EventAccumulator(str(SNAP/source.name)).Reload()
    for tag,want in expected.items():
        event=ea.Scalars(tag);assert len(event)==1
        assert math.isclose(event[0].value,want,rel_tol=1e-6,abs_tol=1e-6),(run,tag,event,want)
        assert tag in tags[run]
        live=get('/data/plugin/scalars/scalars?'+urllib.parse.urlencode({'run':run,'tag':tag}))
        assert len(live)==1 and math.isclose(live[0][2],want,rel_tol=1e-6,abs_tol=1e-6)
        verified.append({'run':run,'tag':tag,'expected':want,'event':event[0].value,'live':live[0][2]})
metrics=['gate/bytes_identical','offline/wall_per_sim','result/wall_s','result/commands','result/model_calls','offline/load_start_1m']
url='http://127.0.0.1:6006/?'+urllib.parse.urlencode({'smoothing':0,'runFilter':'^'+NAME+'/(s2|s3|egomap)-(A1|A2|B1|B2)$','pinnedCards':json.dumps([{'plugin':'scalars','tag':t} for t in metrics],separators=(',',':'))})+'#timeseries'
record={'snapshot':str(SNAP),'url':url,'pinned_metrics':metrics,'default_runs':[NAME+'/'+p.name for p in sorted(VIEWS.iterdir()) if p.name[-2:] in ('A1','A2','B1','B2')],
'hparams_visible_columns':['case','outcome','policy','result/wall_s','result/commands','result/model_calls'],
'scope':'30 SIM seconds per path, fixed saved commands, n=2/condition ABBA; equality gate is not task success. S3 original evaluator error preserved. Profiles and v1/v2 failures excluded from speed means.',
'verification':{'event_and_live_scalars':len(verified),'scalar_tolerance':1e-6,'new_videos':0},'model_response_time':'not measured; model calls 0'}
shared=BASE/'tensorboard-view.json';old=shared.read_text();d=json.loads(old)
assert 'sim_speed_core_20261009' not in d
# Append only our key; preserve all existing bytes/format/order.
cut=old.rfind('}');assert cut>=0
entry=json.dumps({'sim_speed_core_20261009':record},indent=2,ensure_ascii=False)[2:-2]
new=old[:cut].rstrip()+',\n'+entry+'\n'+old[cut:]
assert json.loads(new)==dict(d,sim_speed_core_20261009=record)
assert shared.read_text()==old
shared.write_text(new)
report={'view':record,'verified':verified,'server':{'pid':52016,'logdir':str(BASE/'tensorboard'),'host':'127.0.0.1','port':6006,'other_task_server_unchanged':True}}
Path('experiments/2026-10-09-sim-speed-core/results/tensorboard.json').write_text(json.dumps(report,indent=2)+'\n')
print('VERIFIED',len(verified),'scalars across',len(list(VIEWS.iterdir())),'views')
print(url)
