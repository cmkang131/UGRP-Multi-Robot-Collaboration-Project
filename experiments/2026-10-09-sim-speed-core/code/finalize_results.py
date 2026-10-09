"""Postprocess completed, frozen simspeed2 outputs; never run physics."""
import hashlib,json,statistics,sys
from pathlib import Path
ROOT=Path('/Users/changmin/projects/ugrp-wt/sim-speed-core')
BASE=Path('/Users/changmin/projects/ugrp/outputs')
RUN=BASE/'simspeed-core-20261009-v3'
SHA='725f45b155fda3f7dc93beba782b848ca3b4a6dd'
sys.path.insert(0,str(ROOT))
from scripts.benchmark_v7_speed import compare

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
managed=BASE/'simspeed-core-20261009-v3-managed/manifest.json'
m=read(managed)
assert m['status']=='process_completed' and m['exit_code']==0
assert m['source_changed_during_run'] is False and m['inputs_changed_during_run'] is False
assert m['source']['source_sha']==SHA
module_sha=sha(ROOT/'sim/v7_exact_speedups.py')
summary=dict(source_sha=SHA,module_sha256=module_sha,managed_manifest=dict(path=str(managed),sha256=sha(managed)),
    scope='30 SIM seconds per saved-command physical backend; no online controller or mission success claim',
    n_per_condition=2,paths={},profiles=[],diagnostics=[])
views=BASE/'simspeed-core-20261009-views'
views.mkdir(exist_ok=False)
for kind in ('s2','s3','egomap'):
    path=RUN/kind
    recorded=read(path/'comparison.json')
    input_source=Path(next(r['source'] for r in read(RUN/'suite.json') if r['kind']==kind))
    input_bundle=read(input_source/'bundle.json')
    input_digest=hashlib.sha256(json.dumps(input_bundle,sort_keys=True).encode()).hexdigest()
    pairs=[compare(path/'A1',path/n) for n in ('A2','B1','B2')]
    assert all(x['identical'] for x in pairs)
    measures=[]
    for name in ('A1','B1','B2','A2'):
        r=read(path/(name+'.measurement.json'))
        receipt=read(path/name/'v7-speedups.json')
        rb=read(path/name/'runtime-bundle.json')
        assert receipt==r['receipt']==rb['runtime_speedups']
        assert rb['input_bundle_sha256']==input_digest and rb['source_sha']==input_bundle['source_sha']
        assert rb['execution_bundle_id']==input_bundle['execution_bundle_id']
        assert receipt['module_sha256']==module_sha
        assert receipt['mode']==r['mode'] and receipt['enabled']==name.startswith('B') and receipt['fallback'] is None
        assert r['steps']==120000 and r['sim_s']==30 and r['nice']==0
        r['name']=name
        r['commands']=sum(len(p.read_text().splitlines()) for p in (path/name).glob('robots/*/commands.jsonl'))
        r['measurement_source']=dict(path=str(path/(name+'.measurement.json')),sha256=sha(path/(name+'.measurement.json')))
        measures.append(r)
    a=[r for r in measures if r['name'].startswith('A')];b=[r for r in measures if r['name'].startswith('B')]
    avg=lambda rows: statistics.mean(r['wall_per_sim'] for r in rows)
    loads=lambda rows:[statistics.mean(r[k][i] for r in rows for k in ('load_start','load_end')) for i in range(3)]
    summary['paths'][kind]=dict(seed=measures[0]['seed'],before=avg(a),after=avg(b),wall_reduction_percent=100*(1-avg(b)/avg(a)),
        before_load_mean_1_5_15=loads(a),after_load_mean_1_5_15=loads(b),all_bytes_identical=True,
        behavior_files_per_run=pairs[0]['compared_files'],provenance_exceptions=pairs[0]['explicit_provenance_files'],
        state=read(path/'A1/state-chain.json'),judgment=read(path/'A1/judgement.json'),measurements=measures,
        raw_comparison=dict(path=str(path/'comparison.json'),sha256=sha(path/'comparison.json')),
        input_hashes=recorded['input_hashes'],adapter_sha=recorded['adapter_sha'],
        adapter_manifest=dict(path=str(path/'adapter-manifest.json'),sha256=sha(path/'adapter-manifest.json')))
    for name in ('profile-off','profile-on'):
        p=path/(name+'.measurement.json')
        if p.exists():
            assert compare(path/'A1',path/name)['identical']
            r=read(p);r['name']=kind+'-'+name
            r['measurement_source']=dict(path=str(p),sha256=sha(p))
            summary['profiles'].append(r)
