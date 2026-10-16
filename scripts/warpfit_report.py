"""gcp2 compact result delivery from measured rows; never changes a verdict."""
import argparse
import csv
import json
import os
from pathlib import Path
from collections import defaultdict


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--analysis',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not os.uname().nodename.startswith('ugrp-sim-gcp2'):raise ValueError('gcp2 report only')
    import numpy as np
    a.output.mkdir(parents=True,exist_ok=False)
    rows=json.loads((a.analysis/'rows.json').read_text())
    selected=[r for r in rows if r['protocol']=='primitive-v1' and r['engine']=='warp' and r['round'] in (2,3)]
    compact=[];pulses=[]
    def med(x):return float(np.median(x))
    for r in selected:
        entry={k:r.get(k) for k in ('path','round','nworld','kind','case','profile','status','completed','HOST_ERROR','cap_end',
            'sim_s','physical_gpu_ms_per_step','wall_per_sim_s','amortized_wall_per_world_sim_s','runtime_wall_s','setup_jit_s',
            'loaded_contact_rate','fully_retained_worlds','hold_contact_rate','acceptance_sample_rate','slip_p95_mm','max_ncon','max_nefc','error','rejection_category')}
        if r.get('worlds'):
            entry['height_min_mm']=min(w['height_m']['min'] for w in r['worlds'])*1000
            entry['tilt_max_deg']=max(w['tilt_deg']['max'] for w in r['worlds'])
            entry['hold_samples_per_world']=r['worlds'][0]['hold_samples']
        compact.append(entry)
        groups=defaultdict(list)
        for v in r.get('pulses',[]):groups[(v['case'],v.get('phase','missing_boundary'))].append(v)
        for (case,phase),values in groups.items():
            valid=[v for v in values if 'translation_mm' in v]
            if not valid:
                pulses.append(dict(nworld=r['nworld'],profile=r['profile'],case=case,phase=phase,status='boundary_not_recorded'))
                continue
            prediction=valid[0]['v122_delta']
            ratios=[v['actual_over_prediction'] for v in valid if v['actual_over_prediction'] is not None]
            pulses.append(dict(nworld=r['nworld'],profile=r['profile'],case=case,phase=phase,world_replicas=len(valid),
                translation_mm_p50=med([v['translation_mm'] for v in valid]),
                translation_mm_min=min(v['translation_mm'] for v in valid),translation_mm_max=max(v['translation_mm'] for v in valid),
                yaw_deg_p50=med([v['yaw_deg'] for v in valid]),
                v122_translation_mm=None if prediction is None else float(np.linalg.norm(prediction[:2])*1000),
                v122_yaw_deg=None if prediction is None else float(np.degrees(prediction[2])),
                actual_over_v122_p50=None if not ratios else med(ratios),
                prediction_sample_time_s=valid[0].get('prediction_sample_time_s'),
                prediction_tail_endpoint_held=valid[0].get('prediction_tail_endpoint_held'),
                tilt_deg_p95=med([v['tilt_deg']['p95'] for v in valid]),tilt_deg_max=max(v['tilt_deg']['max'] for v in valid),
                calibration_valid=False,fixture_limit='original chassis/cargo_box_00 interpenetration; see drivecheck'))
        if r['kind']=='drive':
            valid=[v for v in r.get('pulses',[]) if 'translation_mm' in v]
            entry['tilt_max_deg']=max((v['tilt_deg']['max'] for v in valid),default=None)
            reference_case='left-0.06' if r['case']=='tail2' else 'forward-0.1'
            reference=[v for v in valid if v['case']==reference_case and v['phase']=='pulse_plus_stop']
            if reference:
                entry['drive_reference_case']=reference_case+' +1s stop'
                entry['drive_actual_mm']=med([v['translation_mm'] for v in reference])
                pred=reference[0]['v122_delta']
                entry['drive_predicted_mm']=None if pred is None else float(np.linalg.norm(pred[:2])*1000)
    terminal=len(selected)==28 and all(r['status'] in ('complete','HOST_ERROR') for r in selected)
    errors=sum(bool(r['HOST_ERROR']) for r in selected)
    summary=dict(status=('comparison_complete_with_rejections' if errors else 'complete') if terminal else 'partial',
        expected_paired_jobs=28,recorded_paired_jobs=len(selected),completed_paired_jobs=sum(bool(r['completed']) for r in selected),
        rejected_paired_jobs=errors,
        rows=compact,drive_file='drive-summary.json',drive_csv='drive-table.csv',
        drive_rows=len(pulses),thresholds=json.loads((a.analysis/'thresholds.json').read_text()),
        world_scope='same fixed fixture repeated; not independent random-seed task trials',
        latency_definition='runtime wall / common SIM horizon',throughput_definition='runtime wall / (world count x SIM horizon)',
        physics_definition='CUDA event ms per batch physics step, including fixed tape kernel; setup/JIT and final writing excluded',
        slip_definition='per-world temporal P95 of object COM displacement relative to gripper axes; summary contains across-world distribution',
        default_changes=0,adopted=False,teacher_gate_rerun_required=True)
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    (a.output/'drive-summary.json').write_text(json.dumps(pulses,indent=2,allow_nan=False)+'\n')
    fields=sorted(set().union(*(r.keys() for r in pulses))) if pulses else ['status']
    with (a.output/'drive-table.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(pulses)
    table=['|N|입력|프로필|GPU ms/배치step|wall/SIM|wall/(N×SIM)|유지 세계|미끄럼 P95 mm|주행 실제/예측 mm|tilt 최대 °|',
           '|---:|---|---|---:|---:|---:|---:|---:|---:|---:|']
    def num(x):return '미완료' if x is None else f'{x:.5f}'
    for r in sorted(compact,key=lambda r:(r['nworld'],r['kind'],r['case'],r['profile'])):
        retained='해당없음' if r.get('fully_retained_worlds') is None else f"{r['fully_retained_worlds']}/{r['nworld']}"
        slip=r.get('slip_p95_mm')
        actual='해당없음' if r.get('drive_actual_mm') is None else num(r['drive_actual_mm'])+'/'+num(r['drive_predicted_mm'])
        table.append('|'+ '|'.join([str(r['nworld']),r['kind']+'/'+r['case'],r['profile'],num(r['physical_gpu_ms_per_step']),
            num(r['wall_per_sim_s']),num(r['amortized_wall_per_world_sim_s']),retained,num(None if not slip else slip['p95']),
            actual,num(r.get('tilt_max_deg'))])+'|')
    table+=['','유지는 양쪽(빔은 네) 접촉력 양수와 기존 교사12mm 들기 조건이다. 미끄럼 열은 세계별 시간 P95의 세계간 P95다.',
        '상자는 세계당30표본·3초, 빔은3표본·0.3초 유지다. 같은 초기 조건의 복제이며 독립 일반화 성공률이 아니다.',
        '주행 요약은group16/group64 전진100ms, tail2 횡60ms 뒤1초 정지다. 전체18펄스·회전각·펄스 끝/정지 후는drive-table.csv에 있다. 초기 관통 때문에 보정에 쓸 수 없다.',
        'v122는 등록된 짧은 펄스만 쓰며,1초 정지 뒤 비교에는 등록곡선0.2초 끝값을 유지한다.0.2초 이후 drift를 예측한 값은 아니다.',
        'C 분포의 높이 P05/미끄럼 P95 동시 비교는 별도 JSON에 있으며 유지 판정과 혼동하지 않는다. 기본값·채택 변경0이다.']
    (a.output/'timing-table.md').write_text('\n'.join(table)+'\n')
    print(json.dumps({k:summary[k] for k in ('status','recorded_paired_jobs','completed_paired_jobs')}))


if __name__=='__main__':main()
