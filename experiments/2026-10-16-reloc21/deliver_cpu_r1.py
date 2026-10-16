"""Terminal CPU-only handoff summary. Never submits simulation or model work."""
import collections
import hashlib
import json
from pathlib import Path
import platform
import subprocess

R=Path('/home/ugrp/ugrp-sim/runs');B=R/'reloc21-round1'
def read(p):return p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'])
def obj(p):return json.loads(read(p))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    assert platform.node().startswith('ugrp-sim-gcp2') and (B/'ANALYSIS_DONE').exists()
    full=obj(B/'summary.json');queue=obj(B/'queue.json');out=R/'reloc21-delivery';out.mkdir(exist_ok=True)
    assert len(full['integrity'])==8 and all(x['integrity']['verified'] for x in full['integrity'])
    records=[]
    for x in full['runs']:
        raw=Path(x['raw']);original=obj(raw/'result.json')
        record={k:x[k] for k in ('name','kind','condition','seed','source_sha','raw','status','termination_normalized',
            'raw_terminal_reason','sim_s','place_success','complete','command_sequence_complete','input_audit','errors','phase_metrics',
            'gate_cumulative','acquisition_frame_funnel','acquisition_frame_rejections','travel_coverage','travel_command_time_bins_sim_s',
            'geometry_risk_sim_s','lateral_pulse_ticks','drive_errors','registered_errors','registration_frame_funnel','known_mode_measurement_funnel','error') if k in x}
        record['original_reason']=original.get('termination_reason',original.get('stop_reason'))
        record['original_status']=original['status']
        record['raw_receipts']=[]
        for name in ('result.json','manifest.json','artifacts.sha256.json'):
            p=raw/name
            if not p.exists():p=Path(str(p)+'.zst')
            if p.exists():record['raw_receipts'].append(dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)))
        if x['kind']=='carry':
            c=original['teacher']['carry'];nav=c.get('reloc21_progress') or {}
            record['route_progress']=dict(plans=nav.get('plans'),excluded_slots=nav.get('excluded_slots'),last=nav.get('last'),selection=nav.get('selection'),event_counts=dict(collections.Counter(e['event'] for e in nav.get('events',[]))))
            record['estimated_remaining_direct_m']=x.get('travel_coverage',{}).get('estimated_remaining_direct_m')
            record['destination']={k:v for k,v in c.get('destination_visual_acquire',{}).items() if k not in ('events','last')}
            record['destination_last']=c.get('destination_visual_acquire',{}).get('last')
            record['route_funnel']=(c.get('reloc20_motion',{}).get('footprint') or {}).get('plan_funnel')
            record['route_rejections']=(c.get('reloc20_motion',{}).get('footprint') or {}).get('rejections')
            record['visual_stall_reasons']=x.get('visual_stall_frame_reasons')
        records.append(record)
    carry=[x for x in records if x['kind']=='carry'];audits=[x.get('input_audit') for x in records]
    assert all(audits)
    cohorts=[]
    for condition in ('baseline','progress','complete'):
        c=[x for x in carry if x['condition']==condition]
        cohorts.append(dict(condition=condition,N=len(c),place=sum(x.get('place_success') is True for x in c),
            complete=sum(x.get('complete') is True for x in c),
            authored_arrival=sum(x['gate_cumulative']['authored_arrival'] for x in c),
            colour_acquired=sum(x['destination'].get('acquired_t') is not None for x in c),
            termination_distribution=dict(collections.Counter(x['termination_normalized'] for x in c))))
    summary=dict(schema='ugrp.reloc21.cpu_r1_handoff.v1',status='NOT_READY',handoff='CPU_R1_DONE',
        source_sha=queue['source_sha'],analysis_script_sha256=sha(Path(__file__)),backend='C MuJoCo3.12 CPU',host='gcp2/n4-highcpu-64',
        pr='https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/547',
        scope='One DEV CPU round only. Repeated seeds/conditions are not independent success-rate cohorts. No CPU R2/R3. warp5 MJWarp continuation must not pool with CPU.',
        completion_definition='teacher command_complete AND evaluator zone_placement_success; authored-pose arrival or colour detection alone is not completion',
        attempts=8,carry_attempts=len(carry),cohorts=cohorts,
        terminations=dict(collections.Counter(x['termination_normalized'] for x in records)),
        speed=full['speed'],raw_files_verified=sum(x['integrity']['files'] for x in full['integrity']),
        input_audit=dict(measured_runs=len(audits),invisible_measurements=sum(x['invisible_measurements'] for x in audits),held_world_reads=sum(x['held_world_reads'] for x in audits)),
        funnel=dict(attempts=8,controller_started=8,carry_started=len(carry),
            lift=sum(x['gate_cumulative']['lift_success'] for x in carry),travel=sum(x['gate_cumulative']['travel_entered'] for x in carry),
            authored_arrival=sum(x['gate_cumulative']['authored_arrival'] for x in carry),
            colour_acquired=sum(x['destination'].get('acquired_t') is not None for x in carry),
            place_view=sum(x['gate_cumulative']['place_view'] for x in carry),
            place=sum(x.get('place_success') is True for x in carry),complete=sum(x.get('complete') is True for x in carry)),
        runs=records,full_summary=dict(path=str(B/'summary.json.zst'),sha256=sha(B/'summary.json.zst') if (B/'summary.json.zst').exists() else None),
        off_replay=obj(B/'off-replay.json'))
    (out/'summary.json').write_text(json.dumps(summary,separators=(',',':'))+'\n')
    lines=['|조건|seed|종료|place/완주|자기 추정 도착/색 획득|xy/yaw p95|운반 xy/yaw p95|기하 위험 SIM초|','|---|---|---|---|---|---|---|']
    for x in carry:
        e=x['errors'];p=x['phase_metrics']['carry_to_zone']
        lines.append(f"|{x['condition']}|{x['seed']}|{x['original_reason']}|{int(x['place_success'])}/{int(x['complete'])}|{x['gate_cumulative']['authored_arrival']}/{int(x['destination'].get('acquired_t') is not None)}|{e['xy']['p95']:.3f}m/{e['yaw']['p95']:.2f}°|{p['visual_xy']['p95']:.3f}m/{p['visual_yaw']['p95']:.2f}°|{x['geometry_risk_sim_s']:.1f}|")
    (out/'metrics.md').write_text('\n'.join(lines)+'\n')
    p=out/'summary.json'
    if p.stat().st_size>65536:
        before=sha(p);subprocess.run(['zstd','-q','-f',str(p)],check=True)
        after=hashlib.sha256(subprocess.check_output(['zstd','-dc',str(p)+'.zst'])).hexdigest()
        assert after==before
        p.unlink()
    mf={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in out.iterdir() if p.is_file() and p.name!='retrieval-manifest.json'}
    (out/'retrieval-manifest.json').write_text(json.dumps(mf,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ('status','handoff','attempts','cohorts','terminations','funnel','input_audit','raw_files_verified')},indent=2))


if __name__=='__main__':main()