summary['diagnostics']=[
    dict(name='v1-referee-error',source=dict(path=str(BASE/'simspeed-core-20261009-v1-managed/manifest.json'),sha256=sha(BASE/'simspeed-core-20261009-v1-managed/manifest.json')),
         scope='S2 ABBA passed; S3 off completed 30s but original referee ContractViolation stopped report publication; preserved, excluded from final means'),
    dict(name='v2-host-interruption',source=dict(path=str(BASE/'simspeed-core-20261009-v2-managed/host-interruption.json'),sha256=sha(BASE/'simspeed-core-20261009-v2-managed/host-interruption.json')),
         scope='감독 세션 종료로 대기 중단; no physics; not robot failure')]
write(BASE/'simspeed-core-20261009-summary.json',summary)
EXP=ROOT/'experiments/2026-10-09-sim-speed-core'
write(EXP/'results/summary.json',summary)
write(EXP/'results/host-interruption.json',read(BASE/'simspeed-core-20261009-v2-managed/host-interruption.json'))
lines=['# 최종 고정 입력 동등성·속도 결과','',f'실행 SHA `{SHA}`. 각 경로 30 SIM초, ABBA, n=2/조건. 초기화/reset·프로파일 실행은 wall/SIM 평균에서 제외.',
       '부하 평균은 각 조건의 두 반복 시작/끝 1·5·15분 loadavg의 산술 평균이다.','',
       '|경로|off wall/SIM|on wall/SIM|wall 감소|off 부하 1/5/15|on 부하 1/5/15|동일 행동 파일/반복|',
       '|---|---:|---:|---:|---|---|---:|']
for kind,r in summary['paths'].items():
    loads=lambda k:'/'.join(f'{x:.2f}' for x in r[k])
    lines.append(f"|{kind} seed{r['seed']}|{r['before']:.6f}|{r['after']:.6f}|{r['wall_reduction_percent']:.2f}%|{loads('before_load_mean_1_5_15')}|{loads('after_load_mean_1_5_15')}|{r['behavior_files_per_run']}|")
lines += ['', '각 반복 120,000스텝의 integration-state+relay 누적 해시와 최종 상태가 동일하다. 명령·궤적·접촉·판정·영상·scene 등 위 파일은 직접 bytes 차이0이다.',
          '모드가 다른 `v7-speedups.json`과 `runtime-bundle.json` 2개는 의도적인 출처 차이다. 각 모드/실제 enabled/모듈 SHA/입력 bundle 연결도 별도 검증했다.',
          'S3 판정은 원본과 같은 EVALUATOR_ERROR/ContractViolation이다. 오류 문자열까지 동일하며 임무 성공이 아니다. 전체 온라인 제어기·실물 검증은 포함하지 않는다.',
          '자산의 Git export 경로가 달라 원본 scene 비교에서는 file 경로만 자산 SHA로 치환했다. 자산 bytes 및 나머지 XML 동일, on/off XML 자체는 raw bytes 동일이다.','',
          '|경로/순서|mode|wall s|wall/SIM|시작 부하 1/5/15|끝 부하 1/5/15|','|---|---|---:|---:|---|---|']
for kind,r in summary['paths'].items():
    for q in r['measurements']:
        lines.append(f"|{kind}/{q['name']}|{q['mode']}|{q['wall_s']:.6f}|{q['wall_per_sim']:.6f}|"+'/'.join(f'{x:.2f}' for x in q['load_start'])+'|'+ '/'.join(f'{x:.2f}' for x in q['load_end'])+'|')
