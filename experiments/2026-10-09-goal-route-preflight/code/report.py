"""Reuse egomap56/57 scoring and unchanged gates; separate retry artifacts."""
from pathlib import Path
import argparse,importlib.util,json,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from harness.active_camera import bind
from scripts.run_goal_route_preflight import RAW,EXP,SEEDS
path=ROOT/'experiments/2026-10-09-goal-route-continuous/code/report.py'
spec=importlib.util.spec_from_file_location('p1_previous_report',path);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
score=bind(old.score,RAW=RAW,EXP=EXP)
aggregate=bind(old.aggregate,score=score,EXP=EXP)
append_readme=bind(old.append_readme,EXP=EXP)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,choices=SEEDS);p.add_argument('--append-readme',action='store_true');a=p.parse_args()
    r=score(a.seed) if a.seed else aggregate()
    if a.append_readme:append_readme(r)
    print(json.dumps(r,ensure_ascii=False,indent=2))
