"""Read-only host-side record funnel; running/pending are never failures."""
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from act16w_runtime import require_gcp2,frozen_source,sha256
B=Path('/home/ugrp/ugrp-sim')


def read(p,lines=False):
    if p.exists():data=p.read_bytes()
    elif Path(str(p)+'.zst').exists():data=subprocess.check_output(['zstd','-dc',str(p)+'.zst'])
    else:return None
    try:return [json.loads(x) for x in data.splitlines() if x.strip()] if lines else json.loads(data)
    except json.JSONDecodeError:return None  # live controller writes are not all atomic


def main():
    host=require_gcp2();source=frozen_source(ROOT);batch=B/'runs/act16w-resume2-data-r2'
    selection=read(ROOT/'experiments/2026-10-16-act16w/resume2/record-selection.json')
    plans=read(B/'runs/act16w-resume2-record-references/plans.json')['episodes'];locations={}
    for seed in (86821,86822):locations[seed]=(B/f'runs/act16w-resume2-pilot-{seed}',0)
    for group in batch.glob('group-*'):
        launch=read(group/'launch.json')
        if launch:
            for world,index in enumerate(launch['world_indices']):locations[plans[index]['seed']]=(group,world)
    rows=[]
    for seed in selection['selected_seeds']:
        row=dict(seed=seed,status='pending',SIM_s=0.,native_audit=False)
        if seed in locations:
            root,i=locations[seed];original=root/'controller'/f'world-{i:03d}';progress=read(root/'controller/progress.json');result=read(original/'result.json');row['raw']=str(root);row['world']=i
            if progress:row['SIM_s']=progress['ticks'][i]*.1
            if result and all(k in result for k in ('cap_end','physical_success','input_audit')):
                commands=read(original/'teacher-commands.jsonl',True) or []
                command_complete=bool(commands and commands[-1]['phase']=='complete')
                row.update(status='cap_end' if result['cap_end'] else 'success' if result['physical_success'] and command_complete else 'teacher_failure',physical_success=result['physical_success'],command_complete=command_complete,input_audit=result['input_audit'],original_result_sha256=sha256(original/'result.json' if (original/'result.json').exists() else original/'result.json.zst'))
                audit=read(root/'dataset-audit.json') or read(root/'native-pilot-check.json')
                row['native_audit']=bool(audit and audit['passed'] and any(w['seed']==seed and w['world']==i for w in audit['worlds']))
                if row['status']!='success':row['reason']=result.get('reason') or result.get('teacher',{}).get('command_result') or 'physical_or_command_sequence_gate_failed'
            else:
                dispatch=read(batch/'summary.json');failed={x['group'] for x in dispatch.get('finished',[]) if x['exit_code']} if dispatch else set()
                row['status']='HOST_ERROR' if root.name.startswith('group-') and int(root.name[-2:]) in failed else 'running'
                if row['status']=='HOST_ERROR':row['reason']='wrapper_exit_nonzero_before_final_world_result'
        rows.append(row)
    counts=dict(Counter(x['status'] for x in rows));provisional=sum(x['status']=='success' for x in rows);confirmed=sum(x['status']=='success' and x['native_audit'] for x in rows)
    rejected=[dict(seed=r['seed'],category=r['status'],reason=r.get('reason',r['status']),blocking_object='not_attributed_before_playback',minimum_gap_m=None,minimum_gap_status='not measured; no geometric cause claim',raw=r.get('raw')) for r in rows if r['status'] in ('teacher_failure','cap_end','HOST_ERROR')]
    now=datetime.now(timezone.utc);first=datetime.fromisoformat('2026-10-16T05:47:00.019842+00:00');elapsed=(now-first).total_seconds()
    report=dict(status='running' if any(x['status'] in ('pending','running') for x in rows) else 'complete',observed_utc=now.isoformat(),source_sha=source,host=host,N_requested=40,counts=counts,provisional_success_n=provisional,confirmed_native_success_n=confirmed,
        independent_recording_gate_passed=confirmed>=38 and not counts.get('HOST_ERROR') and sum(x['status'] in ('pending','running') for x in rows)==0,
        funnel=[dict(gate='predeclared_starts',passed=40,rejected=0),dict(gate='started',passed=len(locations),rejected=0,pending=40-len(locations)),dict(gate='terminal_records',passed=sum(x['status'] not in ('pending','running') for x in rows),rejected=0,unfinished=sum(x['status'] in ('pending','running') for x in rows)),dict(gate='provisional_physical_and_command_success',passed=provisional,rejected=sum(x['status'] in ('teacher_failure','cap_end','HOST_ERROR') for x in rows)),dict(gate='native_capture_audited_success',passed=confirmed,rejected=0,pending_native_audit=provisional-confirmed)],
        rejections=rejected,rows=rows,raw=str(batch),reproduce='python3 '+str(Path(__file__)),task_elapsed_L4_wall_s=elapsed,task_remaining_wall_s=max(0,28800-elapsed),shared_VM_wall_cost_upper_estimate_USD=elapsed/3600*1.096,cost_scope='rate estimate for whole shared VM window, not billing or additive task charge',training=read(B/'runs/act16w-resume2-training/summary.json'))
    out=B/'runs/act16w-resume2-admission/progress-latest.json';tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(out)
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','training')}))


if __name__=='__main__':main()
