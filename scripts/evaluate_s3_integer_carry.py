"""Post-entire-batch raw-only evaluation on Oracle; no model/render/stepping."""
import argparse,hashlib,json,math,platform
from pathlib import Path
from scripts.evaluate_s3_setdown import evaluate as pair_evaluate
from scripts.evaluate_s3_synchronized_carry import summarize,read,rows


def evaluate(raw):
 b=read(raw/'bundle.json');r=pair_evaluate(raw) if b['case']=='pair' else summarize(raw)
 r['option']=b['integer_carry']['option'];r['initial_check']=read(raw.parent/'initial-check.json')
 r['raw_source']=dict(path=str(raw),manifest_sha256=hashlib.sha256((raw/'artifacts.sha256.json').read_bytes()).hexdigest())
 if b['case']=='cyan':r.update(setdown=None,first_leg_endpoint_error_m=None,planned_pulses=None,issued_pulses=None,pulse_count_correct=None,endpoint_reached=None);return r
 ss=read(raw/'stage-states.json');start=r['robots']['r1']['carry_entry'];end=next((v['t'] for v in ss if start is not None and v['t']>start and any(x['state']!='carry' for x in v['robots'].values())),None)
 rr=read(raw/'student_record.json')
 # Plan events are preserved in the same nested records as the actual commands.
 def events(v):
  if isinstance(v,dict):
   if v.get('event')=='synchronized_carry_plan':yield v
   else:
    for x in v.values():yield from events(x)
  elif isinstance(v,list):
   for x in v:yield from events(x)
 pp={e['robot_id']:e['pulses'] for e in events(rr) if e.get('seg')==0}
 issued={rid:[c for c in rows(raw/f'robots/{rid}/commands.jsonl') if start is not None and end is not None and start<=c['t']<=end and c.get('kind')=='mecanum' and any(c.get(k,0) for k in ('forward','left','turn'))] for rid in ('r1','r2')}
 r.update(planned_pulses=pp,issued_pulses={rid:len(v) for rid,v in issued.items()},pulse_count_correct=set(pp)=={'r1','r2'} and all(len(issued[rid])==pp[rid]==12 for rid in pp),endpoint_reached=r.get('first_leg_endpoint_error_m',math.inf)<=.020)
 r['command_sync']=bool(issued['r1']) and len(issued['r1'])==len(issued['r2']) and all(a['t']==bb['t'] and all(a.get(k,0)==-bb.get(k,0) for k in ('forward','left','turn')) for a,bb in zip(issued['r1'],issued['r2']))
 return r


def main():
 p=argparse.ArgumentParser();p.add_argument('--cohort',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if platform.system()!='Linux' or platform.machine()!='x86_64':raise ValueError('Oracle only')
 cc=read(a.cohort/'cohort.json');assert len(cc)==20
 results=[dict(name=x['name'],**evaluate(a.cohort/x['name']/'raw')) for x in cc]
 by={}
 for o in ('off','integer_ticks_v1'):
  rr=[r for r in results if r['option']==o];pair=[r for r in rr if r['case']=='pair'];cyan=[r for r in rr if r['case']=='cyan']
  by[o]=dict(n=len(rr),pair_n=len(pair),cyan_n=len(cyan),counts={k:sum(r['joint'][k] for r in rr) for k in ('alignment','grasp','lift','carry')},pulse_count_correct=sum(r['pulse_count_correct'] for r in pair),endpoint_reached=sum(r['endpoint_reached'] for r in pair),setdown=sum(r['setdown'] for r in pair),drop_aborts=sum(r['drop_aborts'] for r in rr),tilt_aborts=sum(r['tilt_aborts'] for r in rr),host_errors=sum(r['status']=='HOST_ERROR' for r in rr),cyan_regression_carry=sum(r['joint']['carry'] for r in cyan))
 gate=by['integer_ticks_v1'];passed=all(gate[k]==6 for k in ('pulse_count_correct','endpoint_reached','setdown')) and gate['cyan_regression_carry']==4 and gate['drop_aborts']==gate['tilt_aborts']==gate['host_errors']==0
 summary=dict(host='oracle-x86',n=20,runs=results,by_option=by,second_stage_gate_passed=passed,initial_checks_healthy=sum(r['initial_check']['healthy'] for r in results))
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='runs'}))
if __name__=='__main__':raise SystemExit(main())
