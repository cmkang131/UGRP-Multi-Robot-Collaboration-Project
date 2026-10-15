"""Format GCP2-measured reloc16 records; never launches a physical run."""
import datetime,hashlib,json,platform,statistics
from pathlib import Path
RUNS=Path('/home/ugrp/ugrp-sim/runs')
def load(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fmt(x,scale=1):return '미측정' if x is None else f'{x*scale:.3f}'
def main():
    if not platform.node().startswith('ugrp-sim-gcp2'):raise RuntimeError('gcp2 only')
    rounds=[load(RUNS/f'reloc16-round{n}/summary.json') for n in (1,2,3)]
    assert all(x['status']=='MEASURED' for x in rounds),'results still running'
    runs=[dict(round=x['round'],**r) for x in rounds for r in x['runs']]
    assert all(r.get('integrity',{}).get('verified') for r in runs),'raw hash verification failed'
    static=load(RUNS/'reloc16-static-r3/summary.json')
    out=RUNS/'reloc16-final';out.mkdir(exist_ok=True)
    baseline={r['seed']:r for r in runs if r['scene']=='v1' and r['status']=='RECORDED'}
    final=[r for r in runs if r['round']==3]
    pairs=[dict(seed=r['seed'],old=baseline[r['seed']]['drive_errors'],new=r['drive_errors'],
                old_raw=baseline[r['seed']]['raw'],new_raw=r['raw'],
                scope='same GCP2 CPU and seed; different scene/control path, no pooled rate') for r in final if r['kind']=='selfmap']
    lite=[]
    for r in runs:
        x={k:v for k,v in r.items() if k in ('round','run','kind','seed','scene','source_sha','raw','host_retry_of','integrity','status','failure','physical_frames','termination','termination_category','termination_reason','drive_errors','registered_errors','false_registration_events','funnel','place_verified','sim_s','all_pose_error','input_audit')}
        x['first30_wall_per_sim']=r.get('first30',{}).get('wall_per_sim') if r.get('first30') else None
        if 'heading' in r:x['heading']={k:v for k,v in r['heading'].items() if k not in ('admissions','increments')}
        lite.append(x)
    drive_ok=all(p['new']['N']>0 and all(p['new'][a][q]<=p['old'][a][q] for a in ('xy_m','yaw_deg') for q in ('p50','p95')) for p in pairs)
    place_ok=all(r.get('place_verified') is True for r in final if r['kind']=='carry')
    blockers=['boundary column median/p10 below v1']
    if not drive_ok:blockers.append('no reliable drive improvement for both seeds')
    if not place_ok:blockers.append('place gate not passed')
    summary=dict(schema='ugrp.reloc16.summary.v1',created=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        verdict='NOT_READY',pr=532,base_sha='644289a755ee60df99e916224931c2dec80298eb',scene_pr=527,
        scene_merge_sha='f0ad75304cca6a785ad473a7cf31ffb4ab61df9a',tested_final_source=final[0]['source_sha'],
        scene='walls_floor_contrast_v5_indigo110_s80 + v1 floor + no_mip_v1',backend='GCP2 CPU MuJoCo; no GCP1 access',
        rounds=3,physical_runs=sum(r['status']!='HOST_ERROR' for r in runs),host_errors=sum(r['status']=='HOST_ERROR' for r in runs),
        static=static,pairs=pairs,runs=lite,
        final_place=dict(N=2,verified=sum(r.get('place_verified') is True for r in final if r['kind']=='carry')),
        final_first30_median_wall_per_sim=statistics.median(r['first30']['wall_per_sim'] for r in final),
        blockers=blockers,video_review='See playback-review.md for actual reviewed ranges and successful-mission availability',
        scope=dict(mac_physics=0,mac_render=0,mac_gui=0,models=0,training=0,weld=False,all_new_options_default_off=True,
            teacher_student_success_not_claimed=True,full_raw_retrieval=False,full_raw_backup=False,
            raw_verification='all files checked on GCP2 before aggregation; inventory.json links stored result/manifest hashes',
            previous_carry='GCP1 recovered summary only; 0.221deg vs12.474deg example is not same-frame replay on GCP2'),
        records=dict(rounds=['round1.json','round2.json','round3.json'],inventory='inventory.json',rejections='rejection_table.md',
            playback='playback-review.md',tests='pytest-final.txt'),
        analysis=dict(script=str(Path(__file__)),sha256=digest(Path(__file__))))
    write(out/'summary.json',summary)
    reject=dict(verdict='NOT_READY',unit='ordered frames/columns/events, not independent trial success rate',
        static=load(RUNS/'reloc16-static-r3/rejection-table.json'),
        rounds=[load(RUNS/f'reloc16-round{n}/rejection-table.json') for n in (1,2,3)],
        reproduction=['PYTHONPATH=. python -m scripts.score_reloc16_static --output <new analysis directory>',
            *[f'PYTHONPATH=. python -m scripts.analyze_reloc16 --round {n}' for n in (1,2,3)]])
    for s in reject['static']['stages']:
        reasons=s['reasons'];cols=s['colour_columns'];after=cols-reasons.get('NO_VISIBLE_WALL_FLOOR_TRANSITION',0)
        s['cumulative']=dict(poses=s['candidates'],camera_qualified=s['qualified'],columns=cols,colour_geometry=after,
            line_consensus=after-reasons.get('NO_UNOCCLUDED_LINE_CONSENSUS',0),neighbour_continuity=s['accepted'])
        s['rejection_context']=dict(blocked_object='own_rgb_wall_floor_transition',minimum_gap_m=None,gap_status='not_applicable_image_gate')
    write(out/'rejection-table.json',reject)
    lines=['# reloc16 거부·관문 표','', '모든 수는 같은 실행의 순서 있는 프레임/컬럼/이벤트 수다. 실행 성공률로 합산하지 않는다. 정적56자세 자격 외32자세는 unknown이다.','',
        '|인코딩|자세→카메라자격|컬럼→색/계량지지→직선→연결|첫 거부(색/계량·직선·연결)|','|---|---:|---:|---:|']
    for s in reject['static']['stages']:
        c=s['cumulative'];r=s['reasons'];lines.append(f"|{s['encoding']}|88→56|{c['columns']}→{c['colour_geometry']}→{c['line_consensus']}→{c['neighbour_continuity']}|{r.get('NO_VISIBLE_WALL_FLOOR_TRANSITION',0)}/{r.get('NO_UNOCCLUDED_LINE_CONSENSUS',0)}/{r.get('NO_NEIGHBOUR_CONTINUITY',0)}|")
    lines+=['','|라운드·실행|누적 통과|첫 거부 사유:수|','|---|---|---|']
    for n in (1,2,3):
        for r in reject['rounds'][n-1]['runs']:
            c=' → '.join(f'{k}:{v}' for k,v in r['cumulative'].items())
            why='; '.join(f"{v['category']}:{v['N']}" for v in r['rejections']) or '없음(모두 수용)'
            lines.append(f"|R{n} {r['run']}|{c}|{why}|")
    lines+=['','막은 물체·최소 틈은 JSON의 각 거부 항목에 있다. 위치 추정/호스트/이미지 관문은 물리 틈이 아니므로 null과 명시적 not_applicable 사유를 기록한다. 물리 envelope 거부는 실제 원본의 blocker/minimum_gap을 유지한다.','',
        '원본 경로·원본 manifest/result SHA256: [inventory.json](inventory.json). 순차 누적·원본 경로·재현 명령: [rejection-table.json](rejection-table.json). 초기 분포: [rejection-before.json](rejection-before.json).']
    (out/'rejection_table.md').write_text('\n'.join(lines)+'\n')
    table=['|시드|이전 v1 xy 중앙/p95(m)|R3 v5 xy 중앙/p95(m)|이전→R3 yaw 중앙/p95(°)|이전→R3 오류 프레임|', '|---|---:|---:|---:|---:|']
    for p in pairs:
        a,b=p['old'],p['new'];table.append(f"|{p['seed']}|{fmt(a['xy_m'].get('p50'))}/{fmt(a['xy_m'].get('p95'))}|{fmt(b['xy_m'].get('p50'))}/{fmt(b['xy_m'].get('p95'))}|{fmt(a['yaw_deg'].get('p50'))}/{fmt(a['yaw_deg'].get('p95'))}→{fmt(b['yaw_deg'].get('p50'))}/{fmt(b['yaw_deg'].get('p95'))}|{a['bad_N']}/{a['N']}→{b['bad_N']}/{b['N']}|")
    (out/'pair-table.md').write_text('\n'.join(table)+'\n')
    print(json.dumps(dict(verdict=summary['verdict'],physical_runs=summary['physical_runs'],host_errors=summary['host_errors'],final_place=summary['final_place'])))
if __name__=='__main__':main()
