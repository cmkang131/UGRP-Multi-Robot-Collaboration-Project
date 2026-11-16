"""Read only saved own frames/commands; no physics, renderer or eval truth input."""
import base64, collections, hashlib, io, json, pathlib, time, traceback
import numpy as np
from PIL import Image
from harness import zone_s3_no_prior_contract as contract
from harness.zone_s3_no_prior import Runtime, IntegratedTrial, ROBOTS
from harness.zone_pair_highpose_exact_speedups import install
RAW=pathlib.Path('/Users/changmin/projects/ugrp/outputs/s3-no-prior-6c657124-s14201-v142')
OUT=pathlib.Path('/Users/changmin/projects/ugrp/outputs/s3diag-20261009/host-replay')

def write(name,value):
 (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
def rows(p): return [json.loads(l) for l in p.open()]
def canonical(v): return json.dumps(v,sort_keys=True,separators=(',',':'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
start_wall=time.monotonic()
bundle=json.loads((RAW/'bundle.json').read_text())
manifest_before=sha(RAW/'artifacts.sha256.json')
scenario,mapped,sheet=contract.inputs();static=contract.hp.resolve(bundle['map_id'])[0]
frames={r:rows(RAW/f'robots/{r}/frames.jsonl') for r in ROBOTS}
commands={r:rows(RAW/f'robots/{r}/commands.jsonl') for r in ROBOTS}
expected={r:collections.defaultdict(list) for r in ROBOTS}
for r in ROBOTS:
 for q in commands[r][1:]: expected[r][round(q['t'],9)].append({k:v for k,v in q.items() if k!='t'})
_,undo=install('v98-exact-v6')
rt=None; matched=0; matched_commands=0; terminal_at=None
report=dict(schema='ugrp.s3_saved_input_replay.v1',simulation_runs=0,gt_input=False,source_sha=bundle['source_sha'],raw=str(RAW),raw_manifest_sha256=manifest_before)
try:
 rt=Runtime(static,sheet['orders'],contract.ROOT/bundle['calibration'],bundle['calibration_sha256'],seed=bundle['seed'],config=bundle['controller_config'])
 initial={r:{int(k):v for k,v in commands[r][0]['pulses'].items()} for r in ROBOTS}
 start=frames['r1'][0]['sim_time'];rt.initial_commands(start,initial)
 trial=IntegratedTrial(scenario,seed=bundle['seed'],links=rt.links,map_bundle=mapped,horizon_s=start+bundle['case_cap_s'],code_sha=bundle['source_sha'],pair_records=rt.pair.team.records)
 rt.trial=trial;trial.begin(start)
 for i in range(len(frames['r1'])):
  now=frames['r1'][i]['sim_time']; batch={}
  for r in ROBOTS:
   row=frames[r][i];assert row['sim_time']==now
   jpeg=(RAW/row['path']).read_bytes();assert hashlib.sha256(jpeg).hexdigest()==row['sha256']
   obs={k:v for k,v in row.items() if k not in ('path','commanded_servo')}
   obs['image']=base64.b64encode(jpeg).decode()
   batch[r]=(obs,np.asarray(Image.open(io.BytesIO(jpeg)).convert('RGB')))
  rt.on_frames(now,batch);actions=rt.step(now)
  if rt.terminal:
   terminal_at=now;actions=[(r,{'kind':'hold'}) for r in ROBOTS]
  for r in ROBOTS:
   predicted=[a for rid,a in actions if r==rid]; actual=expected[r].pop(round(now,9),[])
   if canonical(predicted)!=canonical(actual):
    write('command-mismatch.json',dict(frame=i,t=now,robot=r,predicted=predicted,actual=actual))
    raise ValueError(f'command mismatch {r} frame {i} SIM {now}')
  for r,a in actions:rt.on_command(r,now,a);matched_commands+=1
  matched+=1
  if i%100==0:print(json.dumps(dict(frames=matched,sim=now,boot=sorted(rt.boot_done),failure=rt.failures)),flush=True)
  if terminal_at is not None:
   assert i==len(frames['r1'])-1
 end=start+json.loads((RAW/'result.json').read_text())['check_sim_s']
 for r in ROBOTS:
  assert expected[r]=={round(end,9):[{'kind':'hold'}]}, expected[r]
  rt.on_command(r,end,{'kind':'hold'})
 report.update(all_control_commands_match=True,terminal_at=terminal_at,failures=rt.failures,boot_done=sorted(rt.boot_done),startup=rt.boot_records,startup_finished_at=rt.boot_finished_at)
 partial=dict(provenance='derived from exact saved-input replay, all control commands matched; not original student record',failures=rt.failures,startup=rt.boot_records,startup_finished_at=rt.boot_finished_at,localizers={},door_yield=dict(events=rt.relay.events,wait_robot_s=rt.wait_robot_s,rounds=rt.relay.round,final_states={r:c.state for r,c in rt.clients.items()}),pair=dict(robots={r:dict(jobs=a.jobs_done,events=a.events) for r,a in rt.pair.actors.items()}))
 errors={}
 for r,own in rt.localizers.items():
  try: partial['localizers'][r]=own.record()
  except Exception:
   errors[r]=traceback.format_exc()
   partial['localizers'][r]=dict(state=own.state,failure=own.failure,poses=own.pose_log,events=own.events,commands=own.commands)
 write('replayed-student-partial.json',partial)
 for name,producer in [('runtime',rt.record),('trial',lambda:trial.finish(end))]:
  try: write(f'replayed-{name}.json',producer())
  except Exception: errors[name]=traceback.format_exc()
 write('record-errors.json',errors)
 report['record_errors']=errors
except Exception:
 report.update(all_control_commands_match=False,error=traceback.format_exc())
finally:
 if rt:rt.close()
 undo()
 report.update(matched_frames_per_robot=matched,matched_control_commands=matched_commands,replay_wall_s=time.monotonic()-start_wall,raw_manifest_unchanged=sha(RAW/'artifacts.sha256.json')==manifest_before)
 write('replay-verification.json',report)
 print(json.dumps({k:v for k,v in report.items() if k not in ('record_errors','startup')},ensure_ascii=False),flush=True)
