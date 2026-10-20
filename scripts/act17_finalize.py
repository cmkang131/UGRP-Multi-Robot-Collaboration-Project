"""Compact saved diagnostic outputs on gcp2; no inference, training or physics."""
from collections import Counter, defaultdict
import gzip
import json
import math
from pathlib import Path
import sys

import numpy as np
from act16w_runtime import require_gcp2, frozen_source, sha256
from act17_open_loop import read, quantiles

B = Path('/home/ugrp/ugrp-sim')


def yaw(values):
    # Exact frozen command_delta model evaluated over PERIOD_S=.1; units deg.
    wheels=np.asarray(values[:4]);duration=np.clip(np.asarray(values[4:8])*.15,0,.1)
    a,b,c,d=wheels*duration
    return math.degrees((.0325*150*2*math.pi/60)*(-a+b-c+d)/(4*.1255))


def main():
    require_gcp2(training=True)
    source=frozen_source(Path(__file__).resolve().parents[1])
    output=Path(sys.argv[1]);output.mkdir(parents=True,exist_ok=False)
    root=B/'runs/act17-open-loop-r1'
    full=read(root/'summary.json')
    result={k:full[k] for k in ['schema','status','complete','host','source_sha','rows','units','wall_s','scope']}
    result['derived_source_sha']=source
    result['arms']={}
    for arm,values in full['arms'].items():
        row={k:values[k] for k in ['checkpoint','checkpoint_sha256','history_mode']}
        train_root=B/f'runs/act16w-native-training-r1/{arm}/main'
        log=read(train_root/'progress.jsonl',lines=True)
        row['optimizer_TRAIN_last_logged']=log[-1]
        row['optimizer_TRAIN_last100_logs_mean']={key:float(np.mean([x[key] for x in log[-100:]]))
            for key in ['loss','movement_l1_loss','done_bce_loss','kld_loss'] if all(key in x for x in log[-100:])}
        row['optimizer_TRAIN_log']=dict(path=str(train_root/'progress.jsonl'),sha256=sha256(train_root/'progress.jsonl'))
        row['splits']={}
        for split,data in values['splits'].items():
            stages={k:v for k,v in data['stages'].items() if not k.startswith('phase:')}
            for value in stages.values():
                value['errors']={k:v for k,v in value['errors'].items() if k.startswith(('h0_raw:','h0_projected:','persistence:'))}
            direction=defaultdict(Counter)
            with gzip.open(root/f'{arm}-{split}-frames.jsonl.gz','rt') as stream:
                for line in stream:
                    sample=json.loads(line)
                    truth=yaw(sample['teacher_h0_encoded'])
                    pred=yaw(sample['projected_h0_encoded'])
                    for stage in ['all',sample['stage']]:
                        c=direction[stage]
                        c['rows']+=1
                        if truth!=0:
                            c['teacher_turns']+=1
                            c['opposite' if pred*truth<0 else 'student_stopped' if pred==0 else 'same_direction']+=1
                        elif pred!=0:
                            c['student_turn_teacher_stopped']+=1
            row['splits'][split]=dict(rows=data['rows'],transition_rows=data['transition_rows'],
                prior_z0_eval_loss_sample_weighted=data.get('prior_z0_eval_loss_sample_weighted',data.get('posterior_loss_sample_weighted')),
                stages=stages,issued_rotation_direction=dict(direction))
        result['arms'][arm]=row
    result['loss_name_correction']='original source e64bc1924 labels eval-mode prior-z0 loss as posterior; no posterior/KL calculated in eval. Optimizer log with KL retained separately.'
    (output/'open-loop-summary.json').write_text(json.dumps(result,indent=2)+'\n')
    closed_root=B/'runs/act17-closed-loop-r1'
    full_closed=read(closed_root/'summary.json')
    closed={k:full_closed[k] for k in ['schema','status','complete','source_sha','host','reason_distribution','caveats','funnel']}
    closed['derived_source_sha']=source
    rows=[]
    for original in full_closed['rows']:
        row={k:v for k,v in original.items() if k!='pre_exit_one_second'}
        window=original['pre_exit_one_second']
        row['pre_exit_1s_commands']=[dict(elapsed_SIM_s=v['elapsed_SIM_s'],
            student_yaw_command_deg=v['student_yaw_command_deg'],teacher_yaw_command_deg=v['teacher_yaw_command_deg'],
            teacher_label_valid=v['teacher_label_valid'],teacher_rejection=v['teacher_rejection']) for v in window]
        row['student_abs_yaw_command_deg']=quantiles([abs(v['student_yaw_command_deg']) for v in window])
        row['teacher_abs_yaw_command_deg_available_only']=quantiles([abs(v['teacher_yaw_command_deg']) for v in window if v['teacher_yaw_command_deg'] is not None])
        rows.append(row)
    closed['rows']=rows
    closed['oracle_audit_totals']={k:sum(r['oracle_audit'][k] for r in rows) for k in ['invisible_measurements','held_world_reads']}
    closed['oracle_label_counts']=dict(valid=sum(r['oracle_labels'] for r in rows),held_rejected=sum(r['hold_rejected'] for r in rows),states=sum(r['samples'] for r in rows))
    (output/'closed-loop-summary.json').write_text(json.dumps(closed,indent=2)+'\n')
    table=dict(schema='ugrp.act17.rejection_table.v1',source_sha=source,
        scope='all original student failures plus auditable expert-label availability; no physical outcome changed',
        funnel=closed['funnel'],reason_distribution=closed['reason_distribution'],
        rejections=[dict(reason_category='counterfactual_label_unavailable_in_pre_exit_second',
            reason='original qualified oracle is pre-hover and permanently excludes after any lower-than-startup OPEN issued gripper PWM; no missing labels imputed',
            count=sum(r['valid_teacher_comparisons']==0 for r in rows),blocked_object='not_applicable_label_scope',
            minimum_gap_m=None,minimum_gap_status='not_measured_non_geometric')],
        raw=[dict(path=str(p),sha256=sha256(p)) for p in [root/'summary.json',closed_root/'summary.json']],
        reproduce=['python scripts/act17_open_loop.py --out /home/ugrp/ugrp-sim/runs/act17-open-loop-r1',
            'python scripts/act17_closed_loop.py --out /home/ugrp/ugrp-sim/runs/act17-closed-loop-r1',
            'python scripts/act17_finalize.py '+str(output)])
    (output/'rejection_table.json').write_text(json.dumps(table,indent=2)+'\n')
    inventory=[dict(path=str(p),sha256=sha256(p),bytes=p.stat().st_size) for folder in [root,closed_root,output] for p in folder.glob('*') if p.is_file()]
    (output/'artifact-hashes.json').write_text(json.dumps(inventory,indent=2)+'\n')


if __name__=='__main__':
    main()
