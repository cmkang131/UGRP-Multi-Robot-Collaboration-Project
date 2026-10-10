"""Reuse egomap58 scoring and unchanged gates; separate retry artifacts."""
from pathlib import Path
import argparse,importlib.util,json,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from harness.active_camera import bind
from scripts.run_goal_route_motion_audit import RAW,EXP,SEEDS
path=ROOT/'experiments/2026-10-09-goal-route-continuous/code/report.py'
spec=importlib.util.spec_from_file_location('p1_previous_report',path);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
base_score=bind(old.score,RAW=RAW,EXP=EXP)
audit_spec=importlib.util.spec_from_file_location('p1_motion_diagnostic',EXP/'code/diagnose.py')
audit=importlib.util.module_from_spec(audit_spec);audit_spec.loader.exec_module(audit)
current_audit=bind(audit.audit,BASE=RAW)

def score(seed):
    r=base_score(seed)
    if r.get('error_samples'):
        d,_=current_audit(seed)
        r['motion_audit']={k:d[k] for k in ('dr_path_m','posterior_path_m','actual_path_m','dr_to_actual',
            'posterior_to_actual','correction_norm_sum_m','pulse_groups','command_replay_sha256')}
        (EXP/'results'/f'{seed}.json').write_text(json.dumps(r,indent=2)+'\n')
    return r

aggregate=bind(old.aggregate,score=score,EXP=EXP)
base_append=bind(old.append_readme,EXP=EXP)

def append_readme(r):
    base_append(r)
    if r.get('motion_audit'):
        d=r['motion_audit']
        with (EXP/'README.md').open('a') as f:
            f.write(f"\n명령 DR/GT {d['dr_path_m']:.3f}/{d['actual_path_m']:.3f}m={d['dr_to_actual']:.3f}배; "
                    f"위 표의 자기 거리는 posterior 궤적이며 {d['posterior_path_m']:.3f}m, "
                    f"보정 잔차 길이 합 {d['correction_norm_sum_m']:.3f}m(실제 주행 거리 아님).\n")

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,choices=SEEDS);p.add_argument('--append-readme',action='store_true');a=p.parse_args()
    r=score(a.seed) if a.seed else aggregate()
    if a.append_readme:append_readme(r)
    print(json.dumps(r,ensure_ascii=False,indent=2))
