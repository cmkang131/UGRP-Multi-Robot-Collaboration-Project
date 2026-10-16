"""Replay already-retrieved command ledgers; no simulator, renderer or remote.

Uses the original odometry-scale loaders/step alignment/drift metric unchanged.
GT is used only for score denominators and a common initial evaluation anchor.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / 'experiments/2026-10-15-drive-model-deadband'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(EXPERIMENT / 'analysis_helpers'))
import an
import flows
from harness.drive_model import CommandDriveModel, DEFAULT_PARAMETERS
from harness.grasp_act_visible_world import command_delta
from sim.visible_belief import odometry, rates

# Existing odometry-scale/scripts/m3.py: fit on beam only, evaluation comparator.
# Never passed into CommandDriveModel or fitted again on the compared flows.
GT_FIT_GAINS = (.749, .715, .719)
MODELS = ('m1', 'm2', 'gt_fit', 'new')


def stat(values):
    return None if not values else dict(n=len(values), median=statistics.median(values),
                                       min=min(values), max=max(values))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()


def evaluate(name, iterable, own, stage=None, solo=False):
    rows=[]; levels=set(); mismatches=0; ticks=0
    for item in iterable:
        run, robots = item[:2]
        y0 = item[2] if solo else None
        for robot, (ev_t, gt, commands, phases, ledger) in robots.items():
            steps=an.steps(ev_t, gt, commands)
            model=CommandDriveModel()
            for s in steps:
                levels.update(abs(w) for w in s['w'] if w)
                issued={'wheels':s['w'], 'duration_s':s['d']}
                # Compare each adapter's default to the frozen original metric.
                m1=command_delta(issued,min(.15,s['dt']))
                sec=max([min(s['dt'],.1,d) if w else 0. for w,d in zip(s['w'],s['d'])] or [0.])
                m2=odometry(s['w'],sec)
                mismatches += int(json.dumps([m1,m2]) != json.dumps([s['m1'],s['m2']]))
                ticks+=1
                if own == 'm1':
                    s['new']=command_delta(issued,s['dt'],drive_model_deadband_v1=True,model=model)
                else:
                    # Keep the original M2 caller's scalar pulse-duration rule;
                    # change only the drive law. The remaining interval is idle.
                    s['new']=odometry(s['w'],sec,drive_model_deadband_v1=True,model=model)
                    if s['dt']>sec:
                        coast=model.delta([0.]*4,[0.]*4,s['dt']-sec)
                        s['new']=tuple(a+b for a,b in zip(s['new'],coast))
                s['gt_fit']=tuple(a*b for a,b in zip(s['m1'],GT_FIT_GAINS))
            if stage:steps=[s for s in steps if phases[s['i']]==stage]
            if not steps:continue
            has_yaw=gt[0][2] is not None
            def gt_length(s):return math.hypot(*s['g'][:2]) if has_yaw else s['g'][0]
            moving=[s for s in steps if any(s['w'])]
            row=dict(flow=name,run=run,robot=robot,ticks=len(steps),
                     gt_path_m=sum(map(gt_length,steps)),moving_gt_path_m=sum(map(gt_length,moving)))
            for label in MODELS:
                key=label
                final=an.drift(steps,gt,key,y0)[-1]
                row[label]=dict(path_m=sum(math.hypot(*s[key][:2]) for s in steps),
                    moving_path_m=sum(math.hypot(*s[key][:2]) for s in moving),
                    final_error_m=final[0],
                    final_yaw_error_deg=abs(math.degrees(final[1])) if final[1] is not None else None)
                gy=sum(abs(s['g'][2]) for s in steps) if has_yaw else 0
                if gy and sum(abs(s['m1'][2]) for s in steps)>math.radians(20):
                    row[label]['yaw_ratio']=sum(abs(s[key][2]) for s in steps)/gy
            rows.append(row)
    out=dict(flow=name,own_model=own,runs=len({r['run'] for r in rows}),robots=len(rows),
             command_levels=sorted(levels),off_byte_comparison=dict(ticks=ticks,mismatches=mismatches))
    for label in MODELS:
        out[label]=dict(
            path_ratio=stat([r[label]['path_m']/r['gt_path_m'] for r in rows if r['gt_path_m']>.5]),
            moving_path_ratio=stat([r[label]['moving_path_m']/r['moving_gt_path_m'] for r in rows if r['moving_gt_path_m']>.5]),
            final_error_m=stat([r[label]['final_error_m'] for r in rows if r['gt_path_m']>.3]),
            final_yaw_error_deg=stat([r[label]['final_yaw_error_deg'] for r in rows
                                     if r['gt_path_m']>.3 and r[label]['final_yaw_error_deg'] is not None]),
            yaw_ratio=stat([r[label]['yaw_ratio'] for r in rows if 'yaw_ratio' in r[label]]))
    return out,rows


def compressed_json(path, obj):
    raw=(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    zipped=subprocess.run(['zstd','-q','-c'],input=raw,capture_output=True,check=True).stdout
    restored=subprocess.run(['zstd','-q','-d','-c'],input=zipped,capture_output=True,check=True).stdout
    assert restored==raw
    path.write_bytes(zipped)
    return dict(path=str(path.resolve()),sha256=sha(path),decoded_sha256=hashlib.sha256(raw).hexdigest(),
                decoded_bytes=len(raw),bytes=len(zipped))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gcp-runs',type=Path,required=True)
    p.add_argument('--beam-runs',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    flows.G=str(args.gcp_runs);flows.BEAM=str(args.beam_runs)
    inputs={}
    original_jl=flows.jl
    def tracked_jl(path):
        inputs[str(Path(path).resolve())]=dict(sha256=sha(path),bytes=Path(path).stat().st_size)
        return original_jl(path)
    flows.jl=tracked_jl
    # Audit every opened run, including failures/HOST_ERROR; never outcome-filter.
    cases=[('beam_gate_752b0cbb',flows.beam_runs(),'m1',None,False),
           ('release_gate_4a69e6bc',flows.gcp_runs('release-gate-','release'),'m2',None,False),
           ('release_command_gate_cdace35e',flows.gcp_runs('release-command-gate-','release'),'m2',None,False)]
    prefixes=['release-center-diagnostic','release-command-diagnostic','release-diag','release-equiv',
              'release-global-diagnostic','release-look','release-v13','release11-diag','release5-diagnostic',
              'release6-diagnostic','release7-diagnostic','release8-diagnostic','release9-diagnostic','r12d','r14d','r15d']
    def release_diagnostics():
        for pre in prefixes:yield from flows.gcp_runs(pre,'release',exclude=('release-gate','release-command-gate'))
    cases.append(('release_diagnostics',release_diagnostics(),'m2',None,False))
    for pre in ('r12d','r14d'):
        cases.append((pre,flows.gcp_runs(pre,'release'),'m2',None,False))
    for stage,own in [('grasp','m1'),('release','m2')]:
        cases.append(('crate_gate_'+stage,flows.gcp_runs('crate-gate-','applied'),own,stage,False))
        def crate_diag():
            yield from flows.gcp_runs('crate-diag-','applied')
            yield from flows.gcp_runs('crate-repro','applied')
        cases.append(('crate_diagnostics_'+stage,crate_diag(),own,stage,False))
    for pre in ('solo-gate-','solo-truth-free-gate-','solo7-box-gate-','solo-diag-',
                'solo-truth-free-diag-','solo7-negative-'):
        cases.append((pre.rstrip('-'),flows.solo_runs(pre),'m1',None,True))
    for pre in ('solo-carry-93200-84a1b7b8','solo-carry-93220-870c0c59'):
        cases.append((pre,flows.solo_runs(pre),'m1',None,True))
    summaries=[];rows=[]
    for name,it,own,stage,solo in cases:
        out,per=evaluate(name,it,own,stage,solo)
        summaries.append(out);rows.extend(per)
        print(name,json.dumps(out['new'],sort_keys=True),flush=True)
    # Include status/plan evidence for every loaded run without asserting that
    # this local retrieval is an exhaustive remote inventory.
    statuses=[]
    for parent in sorted({Path(s).parent for s in inputs}):
        status={'raw':str(parent)}
        for name in ('plan.json','result.json','progress.json','RUN_META.json'):
            path=parent/name
            if path.exists():
                inputs[str(path)]=dict(sha256=sha(path),bytes=path.stat().st_size)
                if name in ('result.json','progress.json'):
                    obj=json.loads(path.read_text())
                    status[name]={k:obj[k] for k in ('source_sha','status','success','passed','reason','terminal_reason','t') if k in obj}
        statuses.append(status)
    params=DEFAULT_PARAMETERS
    result=dict(schema='ugrp.drive_model_deadband.offline.v2',
                scope='saved-command open-loop score only; no new behavior/simulation/render/remote',
                gt_scope='evaluation denominators and shared initial pose only; never model input',
                metrics='per-robot medians; full/moving path GT>0.5m separately; final position/absolute wrapped yaw error full GT>0.3m; yaw ratio nominal M1>20deg; solo yaw unavailable',
                gt_fit=dict(gains=GT_FIT_GAINS,source='odometry-scale/scripts/m3.py; beam in-sample; fixed comparator only'),
                pulse_timing='new M1 per-wheel durations; new M2 existing scalar duration; both include coast within full evaluation interval',
                parameters=vars(params),confirmed_damping_nm_s=params.damping_nm_s,
                isolated_pulse_rates=rates(drive_model_deadband_v1=True),
                yaw_reference_rad_s=1.03,
                unverified=['yaw loss ratio equals forward loss: unverified',
                            'lateral needs a separate loss coefficient; not calibrated here',
                            'inertia is a mass/XML estimate; coupled/load dynamics unverified',
                            'closed-loop behavior, hardware; only .35 in replay ledgers'],
                base_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True,cwd=ROOT).strip(),
                source_state='working tree identified by code_sha256; final commit recorded in PR',
                code_sha256={str(f.relative_to(ROOT)):sha(f) for f in
                             [Path(__file__).resolve(),ROOT/'harness/drive_model.py',
                              ROOT/'harness/grasp_act_visible_world.py',ROOT/'sim/visible_belief.py',
                              *(EXPERIMENT/'analysis_helpers').glob('*.py')]},
                flows=summaries,raw_inputs=compressed_json(args.out/'inputs.json.zst',inputs),
                per_robot=compressed_json(args.out/'per-robot.json.zst',rows),
                run_statuses=compressed_json(args.out/'run-statuses.json.zst',statuses))
    (args.out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    assert all(s['off_byte_comparison']['mismatches']==0 for s in summaries)
    lines=['# 접촉 손실·펄스 ODE 저장 원장 재생', '',
           '각 셀은 M1 / M2 / GT-fit / 새 모델 순서의 로봇별 중앙값이다. '
           'GT-fit은 기존 빔 적합 .749/.715/.719를 고정 재사용했다. 빔은 in-sample이며 새 모델에는 이 계수를 넣지 않았다.', '',
           '| 흐름 | 실행/로봇 | 최종 병진 drift mm (n) | 최종 요 drift ° (n) | 명령 구간 경로비 (n) | 요 경로비 (n) |',
           '|---|---:|---:|---:|---:|---:|']
    def cell(flow,key,scale=1,digits=2):
        stats=[flow[m][key] for m in MODELS]
        if all(s is None for s in stats):return '미측정/분모 없음 (0)'
        assert len({s['n'] for s in stats if s})==1
        return ' / '.join(f"{s['median']*scale:.{digits}f}" if s else '—' for s in stats)+f" ({stats[0]['n']})"
    for f in summaries:
        lines.append(f"| {f['flow']} | {f['runs']}/{f['robots']} | {cell(f,'final_error_m',1000,1)} | {cell(f,'final_yaw_error_deg')} | {cell(f,'moving_path_ratio',digits=3)} | {cell(f,'yaw_ratio',digits=3)} |")
    lines += ['', '- 병진/요 drift: 전체 GT 경로 >0.3 m, 공통 시작 GT 자세에서 열린고리 적분한 최종 오차. 요는 최단각 절댓값.',
              '- 명령 구간 경로비: 해당 GT 경로 >0.5 m. 요 경로비: 공칭 M1 누적 회전 >20°. solo는 저장 yaw가 없어 요 drift 미측정.',
              '- 실패·중단 포함. 진단 부분집합과 상자 grasp/release는 중복이므로 n을 합산하지 않는다. solo carry 870c0c59는 interrupted 1회다.',
              '- 84a1b7b8은 경로 임계값 미달이며 per-robot.json.zst에 비선별 원시 점수를 보존했다.',
              '- M2 비교는 기존 scalar pulse duration 규칙을 유지하며 새 모델은 남은 구간 coast까지 더한다. M1은 바퀴별 duration을 쓴다.',
              '- 요 손실이 병진과 같은 비율인지는 미확인. 횡이동의 별도 손실 계수·하중·폐루프·실물은 미검증.',
              f"- OFF 바이트 비교 {sum(f['off_byte_comparison']['ticks'] for f in summaries):,}회, 불일치 0회(중복 포함). 원본/plan/상태 {len(inputs):,}파일 SHA-256 기록.",
              '- 상세 수치/분모: [summary.json](summary.json), 전체 로봇: [per-robot.json.zst](per-robot.json.zst), 상태: [run-statuses.json.zst](run-statuses.json.zst), 원본 해시: [inputs.json.zst](inputs.json.zst).']
    (args.out/'results.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':main()
