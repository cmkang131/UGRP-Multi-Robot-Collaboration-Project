"""s2v51 condition A posthoc only; no controller inputs or outcome tuning."""
import sys,runpy,json
from pathlib import Path
raw=Path(sys.argv[1])
runpy.run_path('experiments/2026-10-06-s2-realism/evaluate_goal_heading.py',run_name='__main__')
s=json.loads((raw/'goal-heading-posthoc.json').read_text())
s['pose_metrics_role']='information only; s2v51 gate does not use NEES'
s['criteria_pass']['success']=all(s['evaluation'].get(k) for k in ('success','lifted','inside','stable'))
s['criteria_pass']['uncertified_navigation_lateral_zero']=s['criteria_pass'].pop('unconfirmed_lateral_zero')
s['final_approach_scope']='staging_v133_v1; unobserved final lateral allowed explicitly; no appearance monitor'
s['navigation_scope']='search_move/carry retain rgb_sweep_v1 and v136 stateful goal heading'
old=raw.parent/f's2-realism-4436222c-s{s["seed"]}-v136-goal-heading/result.json'
if old.exists():
 p=json.loads(old.read_text());s['time_delta_vs_v136_same_seed']={'sim_s':s['sim_s']-p['check_sim_s'],'wall_s':s['wall_s']-p['wall_s'],'scope':'previous failure is not a completed-duration baseline'}
(raw/'staging-only-posthoc.json').write_text(json.dumps(s,indent=2)+'\n')
print(json.dumps({k:s[k] for k in ('seed','evaluation','peer_contact_points','wall_s','sim_s','criteria_pass','pose')},indent=2))
