"""Three separate stages: synthesize range, own-only estimate, post-seal score."""
from map_replay import *
from collections import Counter,defaultdict
from dataclasses import asdict
CASES={'s1045':'f0bb26e7','s1046':'e619ee57','s1047':'1a2dbf5e'}
DECOMP=BASE/'camera-pose-projection-v1/decomposition'

def generate():
 from harness.ultrasonic_map import expected_range,static_boxes
 from harness.ultrasonic_model import noisy_reading,reading_rng,DEFAULT_SPEC
 dest=OUT/'pitch';dest.mkdir(parents=True,exist_ok=True)
 if any(dest.iterdir()):raise FileExistsError(dest)
 own=load(DECOMP/'own-nominal.json');receipt={}
 for case,code in CASES.items():
  ep=BASE/f's2-realism-{code}-{case}-P1-2-place';truth=rows(ep/'eval_only/trajectory.jsonl');ts=np.array([r['t'] for r in truth])
  static=load(ep/'inputs/static_map.json');boxes=static_boxes(static);measurements=[]
  for i,r in enumerate(own[case]):
   j=int(np.argmin(abs(ts-r['t'])))
   if abs(ts[j]-r['t'])>1e-6:raise ValueError('SYNTHESIS_MISSING_TRUTH')
   q=truth[j];pose=[*q['robot_xyz_m'][:2],q['robot_yaw_rad']]
   expected=expected_range(static,pose,boxes=boxes)
   tick=round(r['t']/DEFAULT_SPEC.period_s)
   measurement=noisy_reading(r['t'],expected.range_m,reading_rng(55000+int(case[1:]),'r3',tick))
   measurements.append(dict(frame_id=r['frame_id'],**measurement.as_dict()))
  dump(dest/(case+'-readings.json'),measurements)
  receipt[case]=dict(readings=sha(dest/(case+'-readings.json')),truth=sha(ep/'eval_only/trajectory.jsonl'),static_map=sha(ep/'inputs/static_map.json'),n=len(measurements))
 dump(dest/'synthetic-sensor.json',dict(inputs=receipt,noise=asdict(DEFAULT_SPEC),qualification='Synthetic static-map ultrasound only; no dynamic object echo and no actual sensor execution. GT consumed only by this emulator.'))
 print('pitch SYNTHETIC SENSOR SEALED',flush=True)


def predict_pitch():
 dest=OUT/'pitch';manifest=load(dest/'synthetic-sensor.json');nominals=load(DECOMP/'own-nominal.json')
 for case in CASES:
  assert sha(dest/(case+'-readings.json'))==manifest['inputs'][case]['readings']
  readings={r['frame_id']:r for r in load(dest/(case+'-readings.json'))}
  contact_path=ROOT/f'outputs/self-map-v3-confidence-v1/{case}/v3_unloaded_extrinsic_v1/contacts.jsonl'
  contacts={r['frame_id']:r for r in rows(contact_path)};records=[];history=defaultdict(list)
  for own in nominals[case]:
   fid=own['frame_id'];pose_key=','.join(str(own['servo'][str(k)]) for k in (3,4,5,6));contact=contacts.get(fid)
   result=dict(accepted=False,reason='no_eligible_own_contact')
   if contact:
    candidates=[]
    for segment in contact['segments']:
     a,b=np.array(segment);v=b-a
     if abs(v[1])<1e-9:continue
     u=-a[1]/v[1]
     if not 0<=u<=1:continue
     point=a+u*v
     if point[0]<=contact['camera_origin'][0]:continue
     normal=np.array([-v[1],v[0]]);normal/=np.linalg.norm(normal)
     if normal[0]<0:normal=-normal
     candidates.append((point[0],point,normal))
    if candidates:
     _,point,normal=min(candidates,key=lambda q:q[0]);origin=contact['camera_origin']
     result=adapter.pitch_sample(None,reading=readings[fid],camera_origin=origin,nominal_ray=np.r_[point,0.]-origin,wall_normal=normal,pitch_bias=adapter.PITCH)
    else:result=dict(accepted=False,reason='no_front_axis_contact')
   if result['accepted']:
    history[pose_key].append(result['pitch_offset_rad'])
    result['causal_median_offset_rad']=float(np.median(history[pose_key]));result['pose_support']=len(history[pose_key])
   records.append(dict(frame_id=fid,t=own['t'],command_pose=pose_key,**result))
  dump(dest/(case+'-prediction.json'),records)
 dump(dest/'prediction-seal.json',dict(files={case:sha(dest/(case+'-prediction.json')) for case in CASES},gt_inputs=False,own_nominal_sha=sha(DECOMP/'own-nominal.json'),contact_sources={case:sha(ROOT/f'outputs/self-map-v3-confidence-v1/{case}/v3_unloaded_extrinsic_v1/contacts.jsonl') for case in CASES}))
 print('pitch OWN ESTIMATE SEALED',flush=True)


def evaluate_pitch():
 dest=OUT/'pitch';seal=load(dest/'prediction-seal.json');reports=[]
 for case in CASES:
  assert sha(dest/(case+'-prediction.json'))==seal['files'][case]
  pred=load(dest/(case+'-prediction.json'));truth={r['frame_id']:r for r in rows(DECOMP/(case+'-frames.jsonl'))};groups=defaultdict(list)
  for p in pred:
   if p['accepted']:
    gt=truth[p['frame_id']];bias=gt['actual_angles_deg'][1]-gt['nominal_angles_deg'][1]
    groups[p['command_pose']].append(dict(**p,actual_offset_deg=bias,error_deg=abs(math.degrees(p['pitch_offset_rad'])-bias),causal_error_deg=abs(math.degrees(p['causal_median_offset_rad'])-bias)))
  stats=[]
  for key,values in groups.items():
   estimate=math.degrees(values[-1]['causal_median_offset_rad']);actual=float(np.median([v['actual_offset_deg'] for v in values]));error=abs(estimate-actual)
   stats.append(dict(command_pose=key,n=len(values),predicted_offset_deg=estimate,actual_offset_deg=actual,absolute_error_deg=error,passed=error<=.27,
    single_frame_median_error_deg=float(np.median([v['error_deg'] for v in values])),causal_median_error_deg=float(np.median([v['causal_error_deg'] for v in values])),causal_p95_error_deg=float(np.quantile([v['causal_error_deg'] for v in values],.95))))
  reports.append(dict(case=case,frames=len(pred),eligible=sum(p['accepted'] for p in pred),exclusions=dict(Counter(p['reason'] for p in pred if not p['accepted'])),groups=stats,passed=bool(stats) and all(s['passed'] for s in stats)))
 summary=dict(sequences=reports,passed=sum(r['passed'] for r in reports),denominator=3,qualification='Per-command-pose causal median of own-range plane solutions. Actual camera is post-seal evaluation only; synthetic echoes are not a physical calibration result.')
 dump(EXP/'results/pitch.json',summary);print(summary,flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['generate','predict','evaluate']);a=p.parse_args();{'generate':generate,'predict':predict_pitch,'evaluate':evaluate_pitch}[a.mode]()
