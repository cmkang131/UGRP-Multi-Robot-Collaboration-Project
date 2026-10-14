"""Emit the operations handoff after commit/push; does not submit any run."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
EXP = Path(__file__).resolve().parent
ADMIN = Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin')


def main():
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    assert branch == 'claude/act-crate-teacher'
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
    remote = subprocess.check_output(['git', 'ls-remote', 'origin', 'refs/heads/'+branch], cwd=ROOT, text=True).split()[0]
    assert remote == sha
    short = sha[:8]
    oldpath = ADMIN/'vm3-queue/20261014-crate-6f312f74.json'
    old = json.loads(oldpath.read_text())
    q = copy.deepcopy(old)
    offline = json.loads((EXP/'crate4-offline-summary.json').read_text())
    plans = [('diagnostic', 'diag_plan_crate4_reproductions.json'),
             ('diagnostic', 'diag_plan_v5_77920.json'), ('diagnostic', 'diag_plan_v6_77930.json'),
             ('gate', 'gate_plan_v7_77300.json')]
    q.update(owner='codex-crate4', sha=sha, remote_verified_sha=remote, created_utc=datetime.now(timezone.utc).isoformat(),
        status='ready', ready=True, runs_enabled=True, supersedes=[oldpath.name],
        profile='crate_mass_030_v1 / crate_lug_colors_v1 / hidden_v1 / align_relook_v1 / search_reacquire_v1 / approach_goal_set_v1 / crate_rgb_lift_v3 / backoff_v3 / pad_window_v2 / zone slots / own pose commands / weld OFF / training RGB OFF / lookaround OFF',
        purpose='A 77208/77212 + B 77204/77231 + original six diagnostics, then fresh 77300-77339 gate',
        order='회수/정확 RGB 재판정/영상 검토 -> 진단10 -> 새 관문40. 단계 직렬, 전체 동시 최대16. 새 후보의 첫 동시16/30 SIM초 속도 확인 후 다음 wave. 원인 확인 시 즉시 정지.',
        run_count=50, stage_counts={'diagnostic':10,'gate':40}, max_combined_concurrency=16,
        max_parallel_per_stage=16, stage_max_parallel={'diagnostic':10,'gate':16},
        storage_budget_mib={'diagnostic':640,'gate':2560,'total_new_raw_upper_estimate':3200,
                            'scope':'64 MiB per run; source/archive duplication also budgeted'},
        pooling='Only this SHA/profile on gcp1 n4-highcpu-64; diagnostics excluded; do not pool baseline/other-host/0.9 kg negatives',
        candidate_record={'record':str(EXP/'crate4.md'), 'local_tests':'101 passed, 1 skipped, 1 deselected; 3 files',
                          'offline_replay':offline['groups'], 'negative_controls_replayed':'0/2',
                          'new_gcp_runs':0, 'runtime_audit':'unverified'},
        offline_preflight={'status':'awaiting_original_RGB_and_video_review',
            'fetch_request':str(ADMIN/'fetch-requests/crate4.txt'),
            'required':'B confirmed 8/8; old-success unchanged 24/24; failed-lift negative controls replayed 2/2 with FP=0; unknown blocks',
            'command':['/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python','-m','scripts.replay_crate_lift',
                       '--root','/Users/changmin/projects/ugrp/outputs/gcp1-runs',
                       '--negative-sequences',str(EXP/'crate4-negative-sequences.json'),
                       '--out',str(ADMIN/f'crate4-offline-{short}.json'),'--require-ready']},
        worktree_hold=f'Keep source_worktree at {sha} until operations snapshots it; no execution by this coding session',
        report_needed='All runs including failures/HOST_ERROR, raw hashes, exact input audit, per-robot RGB unknown/FP/FN, n/N, first30 speed, video range',
        merged_search_sha='a3f3be78f5547d7b44396cab38b6e57354b4a49d')
    for key in ('superseded_reason','superseded_by','superseded_utc'):
        q.pop(key,None)
    q['criteria'].update(diagnostic_required=10,diagnostic_N=10,
        denominators='fresh gate full grasp+release >=38/40; diagnostics 10/10 excluded; no missing/HOST_ERROR exclusions',
        rgb_lift='crate_rgb_lift_v3: both confirmed; unknown blocks release; truth evaluation only')
    q['criteria']['start_los'].update(gate_both_pass='40/40',original_rejected='14/40 (35%)')
    q['seed_reservation']={'diagnostic_reproductions':[77204,77208,77212,77231],
        'diagnostic_reused_unchanged':[77920,77921,77922,77930,77931,77932],
        'fresh_gate_inclusive':[77300,77339],'split':'crate_gate_v4','never_train':True}
    q['speed_limit'].update(basis='Goal-set planning cost changed: previous speed is reference only; inspect first new gate wave at concurrency16 for 30 SIM seconds before further waves',
                           existing_record='reference only: crate-gate-6f312f74 median 3.16; not new-profile qualification')
    q['preconditions']=[
        'DO NOT SUBMIT while offline_preflight command exits nonzero or original-video review is incomplete; ready=true means a reviewable queue, not evidence passed',
        'Review six uniformly spaced timestamps per A/B case with overview/r1/r2; document actual seen range before claiming visual root cause',
        'Frozen clean source and remote SHA must match; preserve project cost stop, 8h VM cap, 20min idle stop; GCP only; no failover on cost stop',
        'Storage budget across GCP/ARM/Mac, all queued reserved writes, and total concurrency <=16 before each stage',
        'All ten diagnostics on this SHA must be full-chain success, distinct assigned lugs, both RGB confirmed and invisible_measurements=held_world_reads=0',
        'Review first30 raw, issued search revolutions, side approach contact/grasp and RGB; stop same-defect running/pending jobs immediately',
        'No gate until diagnostics pass; review first gate wave30 speed <=3.5 wall/SIM before proceeding; failures/HOST_ERROR stay in N=40',
        'Capture original before/lift_complete/settled own frames with exact times/hashes; unknown blocks; stalled-arm ambiguity requires negative controls',
        'Retrieve and hash all lightweight evidence and required videos; incomplete retrieval is not completion']
    template=copy.deepcopy(old['runs'][0]);q['runs']=[];q['plan_sha256']={}
    for stage, filename in plans:
        path=EXP/filename;plan=json.loads(path.read_text())
        q['plan_sha256'][filename]=hashlib.sha256(path.read_bytes()).hexdigest()
        for index,episode in enumerate(plan['episodes']):
            seed=episode['seed'];name=f'crate-{stage if stage=="gate" else "diag"}-{seed}-{short}'
            row=copy.deepcopy(template)
            payload=['.venv-sim/bin/python','-m','scripts.run_crate_teacher','--plan',str(path.relative_to(ROOT)),
                     '--episode',str(index),'--grasp-cap-s','80','--cap-s','90','--observe-mode','backoff_v3',
                     '--zone-slots','zone','--reach-mode','pad_window_v2','--own-pose-source','commands',
                     '--held-object','hidden_v1','--setdown-lookaround','off','--crate-scene','crate_mass_030_v1',
                     '--rgb-lift','crate_rgb_lift_v3','--teacher-stability','align_relook_v1',
                     '--teacher-search','search_reacquire_v1','--approach-goal-set','approach_goal_set_v1',
                     '--execution-host','gcp1','--pr','500','--out',f'/home/ugrp/ugrp-sim/runs/{name}/raw']
            row.update(stage=stage,seed=seed,scenario_id=episode['scenario_id'],name=name,ready=True,
                max_parallel=10 if stage=='diagnostic' else 16,max_other_running=6 if stage=='diagnostic' else 0,
                condition='offline_preflight exit0 + original-video review; '+('all 10 diagnostics pass before gate; first-wave30 speed check' if stage=='gate' else 'diagnostic stage only; stop on confirmed defect'),
                payload=payload,command=['python3','scripts/remote_run.py','--host','gcp1','--detach','--class','dev',
                    '--pr','500','--per-run-mb','64',str(ROOT),name,'--',*payload],maximum_sim_s_per_episode=170)
            q['runs'].append(row)
    assert len(q['runs'])==50 and len({r['name'] for r in q['runs']})==50
    assert [r['seed'] for r in q['runs'] if r['stage']=='gate']==list(range(77300,77340))
    dest=ADMIN/f'vm3-queue/20261014-crate-{short}.json'
    dest.write_text(json.dumps(q,ensure_ascii=False,indent=2)+'\n')
    old.update(status='superseded',ready=False,runs_enabled=False,superseded_by=dest.name,
               superseded_utc=datetime.now(timezone.utc).isoformat())
    for row in old['runs']:row['ready']=False
    oldpath.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n')
    assert json.loads(dest.read_text())['sha']==sha
    print(json.dumps({'path':str(dest),'sha':sha,'ready':True,'runs':len(q['runs']),
                      'offline_preflight':'pending; must pass before submission'}))


if __name__=='__main__':main()