for p in summary['profiles']:
    lines += ['', '## egomap '+p['mode']+' Python 상위 10개', '', '분모는 C 확장/대기를 포함한 cProfile 전체 self time. Python 항목만 순위화하며 cumulative 중복 합산 없음.',
              '|함수|호출|self s|비율|cumulative s|','|---|---:|---:|---:|---:|']
    for f in p['top10_python']:
        name=f['function'].replace(str(RUN/'egomap/adapter')+'/','').replace(str(ROOT)+'/','').replace('/Users/changmin/Project-Runtimes/ugrp/.venv-sim-worker-mac/lib/python3.12/site-packages/','')
        lines.append(f"|`{name}`|{f['calls']:,}|{f['self_s']:.5f}|{f['percent']:.3f}%|{f['cumulative_s']:.5f}|")
lines += ['', '추가 미세 개선인 torque 속성 직접 보관은 캐시와 함께 측정됐다. 공통 step의 불필요한 zeros 할당 제거는 양쪽에 동일하게 적용되어 이 표에서 독립 효과를 주장하지 않는다.',
          'mj_forward는 이번에도 제거하지 않았다. 선행 #415의 카메라 갱신 호출 확인과 MuJoCo의 적분 후 파생 상태 설명에 따라 유지했다.',
          'v1의 referee 종료·v2의 감독 세션 종료 대기는 raw/사유를 보존했다. v2는 물리 실행0이며 명령은 새 출력 경로 외 v3와 동일하다.']
(EXP/'results/results.md').write_text('\n'.join(lines)+'\n')
source=BASE/'simspeed-core-20261009-summary.json'
for kind,r in summary['paths'].items():
    for q in r['measurements']:
        name=kind+'-'+q['name']
        view=dict(schema='ugrp.offline_audit_view.v1',derived_view_only=True,
            offline_source=dict(path=str(source),sha256=sha(source)),offline_scalar_scope=summary['scope'],
            family='simspeed-core',policy=q['mode'],condition=kind,case=kind+'_30s',seed=r['seed'],
            source_sha=SHA,run_id=name,outcome='byte_equal_prefix',
            success=True,success_definition='state/artifact equality only; not robot task success',
            wall_s=q['wall_s'],sim_s=30,commands=q['commands'],model_calls=0,
            offline_scalars={'offline/wall_per_sim':q['wall_per_sim'],'offline/load_start_1m':q['load_start'][0],
              'offline/load_end_1m':q['load_end'][0],'offline/steps':q['steps'],'gate/bytes_identical':1},
            hparam_metrics=['offline/wall_per_sim','gate/bytes_identical'])
        write(views/name/'result.json',view)
for p in summary['profiles']:
    write(views/p['name']/'result.json',dict(schema='ugrp.offline_audit_view.v1',derived_view_only=True,
        offline_source=p['measurement_source'],offline_scalar_scope='cProfile only; excluded from performance means',
        family='simspeed-core',policy=p['mode'],case='profile',run_id=p['name'],seed=p['seed'],source_sha=SHA,
        outcome='profile_only',model_calls=0,
        offline_scalars={f'offline/hotspot_{i}_percent':f['percent'] for i,f in enumerate(p['top10_python'][:3],1)},
        hparam_metrics=['offline/hotspot_1_percent']))
for d in summary['diagnostics']:
    write(views/d['name']/'result.json',dict(schema='ugrp.offline_audit_view.v1',derived_view_only=True,
        offline_source=d['source'],offline_scalar_scope=d['scope'],family='simspeed-core',policy='diagnostic',
        case=d['name'],run_id=d['name'],outcome=d['name'],model_calls=0,
        offline_scalars={'offline/completed_final_comparison':0},hparam_metrics=['offline/completed_final_comparison']))
print(json.dumps({k:{q:v for q,v in r.items() if q in ('before','after','wall_reduction_percent','behavior_files_per_run')} for k,r in summary['paths'].items()},indent=2))
