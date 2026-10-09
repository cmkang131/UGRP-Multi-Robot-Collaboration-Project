"""Build immutable result tables and TensorBoard views after the ABBA run exits."""
from pathlib import Path
import hashlib,json,statistics
BASE=Path('/Users/changmin/projects/ugrp/outputs/simspeed-20261009')
RUN=BASE/'physical-abba-v2'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
measure=read(RUN/'measurements.json');comparison=read(RUN/'comparison.json')
assert len(measure)==5 and comparison['all_bytes_identical'] and comparison['input_unchanged']
a=[r['wall_per_sim'] for r in measure if r['name'].startswith('A')]
b=[r['wall_per_sim'] for r in measure if r['name'].startswith('B')]
summary=dict(source_sha=comparison['source_sha'],baseline_mean=statistics.mean(a),candidate_mean=statistics.mean(b),
    wall_reduction_percent=100*(1-statistics.mean(b)/statistics.mean(a)),speedup=statistics.mean(a)/statistics.mean(b),
    n_per_condition=2,sim_s=measure[0]['sim_s'],all_bytes_identical=True,
    files_per_run=comparison['comparisons'][0]['files'],measurements=measure,
    scope='12 SIM seconds saved-command physics/render/evaluation prefix; not closed-loop/full-task or hardware success',
    input=comparison['input'],input_hashes=comparison['input_hashes'])
write(BASE/'summary.json',summary)
lines=['## 물리 A/B 결과','',f"실행 SHA `{summary['source_sha']}`, source 원본 파일 해시 재확인.",
    '|순서|옵션|wall/SIM|wall s|시작 부하 1/5/15분|종료 부하 1/5/15분|',
    '|---|---|---:|---:|---|---|']
for r in measure:
    lines.append(f"|{r['name']}|{r['mode']}|{r['wall_per_sim']:.6f}|{r['wall_s']:.4f}|"+
        '/'.join(f'{v:.2f}' for v in r['load_start'])+'|'+ '/'.join(f'{v:.2f}' for v in r['load_end'])+'|')
lines.extend(['',f"프로파일 제외 ABBA 평균 {summary['baseline_mean']:.6f} → {summary['candidate_mean']:.6f} wall/SIM "
    f"(wall {summary['wall_reduction_percent']:.2f}% 감소, {summary['speedup']:.3f}배 처리량). 조건별 n=2.",
    f"매 반복 {measure[1]['steps']:,} 스텝 누적 integration-state 해시 및 최종 상태 동일. "
    f"각 실행 {summary['files_per_run']}개 파일 원본 bytes 동일(A1↔A2/B1/B2); 누락 파일·차이 0.",
    '초기화/reset 시간은 표의 timed prefix 밖 별도 sidecar에 기록. cProfile은 속도 평균에 포함하지 않음.',
    '제어 입력을 고정한 12초 검증이며 온라인 제어기나 전체 운반/귀환 완주를 검증한 것은 아니다.',''])
for title,path in [('동기 물리 재생 cProfile',RUN/'measurements.json'),('저장 RGB/제어기 cProfile',BASE/'saved-egomap49-profile/profile.json'),('입력 relay만 cProfile',BASE/'relay-profile/profile.json')]:
    r=read(path);r=r[0] if isinstance(r,list) else r
    lines += ['### '+title,'','자기 시간(self time) 비율. C 확장/대기 포함, cumulative 비율의 중복 합산 없음.',
        '|함수|호출 수|self s|비율|cumulative s|','|---|---:|---:|---:|---:|']
    for f in r['top10']:
        name=f['function'].replace('/Users/changmin/projects/ugrp-wt/sim-speed/','').replace('/Users/changmin/Project-Runtimes/ugrp/.venv-sim-worker-mac/lib/python3.12/site-packages/','')
        lines.append(f"|`{name}`|{f['calls']:,}|{f['self_s']:.4f}|{f['percent']:.2f}%|{f['cumulative_s']:.4f}|")
    lines.append('')
lines += ['### 별도 mj_forward 호출','', '|호출자|횟수|wall s|','|---|---:|---:|']
for k,v in measure[0]['forward_callers'].items():lines.append(f"|`{k}`|{v}|{measure[0]['forward_seconds'][k]:.6f}|")
lines += ['', '카메라 촬영 전 파생 상태 갱신이다. 적분 후 상태가 달라져 동일 상태 중복으로 제거하지 않았다.',
          '`mj_step` 내부 C forward는 위 Python 호출 수에 중복 포함하지 않는다. 렌더 스레드도 별도 forward 계측에 포함했다.']
(BASE/'results.md').write_text('\n'.join(lines)+'\n')
views=BASE/'tensorboard-views';views.mkdir(exist_ok=False)
for r in measure:
    p=views/r['name'];p.mkdir()
    commands=len((RUN/r['name']/'robots/r3/commands.jsonl').read_text().splitlines())
    write(p/'result.json',dict(schema='ugrp.offline_audit_view.v1',derived_view_only=True,
        offline_source=dict(path=str(BASE/'summary.json'),sha256=sha(BASE/'summary.json')),
        offline_scalar_scope=summary['scope']+'; profile excluded from ABBA averages',
        family='simspeed',policy=r['mode'],condition=r['mode'],case='profile' if r['profile'] else '12s_ABBA',
        seed=49001,source_sha=summary['source_sha'],run_id=r['name'],outcome='byte_equal_prefix',
        success=True,success_definition='All completed prefix artifacts equal A1; not mission success',
        wall_s=r['wall_s'],sim_s=r['sim_s'],commands=commands,model_calls=0,
        offline_scalars={'offline/wall_per_sim':r['wall_per_sim'],'offline/load_start_1m':r['load_start'][0],
            'offline/load_end_1m':r['load_end'][0],'offline/steps':r['steps'],'gate/bytes_identical':1},
        hparam_metrics=['offline/wall_per_sim','gate/bytes_identical'],
        texts={'result/scope':summary['scope']}))
    if r['profile']:
        view=read(p/'result.json')
        view.pop('success');view.pop('success_definition')
        view['outcome']='profile_only'
        view['offline_scalars'].pop('gate/bytes_identical')
        view['hparam_metrics'].remove('gate/bytes_identical')
        write(p/'result.json',view)
src=BASE/'managed-abba-v2/manifest.json'
if src.exists() and read(src).get('status') == 'process_failed':
    p=views/'queue-timeout-v2';p.mkdir()
    write(p/'result.json',dict(schema='ugrp.offline_audit_view.v1',derived_view_only=True,
        offline_source=dict(path=str(src),sha256=sha(src)),
        offline_scalar_scope='3600s research-lock wait exhausted; no physics started; not robot failure',
        family='simspeed',policy='diagnostic',case='prephysics_queue',seed=49001,
        source_sha=read(src)['source']['source_sha'],run_id='queue-timeout-v2',outcome='queue_timeout',
        success=False,success_definition='Driver did not acquire research lock; not mission success/failure',
        model_calls=0,offline_scalars={'offline/physics_steps':0},hparam_metrics=['offline/physics_steps']))
print(json.dumps({k:v for k,v in summary.items() if k not in ('measurements','input_hashes')},indent=2))
