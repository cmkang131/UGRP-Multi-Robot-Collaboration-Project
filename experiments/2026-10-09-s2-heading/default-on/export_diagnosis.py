import json,pathlib,hashlib,urllib.request,urllib.parse,math
from scripts.tensorboard_tools.export import convert
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
BASE=pathlib.Path('/Users/changmin/projects/ugrp/outputs'); DEST=BASE/'s2-heading-v145-diagnosis';TB=BASE/'tensorboard/1009-heading-diagnosis'
SRC=pathlib.Path('experiments/2026-10-09-s2-heading/default-on').resolve()
assert not TB.exists() and not DEST.exists()
DEST.mkdir(); det=json.loads((SRC/'s1068-detections.json').read_text()); ev=json.loads((SRC/'s1068-pose-evaluation.json').read_text())['rows']
source=DEST/'analysis.json';source.write_text(json.dumps(dict(detections=det,evaluation=ev),indent=2)+'\n');expected=[]
for condition,name,t in [('baseline','s2-realism-99d81d8c-s1068-v141-graduation',85.),('heading','s2-heading-b60acdca-s1068-v143',187.9)]:
 q=next(x for x in det[name] if x['t']==t);e=next(x for x in ev if x['run']==name and x['t']==t)
 metrics={'offline/rgb_detections':len(q['detections']),'offline/slot_accepted':sum(d['slot_accept'] for d in q['detections']),'offline/cyan_mask_pixels':q['mask_pixels'],'offline/pose_xy_error_m':e['xy_error_m'],'offline/pose_yaw_error_abs_deg':abs(e['yaw_error_deg']),'offline/bottom_row_px':q['mask_bounds'][3]}
 view=DEST/('s1068-'+condition);view.mkdir()
 value=dict(derived_view_only=True,condition=condition,policy='v141 off' if condition=='baseline' else 'v143 heading',case='s1068-visible-target',model_calls=0,source_sha='99d81d8c9cbc8dee1cc21462d25a1c81f65de9f5' if condition=='baseline' else 'b60acdca6e1c0c477d650b47717b84edb3f08a06',scope='Saved single-frame diagnostic, similar target range; not a new physical run or success result',offline_source=dict(path=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest()),offline_scalar_scope='Own RGB detection/slot filter with separate posthoc GT pose error; no GT control',offline_scalars=metrics)
 (view/'result.json').write_text(json.dumps(value,indent=2)+'\n');run='s1068-'+condition;m=convert(view,TB/run,max_images=0)
 acc=EventAccumulator(str(TB/run));acc.Reload()
 for tag,v in metrics.items():assert math.isclose(acc.Scalars(tag)[-1].value,v,rel_tol=1e-6,abs_tol=1e-7)
 expected.append(dict(run='1009-heading-diagnosis/'+run,scalars=metrics))
pins=['offline/rgb_detections','offline/slot_accepted','offline/pose_xy_error_m','offline/pose_yaw_error_abs_deg']
url='http://127.0.0.1:6006/?'+urllib.parse.urlencode(dict(runFilter='^1009-heading-diagnosis/',smoothing=0,pinnedCards=json.dumps([dict(plugin='scalars',tag=t) for t in pins],separators=(',',':'))))+'#timeseries'
rec=dict(snapshot=str(TB),source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),expected=expected,event_scalars_verified=12,url=url,pinned_metrics=pins,hparams_visible_columns=['model_calls'],physics_runs=0,scope='posthoc single-frame diagnostic')
(DEST/'verification.json').write_text(json.dumps(rec,indent=2)+'\n');(SRC/'diagnosis-tensorboard.json').write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps(rec,indent=2))
