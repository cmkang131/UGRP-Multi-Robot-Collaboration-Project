"""Replay port command interpolation without physics; score with separate eval."""
import collections,hashlib,json,math,platform
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from sim.camera_robot_port import CameraRobotPort
from scripts.analyze_reloc11_selfmap import rows
from harness.active_camera import transform

class Robot:
    def __init__(self,pwm):self.servo_command_pulses=dict(pwm)
    def set_motor_commands(self,x):pass
    def set_servo_pulses(self,x):self.servo_command_pulses.update(x)
class World:
    def __init__(self,pwm,start):self.r=Robot(pwm);self.data=SimpleNamespace(time=start)
    def robot(self,rid):return self.r

def main():
    assert platform.node().startswith('ugrp-sim-gcp2')
    root=Path('/home/ugrp/ugrp-sim/runs');reports=[];details=[]
    for n in (1,2,3):
        queue=json.loads((root/f'reloc16-round{n}/queue.json').read_text())
        for task in queue['runs']:
            if task['kind']!='selfmap':continue
            raw=Path(task['raw']);result=json.loads((raw/'result.json').read_text())
            if not result.get('frames'):continue
            commands=rows(raw/'robots/r3/commands.jsonl');frames=rows(raw/'robots/r3/frames.jsonl');trace=rows(raw/'trace.jsonl');servo={round(r['t'],6):r for r in rows(raw/'eval_only/servo.jsonl')}
            initial=commands[0];pwm={int(k):v for k,v in initial['pulses'].items()};start=initial['t'];dt=json.loads((raw/'eval_only/applied.json').read_text())['timestep_s']
            world=World(pwm,start);port=CameraRobotPort(world,'r3',allow_reverse=True,allow_mecanum=True);ci=1;now=start;settled_errors=[];target_replay_errors=[];cuts=[];residuals=[]
            for r,f in zip(trace,frames):
                t=f['sim_time']
                # Tick at the beginning of each physical step, as Base.advance_to.
                while now+dt<=t+1e-8:
                    while ci<len(commands) and commands[ci]['t']<=now+1e-8:
                        c=commands[ci];a={k:v for k,v in c.items() if k!='t'}
                        if a['kind']=='hold':
                            if port._servo_targets:cuts.append(dict(t=c['t'],targets=dict(port._servo_targets),applied=dict(port._servo_applied)))
                            port.hold(now)
                        else:port.apply(a,now)
                        ci+=1
                    world.data.time=now;port.tick(now);now=round(now+dt,9)
                e=servo[round(t,6)];target=e['joints']['6']['target_rad'];requested=int(f['commanded_servo']['6']);predict=math.radians((world.r.servo_command_pulses[6]-1500)/ (2000/180))
                diff=abs(math.degrees(predict-target));target_replay_errors.append(diff)
                error=abs((requested-1500)*.09-math.degrees(e['joints']['6']['q_rad']))
                if r.get('static_registration',{}).get('updated'):settled_errors.append(error)
                details.append(dict(run=task['name'],t=t,requested_pan=requested,effective_setpoint_pan=world.r.servo_command_pulses[6],target_replay_error_deg=diff,requested_vs_actual_pan_error_deg=error,pf_update=bool(r.get('static_registration',{}).get('updated'))))
            def dist(xs):return dict(N=len(xs),**{k:float(v) for k,v in zip(('p50','p95','max'),np.percentile(xs,[50,95,100]))})
            reports.append(dict(run=task['name'],round=n,seed=task['seed'],scene=task['scene'],dt=dt,raw=str(raw),servo_cancel_events=len(cuts),cancel_events=cuts,
                command_replay_vs_evaluator_target_deg=dist(target_replay_errors),pan_error_on_PF_updates_deg=dist(settled_errors),pf_updates_over5deg=sum(e>5 for e in settled_errors),
                scope='predictor reads issued commands and fixed 2000PWM/s port schedule only; evaluator joints used only for errors'))
    out=root/'reloc17-investigation';(out/'servo-audit.json').write_text(json.dumps(dict(analysis_host='gcp2',runs=reports),indent=2)+'\n')
    import csv
    with (out/'servo-audit-frames.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(details[0]));w.writeheader();w.writerows(details)
    print(json.dumps([{k:v for k,v in r.items() if k not in ('cancel_events','scope')} for r in reports]))

if __name__=='__main__':main()
