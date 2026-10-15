"""gcp2 numerical report from terminal ledgers; no controller/evaluator feedback."""
import collections, hashlib, json, platform, subprocess
from pathlib import Path

RUNS=Path('/home/ugrp/ugrp-sim/runs')


def obj(p):
    return json.loads(p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst']))


def pair(d):
    return f"{d['p50']:.4f}/{d['p95']:.4f}" if d.get('N',0) else 'NA'


def main():
    assert platform.node().startswith('ugrp-sim-gcp2')
    summaries=[obj(RUNS/f'reloc18-round{n}/summary.json') for n in (1,2,3)]
    r3=summaries[-1];sm=obj(RUNS/'reloc18-round3/selfmap-results.json')
    integrity=obj(RUNS/'reloc18-integrity.json')
    out=RUNS/'reloc18-report';out.mkdir(exist_ok=True)
    records=[];audits=[]
    for summary in summaries:
        for r in summary['runs']:
            raw=Path(r['raw']);result=obj(raw/'result.json');audit=result.get('input_audit',{})
            audits.append(dict(run=r['name'],input_audit=audit))
            ir=next(x for x in integrity['runs'] if x['run']==r['name'])
            records.append(dict(round=summary['round'],run=r['name'],kind=r['kind'],condition=r['condition'],seed=r['seed'],
                source_sha=r['source_sha'],raw=r['raw'],status=r['status'],
                termination=r['termination'] or ('invalid_control_interrupted' if ir['invalid'] else 'original_missing_reason'),
                original_termination=r['termination'],
                invalid=ir['invalid'],predetermined_failure_window=r['condition']=='legacy_failure_window',
                place_success=r.get('place_success'),sim_s=r.get('sim_s',result.get('elapsed_sim_s')),
                result_sha256=ir['result_sha256'],integrity=ir['integrity']))
    data=dict(status='NOT_READY',rounds=3,submitted_runs=len(records),running_runs=0,
        scope='gcp2 n4-highcpu-64 C MuJoCo CPU DEV only; no student or physical robot result',
        base_sha='47670d1428abfbb09756627c1a2be31caf650465',r3_source_sha=r3['runs'][0]['source_sha'],
        scene='walls_floor_contrast_v5_indigo110_s80 + v1 floor + no_mip_v1',
        valid_place_candidates_by_round=[dict(round=n,N=2,success=0) for n in (1,2,3)],
        termination_counts=dict(collections.Counter(x['termination'] for x in records)),
        literal_status_counts=dict(collections.Counter(x['status'] for x in records)),
        host_error_scope='two R3 selfmap results literally HOST_ERROR; category selfmap4_relocalization_exhausted is algorithmic exhaustion, not a measured VM outage',
        invalid_runs=sum(x['invalid'] for x in records),predetermined_failure_window_runs=1,
        all_manifest_hashes_verified=integrity['all_manifest_hashes_verified'],verified_files=sum(x['integrity']['files'] for x in records),
        complete_transport_plan=False,success_playback_reference_available=False,
        r3_carry=[{k:r[k] for k in ('name','seed','condition','errors','tracker','heading','gate_cumulative','final_evaluator')} for r in r3['runs'] if r['kind']=='carry'],
        r3_selfmap=[dict(run=r['run'],source_sha=r['source_sha'],global_same_trajectory=r['global_same_trajectory']) for r in sm['runs']],
        runs=records,input_audits=audits,
        raw_integrity_manifest=str(RUNS/'reloc18-integrity.json'),
        note='all-seed no-regression criterion failed; no fourth physics round submitted; all runtime options remain default off')
    (out/'summary.json').write_text(json.dumps(data,indent=2)+'\n')
    lines=['# 긴 경로 오차: 명령 예측과 보정','',
           '단위 m, 중앙/p95. 같은 후보 실행의 저장 명령열을 적분한 shadow와 비교한다. 별도 폐루프 대조 실행과 동일 궤적이라고 가정하지 않는다.',
           '운반은 시작부터, selfmap은 첫 RGB 등록부터 SIM 구간이다. 정답은 평가 전용. 전체 운반 계획 완주는 0회다.','',
           '|실행|SIM 구간|명령 xy|보정 xy|명령 yaw p95 °|보정 yaw p95 °|','|---|---|---|---|---|---|']
    for r in r3['runs']:
        if r['kind']!='carry' or r['condition']!='candidate':continue
        for b in r['drift_bins']:
            e=b['errors']
            if not e['xy'].get('N'):continue
            lines.append(f"|carry{r['seed']}|{b['sim_interval']}|{pair(e['command_xy'])}|{pair(e['xy'])}|{e['command_yaw']['p95']:.2f}|{e['yaw']['p95']:.2f}|")
    for r in sm['runs']:
        for b in r['global_same_trajectory']['bins']:
            c,e=b['command'],b['candidate']
            if not e['N']:continue
            lines.append(f"|selfmap{r['run'].split('-')[-2]}|{b['sim_interval']}|{pair(c['xy_m'])}|{pair(e['xy_m'])}|{c['yaw_deg']['p95']:.2f}|{e['yaw_deg']['p95']:.2f}|")
    (out/'drift-table.md').write_text('\n'.join(lines)+'\n')
    place=obj(RUNS/'reloc18-round3/place-predicates.json')
    lines=['# 최종 place 관문','',
           'R3 DEV 예산 observe-only 조건. site는 발행 PWM의 명목 FK로 계산하고 실제 base로 평가 변환했다. 하중 처짐/실기 교정 미확인.','',
           '|조건·시드|place RGB|기하 통과|색 통과|처음 xy 오차 m|처음 site 구역 여유 m|종료|',
           '|---|---|---|---|---|---|---|']
    for r in place['runs']:
        if not r.get('frames'):
            lines.append(f"|{r['run']}|0|NA|NA|NA|NA|place 미도달|");continue
        e=r['first_evaluator'];c=r['cumulative']
        lines.append(f"|{r['condition']} {r['run'].split('-')[-2]}|{r['place_phase_frames']}|{c['geometry_qualified']}|{c['painted_and_qualified']}|{e['localization_error_xy_m']:.4f}|{e['nominal_site_zone_margin_m']:.4f}|destination_floor_not_visible|")
    lines+=['','도착 추정→place-view는 후보2/2, advance/lower/open/final place는0/2. 검사한93프레임은 전부 색 비율0이며 재구성 불일치0이다.',
            '목적지 바닥이 보이지 않는 것을 실제로 거부했다. 내려놓기 동작·최종 높이·자세 판정까지 가지 않아 그 조건의 결함/성공은 미검증이다.']
    (out/'final-place-table.md').write_text('\n'.join(lines)+'\n')
    tables=[dict(round=n,**obj(RUNS/f'reloc18-round{n}/rejection-table.json')) for n in (1,2,3)]
    (out/'rejection-table.json').write_text(json.dumps(dict(round_tables=tables,
        place_frame_funnel=[{k:r[k] for k in ('run','raw','cumulative','rejection_reasons')} for r in place['runs'] if r.get('frames')],
        source_place_predicates=str(RUNS/'reloc18-round3/place-predicates.json'),reproduce=f'PYTHONPATH=. python {__file__}'),indent=2)+'\n')
    print(json.dumps(dict(runs=len(records),bytes=(out/'summary.json').stat().st_size,termination_counts=data['termination_counts'])))


if __name__=='__main__':main()
