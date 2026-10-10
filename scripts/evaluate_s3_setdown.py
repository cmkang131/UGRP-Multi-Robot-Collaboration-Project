"""Raw-only post-batch evaluation, no images, physics or TensorBoard conversion."""
import argparse,hashlib,json,platform
from pathlib import Path
from scripts.evaluate_s3_synchronized_carry import summarize,rows,read,sustained

def evaluate(raw):
 r=summarize(raw);rr=rows(raw/'eval_only/setdown.jsonl');states=read(raw/'stage-states.json')
 lower=next((x['t'] for x in states if all(v['state']=='lower' for v in x['robots'].values())),None)
 open_time={rid:next((c['t'] for c in rows(raw/f'robots/{rid}/commands.jsonl') if lower is not None and c['t']>=lower and c.get('servo_id')==1 and c.get('pulse',0)>1500),None) for rid in ('r1','r2')}
 full_open={rid:next((c['t'] for c in rows(raw/f'robots/{rid}/commands.jsonl') if lower is not None and c['t']>=lower and c.get('servo_id')==1 and c.get('pulse')==2000),None) for rid in ('r1','r2')}
 floor_first=next((x['t'] for x in rr if lower is not None and x['t']>=lower and x['floor_normal_n']>=.1),None)
 released=max(full_open.values()) if all(v is not None for v in full_open.values()) else None
 times=[x['t'] for x in rr if released is not None and x['t']>=released and x['floor_normal_n']>=.1 and x['cargo_z_m']<=.025 and abs(x['vertical_speed_m_s'])<=.02 and x['cargo_tilt_deg']<10.]
 failures={rid:v['failure'] for rid,v in (r['final_controller_states'] or {}).items() if v.get('failure')}
 r.update(setdown=sustained(times) is not None and not failures and r['status'] not in ('HOST_ERROR','PHYSICAL_STOP','EARLY_STOP'),lower_start=lower,first_open_change=open_time,full_open=full_open,floor_first=floor_first,open_before_floor=any(t is not None and (floor_first is None or t<floor_first) for t in open_time.values()),controller_failures=failures,option=read(raw/'bundle.json')['setdown']['option'])
 r['corrected_guard_samples']=len(rows(raw/'eval_only/setdown-classification.jsonl')) if (raw/'eval_only/setdown-classification.jsonl').exists() else 0
 r['initial_check']=read(raw.parent/'initial-check.json')
 r['raw_source']=dict(path=str(raw),manifest_sha256=hashlib.sha256((raw/'artifacts.sha256.json').read_bytes()).hexdigest())
 # Source endpoints are fixed public geometry, used here only for evaluation.
 rec=read(raw/'student_record.json');route=rec['pair']['pair'][0]['plan']['route'];carry=r['robots']['r1']['carry_entry']
 end=next((x['t'] for x in states if carry is not None and x['t']>carry and any(v['state']!='carry' for v in x['robots'].values())),None)
 truth=[x for x in rows(raw/'eval_only/referee_truth.jsonl') if end is not None and x['t']<=end]
 if truth:
  import math
  p=truth[-1]['items']['beam_1'];r['first_leg_endpoint_error_m']=math.dist([p['x'],p['y']],route[1])
 return r

def main():
 p=argparse.ArgumentParser();p.add_argument('--cohort',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if platform.system()!='Linux' or platform.machine()!='x86_64':raise ValueError('Oracle evaluation only')
 cohort=read(a.cohort/'cohort.json');assert len(cohort)==10
 results=[dict(name=x['name'],**evaluate(a.cohort/x['name']/'raw')) for x in cohort]
 summary=dict(host='oracle-x86',n=10,runs=results,counts={k:sum(r['joint'][k] for r in results) for k in ('alignment','grasp','lift','carry','target_distance')},setdown=sum(r['setdown'] for r in results),physical_stops=sum(r['status']=='PHYSICAL_STOP' for r in results),host_errors=sum(r['status']=='HOST_ERROR' for r in results),initial_checks_healthy=sum(r['initial_check']['healthy'] for r in results))
 summary['by_option']={o:dict(n=len(rr),setdown=sum(r['setdown'] for r in rr),core_n=sum(r['condition'] in (2,5) for r in rr),core_setdown=sum(r['setdown'] and r['condition'] in (2,5) for r in rr)) for o in ('off','canonical_floor_v1','slow_final_v1','settle_floor_v1') for rr in [[r for r in results if r['option']==o]]}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='runs'}))
if __name__=='__main__':raise SystemExit(main())
