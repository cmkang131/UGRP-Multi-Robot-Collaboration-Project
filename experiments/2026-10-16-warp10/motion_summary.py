"""CPU-only prefix exposure funnel. Issued phases are not physical success."""
import argparse,collections,hashlib,json,gzip,subprocess
from pathlib import Path

def existing(p):
    for candidate in (p,Path(str(p)+'.zst'),Path(str(p)+'.gz')):
        if candidate.exists():return candidate
    return p
def decoded(p):
    if p.suffix=='.zst':return subprocess.check_output(['zstd','-qdc',str(p)])
    if p.suffix=='.gz':return gzip.decompress(p.read_bytes())
    return p.read_bytes()
def read(p):return json.loads(decoded(existing(p)))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);q=read(a.raw/'queue.json');parent=read(a.raw/'summary.json') if (a.raw/'summary.json').exists() else {'status':'RUNNING'}
    note=a.raw.parent.parent/(a.raw.parent.name+'-supervisor-stop.json')
    supervisor=read(note) if note.exists() else None
    worlds=[];source={};raw_status=collections.Counter();reasons=collections.Counter();phase_ticks=collections.Counter()
    for i,run in enumerate(q['runs']):
        raw=a.raw/f'world-{i:03d}'/'raw';trace=existing(raw/'teacher-commands.jsonl')
        if not trace.exists():raise FileNotFoundError('original command trace missing: '+str(raw))
        payload=decoded(trace);text=payload.decode()
        manifest=read(raw/'manifest.json')
        entry=manifest[str(trace.relative_to(raw))]
        if entry.get('decoded_sha256',entry['sha256'])!=hashlib.sha256(payload).hexdigest():raise ValueError('decoded trace hash mismatch')
        rows=[json.loads(line) for line in text.splitlines()]
        if trace.exists():source[str(trace)]=sha(trace)
        result=read(raw/'result.json') if existing(raw/'result.json').exists() else {'status':'RUNNING'}
        raw_status[result['status']]+=1;phases={r['phase'] for r in rows};phase_ticks.update(r['phase'] for r in rows)
        error=result.get('error_type');interpretation=result['status']
        if error=='GeneratorExit':
            interpretation='planned_diagnostic_close' if parent['status'] in ('FIRST30_COMPLETE','SPEED_GATE_FAIL','PROFILE_COMPLETE') else 'parent_abort_then_generator_close'
        if supervisor and error in ('GeneratorExit','KeyboardInterrupt'):interpretation='supervisor_cpu_diagnosis_incomplete'
        if error and interpretation not in ('planned_diagnostic_close','supervisor_cpu_diagnosis_incomplete'):reasons[('HOST_ERROR',error,result.get('error') or 'exception text empty; error_type retained')]+=1
        audit=result.get('input_audit')
        frames=sum(bool(r.get('map_pose',{}).get('own_frame',{}).get('sha256')) for r in rows)
        commands=sum(all(k in r.get('command',{}) for k in ('wheels','pwm','t')) for r in rows)
        answer_yes=any(r.get('rgb_confirmation',{}).get('answer')=='yes' and r['phase'] in ('verify_lift','hold','carry_prepare','carry_to_zone') for r in rows)
        worlds.append(dict(world=i,seed=run['seed'],raw=str(raw),status=result['status'],error_type=error,interpretation=interpretation,
            trace_N=len(rows),rgb_hash_N=frames,issued_command_N=commands,phases=sorted(phases),
            first_t=rows[0]['t'] if rows else None,last_t=rows[-1]['t'] if rows else None,
            input_audit=audit,own_rgb_holding_hypothesis=answer_yes,
            physical_success=result.get('physical_success'),place_success=result.get('zone_placement_success'),
            cap_end=result.get('cap_end',False),failure_buffer=result.get('failure_rgb_buffer')))
    selected=set(range(len(worlds)));stages=[]
    # Source phase names come from SoloTeacher.update. These are exposure
    # milestones only. Unreached prefix stages are not failed mission trials.
    checks=[('native_setup',lambda w:(Path(w['raw'])/'scene.json').exists()),
        ('control_trace_started',lambda w:w['trace_N']>0),
        ('all_trace_own_rgb_hashes_present',lambda w:w['trace_N']>0 and w['rgb_hash_N']==w['trace_N']),
        ('all_trace_commands_present',lambda w:w['issued_command_N']==w['trace_N']),
        ('approach_or_align_phase_seen',lambda w:bool(set(w['phases'])&{'approach','align'})),
        ('close_phase_seen',lambda w:'close' in w['phases']),
        ('lift_phase_seen',lambda w:'lift' in w['phases']),
        ('carry_phase_seen',lambda w:'carry_to_zone' in w['phases']),
        ('destination_place_phase_seen',lambda w:bool(set(w['phases'])&{'zone_place_view','zone_place_advance'})),
        ('physical_place_reported',lambda w:w['place_success'] is True),
        ('physical_complete_reported',lambda w:w['physical_success'] is True)]
    stages.append(dict(stage='requested_worlds',cumulative_pass_n=len(selected),rejected_n=0,worlds=sorted(selected)))
    for name,check in checks:
        passed={w['world'] for w in worlds if w['world'] in selected and check(w)};removed=selected-passed
        stages.append(dict(stage=name,cumulative_pass_n=len(passed),rejected_n=len(removed),worlds=sorted(passed),
            rejection_scope='not observed in diagnostic prefix, not a mission-failure assertion',
            reason_category='prefix_stage_not_observed' if removed else None,blocked_object=name if removed else None,
            minimum_gap_m=None,gap_scope='exposure_not_physical_gap'))
        selected=passed
    clean=[w for w in worlds if w['input_audit'] is not None and w['input_audit'].get('invisible_measurements')==0 and w['input_audit'].get('held_world_reads')==0]
    value=dict(status=parent['status'],source_sha=q['source_sha'],raw=str(a.raw),supervisor_note=supervisor,
        scope='teacher diagnostic prefix only; no LLM, ACT student, full-task, held-travel or physics-equivalence qualification',
        worlds=worlds,world_exposure_funnel=stages,raw_status_counts=dict(raw_status),phase_tick_distribution=dict(phase_ticks),
        frame_funnel=[dict(stage='trace_ticks',cumulative_pass_n=sum(w['trace_N'] for w in worlds),rejected_n=0),
            dict(stage='own_rgb_hash_recorded',cumulative_pass_n=sum(w['rgb_hash_N'] for w in worlds),rejected_n=sum(w['trace_N']-w['rgb_hash_N'] for w in worlds))],
        event_funnel=[dict(stage='trace_ticks',cumulative_pass_n=sum(w['trace_N'] for w in worlds),rejected_n=0),
            dict(stage='issued_command_recorded',cumulative_pass_n=sum(w['issued_command_N'] for w in worlds),rejected_n=sum(w['trace_N']-w['issued_command_N'] for w in worlds))],
        input_audit_worlds=dict(measured=len([w for w in worlds if w['input_audit'] is not None]),clean=len(clean),
            warning='zero counters cover only executed input paths; check phase exposure before claiming held/transport audit'),
        error_distribution=[dict(category=c,error_type=t,reason=r,n=n,blocked_object='world_controller',minimum_gap_m=None,gap_scope='runtime_not_gap') for (c,t,r),n in reasons.items()],
        cap_end=sum(bool(w['cap_end']) for w in worlds),independent_initial_cases=len({r['seed'] for r in q['runs']}),
        explicit_replica_worlds=len(q['runs'])-len({r['seed'] for r in q['runs']}),independent_complete_task_trials=0,
        source_sha256=source,reproduction=['python',__file__,'--raw',str(a.raw),'--output',str(a.output)])
    (a.output/'motion-summary.json').write_text(json.dumps(value,indent=2)+'\n')
if __name__=='__main__':main()
