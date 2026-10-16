"""Write small review tables from evaluator analysis; raw arrays stay on gcp2."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess


def read(path):
    return json.loads(path.read_bytes() if path.is_file() else subprocess.check_output(['zstd','-dc',str(path)+'.zst']))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--analysis',type=Path,required=True);p.add_argument('--raw',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if not os.uname().nodename.startswith('ugrp-sim-gcp2'):raise ValueError('gcp2 only')
    rows=read(a.analysis/'pulse-table.json')
    names=['cpu312-v2','cpu316-v2','warp-baseline-v2','cpu312-clear-v1','cpu316-clear-rgb-v1','warp-clear-v2']
    names += [f'warp-L{l}D{d}N{n}' for l in (0,1) for d in (0,1) for n in (0,1) if (l,d,n)!=(0,0,1)]
    selected=[r for r in rows if r['run'] in names]
    a.out.mkdir(parents=True,exist_ok=True)
    compact=[]
    for row in selected:
        actual=abs(row['yaw_deg']) if row['axis']=='turn' else row['translation_mm']
        motor=row['no_load_motor_upper_yaw_deg'] if row['axis']=='turn' else row['no_load_motor_upper_distance_mm']
        compact.append(dict(run=row['run'],case=row['case'],phase=row['phase'],translation_mm=row['translation_mm'],
            dx_mm=row['delta_xyyaw'][0]*1000,dy_mm=row['delta_xyyaw'][1]*1000,
            yaw_deg=row['yaw_deg'],tilt_settled_deg=row['tilt_settled_deg'],tilt_end_deg=row['tilt_end_deg'],
            actual_over_v122=row['actual_over_v122'],actual_over_motor_reference=actual/motor,
            motor_reference= motor,unit='deg' if row['axis']=='turn' else 'mm',
            min_contact_gap_m=row['min_wheel_floor_contact_gap_m']))
    with (a.out/'pulse-summary.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(compact[0]));w.writeheader();w.writerows(compact)
    contact_columns=['run','case','phase','contact_count_p50_fl_fr_rl_rr','normal_N_p50_fl_fr_rl_rr',
        'tangent_N_p50_fl_fr_rl_rr','contact_slip_p50_m_s','contact_slip_p95_m_s','minimum_wheel_floor_gap_m']
    contact_data=[]
    for r in selected:
        wheels=r['wheel_floor'];slip=r['contact_point_tangent_slip_m_s']
        contact_data.append([r['run'],r['case'],r['phase'],*[[(w[key] or {}).get('p50') for w in wheels]
            for key in ('contact_count','normal_N','tangent_N')],None if slip is None else slip['p50'],
            None if slip is None else slip['p95'],r['min_wheel_floor_contact_gap_m']])
    (a.out/'contact-summary.json').write_text(json.dumps(dict(columns=contact_columns,rows=contact_data),separators=(',',':'),allow_nan=False)+'\n')
    reports=[]
    for name in names:
        path=a.raw/name/'result.json'
        if not path.is_file():continue
        r=read(path)
        reports.append({k:r.get(k) for k in ('host','engine','mujoco','source_sha','status','completed_cases','samples',
            'contact_rows','wall_s','recording_bytes','capacities','toggles','fixture_ablation','fixture_sha256','xml_sha256',
            'initial_qpos_sha256','online_own_rgb_ring','error')}|dict(run=name,raw=str(path.parent),result_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    def dump(name,x):
        (a.out/name).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
    dump('run-summary.json',dict(scope='diagnostic_only',runs=reports,
        completed=all(r['status']=='cap_end' for r in reports) and len(reports)==len(names),
        raw=str(a.raw),analysis=str(a.analysis),detailed_table=str(a.analysis/'pulse-table.json.zst'),
        no_load_reference_note='v7 no-load model mechanical reference, not calibrated traction prediction; missing v122 curves remain null'))
    lookup={(r['run'],r['case'],r['phase']):r for r in compact}
    lines=['|axis|pulse SIM s|C3.12 actual|C3.16 actual|Warp3.16 actual|Warp/C3.16|C3.12 / motor ref|Warp / motor ref|unit|',
           '|---|---:|---:|---:|---:|---:|---:|---:|---|']
    for axis in ('forward','left','turn'):
        for t in (.25,.5,1.,2.,4.):
            case=f'{axis}-{t:g}';vs=[lookup.get((n,case,'pulse_plus_stop')) for n in names[:3]]
            def value(v):return None if v is None else abs(v['yaw_deg']) if axis=='turn' else v['translation_mm']
            actual=[value(v) for v in vs]
            fmt=lambda x:'pending' if x is None else f'{x:.6f}'
            ratio=None if not actual[1] or actual[2] is None else actual[2]/actual[1]
            lines.append('|'+ '|'.join([axis,f'{t:g}',*[fmt(v) for v in actual],fmt(ratio),
                fmt(None if vs[0] is None else vs[0]['actual_over_motor_reference']),
                fmt(None if vs[2] is None else vs[2]['actual_over_motor_reference']),'deg' if axis=='turn' else 'mm'])+'|')
    (a.out/'paired-table.md').write_text('\n'.join(lines)+'\n')
    lines=['|legacy plane|dense capacity|NoSlip|worlds|forward .1s mm|left .06s mm|turn .1s deg|settled tilt deg|status|',
           '|---|---|---|---:|---:|---:|---:|---:|---|']
    for r in reports:
        if not (r['run']=='warp-baseline-v2' or r['run'].startswith('warp-L')):continue
        ts=r['toggles'];vals=[lookup.get((r['run'],case,'pulse_plus_stop')) for case in ('forward-0.1','left-0.06','turn-0.1')]
        fmt=lambda x:'pending' if x is None else f'{x:.6f}'
        lines.append('|'+ '|'.join([str(ts['legacy_plane_v1']),str(ts['dense_capacity_v1']),str(not ts['noslip_off_v1']),
            '18' if r['run']=='warp-baseline-v2' else '3',fmt(None if vals[0] is None else vals[0]['translation_mm']),
            fmt(None if vals[1] is None else vals[1]['translation_mm']),fmt(None if vals[2] is None else vals[2]['yaw_deg']),
            fmt(None if vals[0] is None else vals[0]['tilt_settled_deg']),r['status']])+'|')
    (a.out/'toggle-table.md').write_text('\n'.join(lines)+'\n')
    groups=[]
    for label,ns in [('original_pair',names[:3]),('clear_overlap_causal',names[3:6]),('toggle_matrix',names[6:])]:
        rs=[r for r in reports if r['run'] in ns];planned=sum(18 if n in names[:4] else 3 if n.startswith('warp-L') else 1 for n in ns)
        recorded=sum(r.get('completed_cases') or 0 for r in rs)
        reasons=[]
        if label in ('original_pair','toggle_matrix'):
            reasons=[dict(category='INITIAL_SCENE_OVERLAP',reason='base overlaps cargo before command; diagnostic intentionally reproduces mapbuild2',
                blocked_object='cargo_box_00_geom',minimum_gap_m=-.015344881182340743,basis='C312 initial original fixture contact record')]
        groups.append(dict(scope=label,raw=[r['raw'] for r in rs],stages=[
            dict(stage='planned_pulses',cumulative_pass_n=planned,rejected_n=0),
            dict(stage='complete_tapes',cumulative_pass_n=recorded,rejected_n=planned-recorded),
            dict(stage='initial_nonoverlap',cumulative_pass_n=recorded if label=='clear_overlap_causal' else 0,
                 rejected_n=0 if label=='clear_overlap_causal' else recorded)],reasons=reasons))
    dump('rejection_table.json',dict(cohorts=groups,raw=str(a.raw),reproduce=list(__import__('sys').argv),
        note='separate cumulative funnels; cap_end means fixed diagnostic tape complete, never task success'))
    dump('summary-sha256.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.out.iterdir() if p.is_file() and p.name!='summary-sha256.json'})


if __name__=='__main__':main()
