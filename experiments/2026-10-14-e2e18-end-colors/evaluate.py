"""Post-run evaluation only; same stance metric, separated appearance/cohorts."""
import collections,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.e2e_stage_pose_eval import read
spec=importlib.util.spec_from_file_location('previous_eval',ROOT/'experiments/2026-10-14-e2e18-end-assignment/evaluate_stage.py')
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
rows=[]
for p in sorted((ROOT/'outputs/azure3-runs').glob(sys.argv[1])):
    row=previous.evaluate(p);plan=read(p/'STAGE_PLAN.json');bundle=read(p/'raw/bundle.json');events=read(p/'raw/transport-trace.json')
    row['analysis_set']=plan['analysis_set'];row['appearance']=bundle['e2e_options'].get('end_color_scene','off')
    row['legacy_raw_first_attempt_success']=row['first_attempt_success']
    row['color_search_views']=dict(collections.Counter(e['robot_id'] for e in events if e.get('event')=='own_color_search_view'))
    row['first_attempt_success']=row['first_attempt_success'] and not any(row['color_search_views'].values())
    rows.append(row)
groups={}
for cohort in sorted({r['analysis_set'] for r in rows}):
 for condition in sorted({r['condition'] for r in rows}):
    rs=[r for r in rows if r['analysis_set']==cohort and r['condition']==condition and r['eligible_for_denominator']]
    groups[cohort+'/'+condition]=dict(N=len(rs),opposite=sum(r['relation']=='opposite' for r in rs),simultaneous_opposite=sum(r['simultaneous_opposite'] for r in rs),relations=dict(collections.Counter(r['relation'] for r in rs)),both_held=sum(r['both_held'] for r in rs),first_attempt_success=sum(r['first_attempt_success'] for r in rs),ready_wait_sim_s=[v['ready_wait_sim_s'] for r in rs for v in r['robots'].values() if v.get('ready_wait_sim_s') is not None])
out=dict(evaluation_only=True,first_attempt_definition='conservative common criterion: held without any legacy acquisition entry or new color search view; raw legacy field retained separately',stance_offset_m=.4732,threshold_m=.25,groups=groups,runs=rows)
Path(sys.argv[2]).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(groups))
