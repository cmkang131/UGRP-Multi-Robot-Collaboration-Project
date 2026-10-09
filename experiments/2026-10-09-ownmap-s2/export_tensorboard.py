import json,hashlib,sys,urllib.parse,urllib.request
from pathlib import Path
import numpy as np
from scripts.tensorboard_tools.offline_audit import main as export_main
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

raw=Path(sys.argv[1]);evaluation=Path(sys.argv[2]);snapshot=Path(sys.argv[3])
result=json.loads((evaluation/'result.json').read_text());series=json.loads((evaluation/'series.json').read_text())
derived=evaluation/'tensorboard-inputs';derived.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
args=[];expected={}
for row in result['pairs']:
 for opt,label in [('off','base'),('own_grid_v1','own')]:
  if opt not in row:continue
  m=row[opt];pred=json.loads((raw/row['pair_id']/opt/'prediction.json').read_text())
  name=row['pair_id']+'-'+label;dest=derived/name;dest.mkdir()
  metric={'offline/correct_convergence':int(m['correct_convergence']),'offline/converged':int(m['converged']),
    'offline/wrong_mode':int(m['wrong_mode']),'offline/unflagged25cm_count':m['unflagged_gt25cm'],
    'offline/decision_count':m['decisions'],'offline/nees_denominator':m['nees_all']['valid']}
  if m['post_convergence_rmse_m'] is not None:metric['offline/post_rmse_m']=m['post_convergence_rmse_m']
  if m['nees_all']['exceed_fraction'] is not None:metric['offline/nees_fraction']=m['nees_all']['exceed_fraction']
  if m['first_convergence']:metric['offline/convergence_sim_s']=m['first_convergence']['t']
  timeline=dest/'timeline.jsonl';timeline.write_text(''.join(json.dumps(q)+'\n' for q in series[row['pair_id']+'-'+opt]))
  view=dict(schema='ugrp.offline_audit_view.v1',derived_view_only=True,
    offline_source={'path':str(evaluation/'result.json'),'sha256':sha(evaluation/'result.json')},
    offline_source_pointer=f"pairs/{row['pair_id']}/{opt}",offline_scalars=metric,
    offline_scalar_scope='Offline fixed RGB/issued-command localization replay. No physics, no model calls. Success=correct first convergence, not transport. Wall time is processing only. Own-map source and S2 differ in lower doorway geometry.',
    family='ownmaps2a',policy=opt,condition=row['map_seed'] if opt!='off' else 'provided_map',case=row['pair_id'],
    source_sha=pred['source_sha'],run_id=name,outcome='correct' if m['correct_convergence'] else 'not_ready',
    success=m['correct_convergence'],success_definition='First declared std_xy<=5cm has XY<=25cm and yaw<=15deg after fixed evaluation-only map-start alignment; NOT physical task success.',
    wall_s=pred['wall_s'],commands=pred['commands'],model_calls=0,
    hparam_metrics=['offline/correct_convergence','offline/unflagged25cm_count','result/wall_s','result/commands','result/model_calls']+(['offline/post_rmse_m'] if 'offline/post_rmse_m' in metric else []),
    offline_series=dict(source={'path':str(timeline),'sha256':sha(timeline)},format='jsonl',sim_time_field='t',tags=[{'tag':'trace/xy_error_m','path':['xy_error_m']},{'tag':'trace/std_xy_m','path':['std_xy_m']}]),
    texts={'provenance/no_new_video':'No new render/video. Original S2 frames were SHA256-verified; originals retained.','provenance/input_paths':{'raw':pred['raw'],'map_raw':pred['map_raw']}},evaluation=m)
  (dest/'result.json').write_text(json.dumps(view,ensure_ascii=False,indent=2)+'\n')
  args+=['--source',str(dest)];expected[name]={**metric,'result/wall_s':pred['wall_s'],'result/commands':pred['commands'],'result/model_calls':0,'evaluation/reported_success':int(m['correct_convergence'])}
export_main(args+['--output',str(snapshot)])
verification=[]
for name,metrics in expected.items():
 acc=EventAccumulator(str(snapshot/name),size_guidance={'scalars':0});acc.Reload()
 for tag,value in metrics.items():
  data=acc.Scalars(tag);assert len(data)==1 and np.isclose(data[0].value,value,rtol=2e-6,atol=1e-8),(name,tag,data,value)
 verification.append(dict(run=name,scalars=len(metrics),trace_samples=len(acc.Scalars('trace/xy_error_m'))))
tags=['offline/correct_convergence','offline/post_rmse_m','offline/nees_fraction','offline/unflagged25cm_count','result/wall_s','result/commands','result/model_calls']
url='http://127.0.0.1:6006/?'+urllib.parse.urlencode({'runFilter':'^'+snapshot.name+'/', 'smoothing':'0', 'pinnedCards':json.dumps([{'plugin':'scalars','tag':t} for t in tags])})+'#timeseries'
report=dict(snapshot=str(snapshot),url=url,event_accumulator_verified=verification,pinned_metrics=tags,
 hparams_visible_columns=['condition','case','outcome','offline/correct_convergence','offline/post_rmse_m','offline/unflagged25cm_count','result/wall_s','result/commands','result/model_calls'],
 new_videos=0,video_registration='not applicable: no new physics/render/video',ui_verified=False)
(evaluation/'tensorboard-delivery.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
