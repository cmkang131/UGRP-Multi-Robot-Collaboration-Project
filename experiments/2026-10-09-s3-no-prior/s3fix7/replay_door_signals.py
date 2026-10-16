"""Open-loop protocol probe using saved own poses/issued servo, not GT."""
import argparse,json
from pathlib import Path
from types import SimpleNamespace as NS
from harness.zone_s3_door_lease import Board,Client,ROBOTS

def main():
 p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 record=json.loads((a.raw/'student_record.json').read_text());static=json.loads((a.raw/'inputs/static_map.json').read_text())
 passage=next(x for x in static['passages'] if x['id']=='door_1')
 board=Board();clients={};indexes={r:0 for r in ROBOTS};commands={}
 for rid in ROBOTS:
  commands[rid]=[json.loads(x) for x in (a.raw/'robots'/rid/'commands.jsonl').open()]
  own=NS(last_report=None,servo={},pose=NS(provider=NS(loc=NS(_pf=NS(load=NS(loaded=False))))))
  clients[rid]=Client(rid,own,board,passage,NS(offset=(0.,0.,0.),envelope=(0.,0.)),NS(note=lambda *a,**kw:None))
 counts={r:dict(request_frames=0,blocked_frames=0,permitted_frames=0) for r in ROBOTS};samples=[]
 first=record['startup_finished_at'];n=0
 for rows in zip(*(record['localizers'][r]['poses'] for r in ROBOTS)):
  now=rows[0]['t']
  if now<first:continue
  signals=[]
  for rid,row in zip(ROBOTS,rows):
   c=clients[rid];j=indexes[rid]
   while j<len(commands[rid]) and commands[rid][j]['t']<=now+1e-8:
    cmd=commands[rid][j]
    if cmd['kind']=='initial_servo_command':c.own.servo.update({int(k):v for k,v in cmd['pulses'].items()})
    elif cmd['kind']=='arm':c.own.servo[cmd['servo_id']]=cmd['pulse']
    elif cmd['kind']=='look':c.own.servo[6]=cmd['pan_pulse']
    j+=1
   indexes[rid]=j
   c.own.last_report=NS(t_est=row['t_est'],initialized=True,x_m=row['x'],y_m=row['y'],yaw_rad=row['yaw'],std_xy_m=row['std_xy_m'],std_yaw_rad=row['std_yaw_rad'])
   signals.append(c.offer(now))
  board.exchange(signals,now)
  for rid in ROBOTS:
   c=clients[rid];c.grant=board.epoch if board.owner==c.team else -1
   counts[rid]['request_frames']+=c.request
   counts[rid]['blocked_frames']+=not c.permits()
   counts[rid]['permitted_frames']+=c.permits()
  if n==0:samples.append(dict(sim_s=now,owner=board.owner,signals=[vars(s) for s in signals]))
  n+=1
 result=dict(scope='saved own pose/servo signals; open-loop protocol only; no new motion or closed-loop success',gt_inputs=False,loaded=False,loaded_basis='v151 no grasp or load transition',frames=n,counts=counts,initial=samples,events=board.events)
 with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps(dict(frames=n,counts=counts,events=len(board.events))))
if __name__=='__main__':main()
