"""gcp2-only small summary and full evidence receipt, no new simulation."""
import hashlib,json,platform,subprocess
from pathlib import Path
R=Path('/home/ugrp/ugrp-sim/runs');B=R/'reloc20-delivery'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def obj(p):return json.loads(p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst']))
def main():
 assert platform.node().startswith('ugrp-sim-gcp2')
 if not (B/'full-report.json.zst').exists():
  subprocess.run(['zstd','-q','-f',str(B/'summary.json'),'-o',str(B/'full-report.json.zst')],check=True)
  assert hashlib.sha256(subprocess.check_output(['zstd','-dc',str(B/'full-report.json.zst')])).hexdigest()==sha(B/'summary.json')
 d=obj(B/'full-report.json')  # rerunning never replaces the full receipt with its short form
 coverage={x['run']:x for x in obj(B/'coverage.json')['runs']};records=[]
 for x in d['runs']:
  r={k:x[k] for k in ('name','round','kind','condition','seed','source_sha','raw','status','termination_normalized','raw_terminal_reason','error','failure_class','place_success','errors','aligned_command_errors','phase_metrics','gate_cumulative','input_audit','stall_enabled','stall_count','stall_sim_s','lateral_pulse_ticks','geometry_risk_sim_s','drive_errors','registered_errors','registration_frame_funnel','known_mode_measurement_funnel') if k in x}
  r['coverage']=coverage.get(x['name'])
  r['raw_receipts']=[]
  for name in ('result.json','manifest.json','artifacts.sha256.json'):
   p=Path(x['raw'])/name
   if not p.exists():p=Path(str(p)+'.zst')
   if p.exists():r['raw_receipts'].append(dict(path=str(p),stored_sha256=sha(p)))
  records.append(r)
 d['input_audit']['audit_records']=d['input_audit'].pop('measured_runs')
 d['input_audit']['controller_started_runs']=sum(x.get('failure_class')!='precontrol_configuration' for x in records)
 d['input_audit']['precontrol_zero_only']=[x['name'] for x in records if x.get('failure_class')=='precontrol_configuration']
 small={k:d[k] for k in ('schema','status','scope','rounds','attempts','carry_attempts','carry_control_started','place_success','terminations','input_audit','metric_scope','sources')}
 small.update(runs=records,full_report=dict(path=str(B/'full-report.json.zst'),stored_sha256=sha(B/'full-report.json.zst'),decoded_sha256=hashlib.sha256(subprocess.check_output(['zstd','-dc',str(B/'full-report.json.zst')])).hexdigest()),pack_script_sha256=sha(Path(__file__)))
 (B/'summary.json').write_text(json.dumps(small,separators=(',',':'))+'\n')
 manifest={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in B.iterdir() if p.is_file() and p.name!='retrieval-manifest.json'}
 (B/'retrieval-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps(dict(summary_bytes=(B/'summary.json').stat().st_size,input_audit=small['input_audit'])))
if __name__=='__main__':main()
