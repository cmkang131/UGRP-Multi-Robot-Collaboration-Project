"""Summarize completed expert-state predictions; no model/physics/render call."""
import argparse
from collections import defaultdict
import gzip
import json
from pathlib import Path
import sys

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256
from act17_data import Dataset,library,read
from act17_open_loop import action_errors,quantiles

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['audit','dataset','out']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();host=require_gcp2(training=True);source=frozen_source(ROOT)
    audit=read(a.audit)
    if not audit.get('complete') or audit.get('status')!='complete' or set(audit['arms'])!={'M','F','S'}:
        raise ValueError('all completed M/F/S expert-state predictions required')
    library()
    from harness import grasp_act_contract as c
    data=Dataset(a.dataset,'validation');a.out.mkdir(parents=True,exist_ok=False)
    persistence=defaultdict(lambda:defaultdict(list))
    for index,(j,i) in enumerate(data.index):
        state=data.shards[j]['state'][i]
        # Raw context stores13 command components followed by its age. This is
        # an offline last-command reference, not a proposed rollout controller.
        last=np.r_[state[(c.HISTORY-1)*14:(c.HISTORY-1)*14+13],0.]
        truth=data.shards[j]['action'][i,0]
        for key,values in action_errors(last,truth).items():persistence[data.metadata[index]['stage']][key].extend(values.tolist())
    report=dict(source_sha=source,host=host,complete=True,physics_steps=0,training_updates=0,
        audit=dict(path=str(a.audit),sha256=sha256(a.audit)),arms={},
        last_issued_command_reference={stage:{k:quantiles(v) for k,v in units.items()} for stage,units in persistence.items()},
        scope='expert-state action error and uncalibrated completion-score confusion; no task-success or causal-failure claim',
        notes=['TRAIN is actual optimizer log including posterior/KL; VAL is prior-z0 eval without KL, so objectives differ',
               'completion uses the existing frozen decode_action output, not a new threshold',
               'last issued command is a numerical persistence reference, not an executable fallback'])
    lines=['# v7 R1 개루프 오차', '', '모두 VAL 교사 상태에서의 발행 명령 오차다. 실제 이동·성공률이 아니다.', '',
        '|후보|실제 TRAIN 마지막100 로그 평균|VAL prior-z0 손실|', '|---|---:|---:|']
    for candidate,arm in audit['arms'].items():
        lines.append(f"|{candidate}|{arm['actual_optimizer_TRAIN_last100']['loss_mean']:.6f}|{arm['prior_z0_VAL_loss_sample_weighted']['total_loss']:.6f}|")
    lines+=['', 'TRAIN은 posterior/KL 포함 optimizer 목적, VAL은 prior-z0/KL0이므로 같은 손실로 직접 비교하지 않는다.', '',
        '|후보|구간|프레임|바퀴 median/p90 (full-scale)|펄스 median/p90 (ms)|서보 median/p90 (PWM counts)|집게 median/p90 (PWM counts)|',
        '|---|---|---:|---:|---:|---:|---:|']
    units=['wheel_full_scale','pulse_ms','servo_PWM_counts','gripper_PWM_counts']
    for candidate,arm in audit['arms'].items():
        confusion=defaultdict(lambda:defaultdict(int))
        path=a.audit.parent/(candidate+'-VAL-frames.jsonl.gz')
        with gzip.open(path,'rt') as stream:
            n=0
            for index,line in enumerate(stream):
                row=json.loads(line)
                if row['sample_id']!=data.metadata[index]['sample_id']:raise ValueError('saved frame ordering differs')
                truth=np.asarray(row['teacher_h0_encoded']);pred=np.asarray(row['projected_h0_encoded'])
                value=confusion[row['stage']];positive=bool(truth[-1]);chosen=bool(pred[-1])
                value['frames']+=1;value['teacher_done_positive']+=int(positive)
                value['true_positive']+=int(positive and chosen);value['false_positive']+=int(not positive and chosen)
                value['false_negative']+=int(positive and not chosen)
                value['wheel_components']+=4;value['teacher_nonzero_wheels']+=int(np.count_nonzero(truth[:4]))
                value['student_stopped_teacher_moves']+=int(np.sum((pred[:4]==0)&(truth[:4]!=0)))
                value['student_moves_teacher_stopped']+=int(np.sum((pred[:4]!=0)&(truth[:4]==0)))
                value['opposite_wheel_sign']+=int(np.sum(pred[:4]*truth[:4]<0));n+=1
        if n!=len(data):raise ValueError('all VAL frames required')
        report['arms'][candidate]=dict(frame_prediction_sha256=sha256(path),completion_and_wheel_confusion=dict(confusion))
        for stage in ['approach','alignment','grasp','release']:
            value=arm['stages'][stage];cells=[]
            for unit in units:
                q=value['errors']['h0_projected:'+unit];cells.append(f"{q['median']:.4f}/{q['p90']:.4f}")
            lines.append('|'+candidate+'|'+stage+'|'+str(value['rows'])+'|'+'|'.join(cells)+'|')
    lines+=['', '원본: `'+str(a.audit)+'`。기존 actuator projection 후 h0 기준이다. raw h0와 유효 chunk 전체는 원본 JSON에 별도로 보존한다.']
    (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    (a.out/'error-table.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(complete=True,models=3,frames_per_model=len(data),physics_steps=0,training_updates=0)))


if __name__=='__main__':main()
