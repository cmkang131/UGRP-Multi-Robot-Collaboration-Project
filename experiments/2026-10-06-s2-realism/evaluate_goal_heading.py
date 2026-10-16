"""s2v49 post-run audit; GT is read only after the controller has closed."""
import sys,runpy,json
from pathlib import Path
raw=Path(sys.argv[1]);runpy.run_path('experiments/2026-10-06-s2-realism/evaluate_look_before_move.py',run_name='__main__')
s=json.loads((raw/'look-before-move-posthoc.json').read_text());r=json.loads((raw/'student_record.json').read_text());g=r['look_before_move']['goal_heading']
s['goal_heading']={'parameters':{'xy_goal_tolerance_m':.03,'yaw_goal_tolerance_rad':.06,'stateful':True},'trace':g['rows'],'rotations':sum(q['event']=='rotate' for q in g['rows']),'goals_reached':sum(q['event']=='goal_reached' for q in g['rows']),'final_phase':g['phase']}
s['controller_states']=[q for q in r['events'] if q['event']=='state'];s['pose_metrics_role']='information only; s2v49 success gate does not use NEES'
s['criteria_pass'].pop('nees');s['criteria_pass'].pop('unflagged');s['criteria_pass']['unconfirmed_lateral_zero']=s['look']['unconfirmed_lateral_issued']==0
s['look'].pop('goal_heading',None)
s['end_state']=r.get('state') or (s['controller_states'][-1]['state'] if s['controller_states'] else None)
s['failure_context']={'last_commands':r['commands'][-5:],'last_guard_checks':r['look_before_move']['checks'][-2:]}
old=Path('/Users/changmin/projects/ugrp/outputs')/f's2-realism-88f5fbbb-s{s["seed"]}-v135-look-before-move/result.json'
if old.exists():
 p=json.loads(old.read_text());s['time_delta_vs_v135_same_seed']={'sim_s':s['sim_s']-p['check_sim_s'],'wall_s':s['wall_s']-p['wall_s'],'scope':'failed previous run is not a completed-duration baseline'}
(raw/'goal-heading-posthoc.json').write_text(json.dumps(s,indent=2)+'\n')
print(json.dumps({'seed':s['seed'],'evaluation':s['evaluation'],'peer_contacts':s['peer_contact_points'],'goal_rotations':s['goal_heading']['rotations'],'goals_reached':s['goal_heading']['goals_reached'],'states':[(q['t'],q['state']) for q in s['controller_states']],'criteria_pass':s['criteria_pass']},indent=2))
