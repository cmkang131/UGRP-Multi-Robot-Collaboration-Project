"""ACT18 TRAIN4 stop-onset/posture table + stop/align frame montages (raw EVM data)."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

VM_BASE=Path('/home/ugrp/ugrp-sim/runs/act18')
DATASET=Path('/home/ugrp/ugrp-sim/runs/act17-v7/dataset-r1')
PWM_KEYS=('1','3','4','5','6')


def font(size=12):
    try:return ImageFont.load_default(size=size)
    except TypeError:return ImageFont.load_default()


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).open()]


def teacher_phases(seed):
    samples=json.loads((DATASET/str(seed)/'samples.json').read_text())
    phases=[]
    for row in samples:
        key=(row['stage'],row['teacher_phase'])
        if not phases or phases[-1]['stage']!=key[0] or phases[-1]['phase']!=key[1]:
            phases.append(dict(stage=key[0],phase=key[1],start_t=row['t'],end_t=row['t']))
        else:
            phases[-1]['end_t']=row['t']
    return phases


def analyse_world(actions,index,physics):
    wheels=[];pwm=[];done=[];skills=[]
    for row in actions:
        action=row['actions'][index];command=action['command']
        wheels.append([float(x) for x in command['wheels']])
        pwm.append([int(command['pwm'][key]) for key in PWM_KEYS])
        done.append(bool(action.get('done')));skills.append(row['skills'][index])
    ticks=len(wheels)
    final_pwm=pwm[-1];final_wheels=wheels[-1]
    def last_change(channels,threshold):
        idx=[]
        for i in range(1,ticks):
            if any(abs(pwm[i][c]-pwm[i-1][c])>=threshold for c in channels):idx.append(i)
        return idx[-1] if idx else None
    base_last=[i for i in range(ticks) if any(abs(x)>0.01 for x in wheels[i])]
    base_last=base_last[-1] if base_last else None
    arm_last=last_change([0,1,2],3)   # pwm keys 1,3,4: lift/arm servos
    finger_last=last_change([3,4],10) # pwm keys 5,6: gripper fingers
    close_onset=None
    for i in range(1,ticks):
        if abs(pwm[i][3]-pwm[i-1][3])>=100 or abs(pwm[i][4]-pwm[i-1][4])>=100:
            close_onset=i;break
    # last tick at which any wheel command or servo PWM still differs from the
    # final held pose beyond sensor/rounding noise
    last_moving=max([i for i in range(ticks)
                     if any(abs(wheels[i][c]-final_wheels[c])>0.01 for c in range(4))
                     or any(abs(pwm[i][c]-final_pwm[c])>2 for c in range(5))],default=0)
    # physical body motion from the evaluation-only per-tick score stream
    speeds=[(e['t'],e['speed']) for e in physics if e.get('speed') is not None]
    moving=[t for t,s in speeds if s and s>0.005]
    moving_loose=[t for t,s in speeds if s and s>0.0005]
    physical_stop=round(moving[-1],2) if moving else None
    physical_stop_loose=round(moving_loose[-1],2) if moving_loose else None
    path_m=round(sum((s or 0) for _,s in speeds)*0.1,3)
    lift_like=[e for e in physics if e.get('lift_success') or e.get('max_stable_lift_s',0)>0]
    return dict(ticks=ticks,
        command_settle_sim_s=round((last_moving+1)*0.1+1.7,2),
        physical_stop_sim_s=physical_stop,
        physical_stop_loose_sim_s=physical_stop_loose,
        static_tail_ticks=ticks-(last_moving+1),
        base_last_move_sim_s=round(base_last*0.1+1.7,2) if base_last is not None else None,
        arm_last_change_sim_s=round(arm_last*0.1+1.7,2) if arm_last is not None else None,
        finger_last_change_sim_s=round(finger_last*0.1+1.7,2) if finger_last is not None else None,
        gripper_close_onset_sim_s=round(close_onset*0.1+1.7,2) if close_onset is not None else None,
        final_command=dict(wheels=final_wheels,pwm=dict(zip(PWM_KEYS,final_pwm))),
        last100_ranges=dict(
            pwm={k:max(p[i] for p in pwm[-100:])-min(p[i] for p in pwm[-100:]) for i,k in enumerate(PWM_KEYS)},
            wheels=[max(w[i] for w in wheels[-100:])-min(w[i] for w in wheels[-100:]) for i in range(4)]),
        path_length_m=path_m,
        gripper_pwm_distinct=len({tuple(p[3:]) for p in pwm}),
        gripper_pwm_range=[max(p[3] for p in pwm)-min(p[3] for p in pwm),max(p[4] for p in pwm)-min(p[4] for p in pwm)],
        done_issued=any(done),skill=[skills[0],skills[-1]],
        speed_max=round(max((s or 0) for _,s in speeds),3) if speeds else None,
        min_clearance_m=round(min(e.get('min_z',0) for e in physics),5) if physics else None,
        max_tilt_deg=round(max(e.get('tilt_deg',0) for e in physics),2) if physics else None,
        finger_force_max=round(max(max(e.get('finger_forces') or [0,0]) for e in physics),3) if physics else None,
        finger_force_at_end=(physics[-1].get('finger_forces') if physics else None),
        physical_lift_seen=bool(lift_like))


def montage(rows,frame_paths,out,labeler):
    cell=(160,120);cols=len(frame_paths[0])
    image=Image.new('RGB',(cell[0]*cols,cell[1]*len(rows)),(16,16,16));draw=ImageDraw.Draw(image)
    for r,row in enumerate(rows):
        y=r*cell[1]
        for c,frame in enumerate(frame_paths[r]):
            with Image.open(frame) as source:
                image.paste(source.convert('RGB').resize(cell,Image.BILINEAR),(c*cell[0],y))
        draw.rectangle([0,y,300,y+16],fill=(0,0,0));draw.text((2,y+1),labeler(row),fill=(230,230,60),font=font())
    out.parent.mkdir(parents=True,exist_ok=True);image.save(out)
    return dict(path=str(out),sha256=hashlib.sha256(out.read_bytes()).hexdigest(),bytes=out.stat().st_size)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--enabled',action='store_true')
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if not a.enabled:p.error('faildiag default OFF')
    a.out.mkdir(parents=True,exist_ok=False)
    report=dict(schema='ugrp.act18.train4_faildiag.v1',stage='train4',candidates={})
    for candidate in ('R8','R100'):
        stage=VM_BASE/'finish-r3'/(candidate+'-train')
        summary=json.loads((stage/'summary.json').read_text())
        if not summary.get('complete'):raise ValueError('complete stage required')
        rows=[];stop_frames=[];align_frames=[]
        for evaluation in map(Path,summary['finished']):
            plans=json.loads((evaluation/'initial-plans.json').read_text())['episodes']
            actions=read_jsonl(evaluation/'actor-actions.jsonl')
            owner=read_jsonl(evaluation/'owner/evaluation-only.jsonl')
            for index,plan in enumerate(plans):
                physics=[e for e in owner if e.get('world')==index and e.get('speed') is not None]
                metric=analyse_world(actions,index,physics)
                metric.update(seed=plan['seed'],kind=plan['kind'],role=plan.get('role'),
                    start_to_cargo_m=plan.get('start_to_cargo_m'),cargo_pose_m=plan.get('cargo_pose_m'))
                rgbdir=evaluation/'actor-inputs'/('world-%03d'%index)/'rgb/r1'
                frames=sorted(rgbdir.glob('*.jpg'))
                stop_ref=metric['physical_stop_sim_s'] or metric['physical_stop_loose_sim_s'] or metric['command_settle_sim_s']
                stop_tick=int(round(((stop_ref)-1.7)/0.1))
                start=max(0,min(stop_tick-10,len(frames)-20))
                stop_frames.append([frames[start+i] for i in range(20)])
                align_frames.append([frames[min(len(frames)-1,int(round((t-1.7)/0.1)))] for t in range(8,18)])
                phases=teacher_phases(plan['seed'])
                stop_ref=metric['physical_stop_sim_s'] or metric['physical_stop_loose_sim_s'] or metric['command_settle_sim_s']
                metric['stop_reference_sim_s']=stop_ref
                at=[q for q in phases if q['start_t']<=stop_ref<=q['end_t']]
                metric['teacher_phase_at_physical_stop']=at[0] if at else None
                metric['teacher_close']=next((q for q in phases if q['stage']=='grasp' and q['phase']=='close'),None)
                metric['teacher_remaining_action_s']=round(metric['teacher_close']['end_t']-stop_ref,2) if metric['teacher_close'] else None
                metric['teacher_total_demo_s']=round(phases[-1]['end_t'],1)
                metric['stop_window_ticks']=[start,start+19]
                rows.append(metric)
        rows.sort(key=lambda r:r['seed'])
        stop_png=montage(rows,stop_frames,a.out/(candidate+'-stop-window-10hz.png'),
            lambda r:'%d stop@%ss kind=%s'%(r['seed'],r['stop_reference_sim_s'],r['kind']))
        align_png=montage(rows,align_frames,a.out/(candidate+'-align1hz.png'),
            lambda r:'%d t=8..17s kind=%s'%(r['seed'],r['kind']))
        report['candidates'][candidate]=dict(stage_dir=str(stage),rows=rows,
            stop_montage=stop_png,align_montage=align_png)
    (a.out/'faildiag.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(out=str(a.out),candidates={c:dict(rows=len(v['rows']),
        stop_sha=v['stop_montage']['sha256'],align_sha=v['align_montage']['sha256']) for c,v in report['candidates'].items()})))


if __name__=='__main__':main()
