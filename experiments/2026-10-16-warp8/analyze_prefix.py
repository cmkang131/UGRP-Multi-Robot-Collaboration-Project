"""gcp2 CPU: verify a live snapshot and summarize phases/reasons, no simulation."""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket

ROOT=Path('/home/ugrp/ugrp-sim')
p=argparse.ArgumentParser();p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--batch',default='beam40-r2');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
assert socket.gethostname().split('.')[0]=='ugrp-sim-gcp2'
assert a.snapshot.parent==ROOT/'runs' and a.batch not in ('.','..') and Path(a.batch).name==a.batch
run=a.snapshot/a.batch;lease=ROOT/'leases/warp8-prefix-analysis.json';assert not lease.exists()
lease.write_text(json.dumps(dict(task='warp8',pid=os.getpid(),started_at=dt.datetime.now(dt.timezone.utc).isoformat(),expected_end=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=15)).isoformat(),GPU=False)))
try:
 manifest=json.loads((run/'snapshot-manifest.json').read_text());mismatches=[]
 for relative,expected in manifest['files'].items():
  path=run/relative
  if path.stat().st_size!=expected['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=expected['sha256']:mismatches.append(relative)
 assert not mismatches,mismatches
 spec=importlib.util.spec_from_file_location('counter',ROOT/'ops-reviews/warp8-collect_gate.py');counter=importlib.util.module_from_spec(spec);spec.loader.exec_module(counter)
 summary=counter.data(run/'summary.json');first=counter.data(run/'first30-speed.json');progress=counter.data(run/'progress.json');phases=Counter();hist=Counter();gaps={};worlds=[];complete=[]
 for folder in sorted(run.glob('world-*')):
  if not folder.is_dir():continue
  raw=counter.data(folder/'raw/result.json',{});state=counter.data(folder/'raw/progress.json',{});diagnostic=counter.data(folder/'raw/diagnostic-snapshot.json',{});pair=tuple(sorted(state.get('phases',{}).items()));phases[pair]+=1
  worlds.append(dict(world=folder.name,raw_status=raw.get('status'),phase_progress_sim_s=state.get('sim_s'),phases=state.get('phases'),diagnostic_sim_s=diagnostic.get('sim_s'),input_audit=diagnostic.get('input_audit'),reason_source='diagnostic-snapshot teachers, falling back to terminal raw teachers'))
  if raw.get('status')=='complete':complete.append(dict(world=folder.name,recount=counter.beam_recount(raw,folder/'raw'),audit=raw.get('input_audit'),sim_s=raw.get('sim_s')))
  for reason,obj,gap in counter.reasons(diagnostic.get('teachers') or raw.get('teachers',{})):
   hist[(reason,obj)]+=1
   if isinstance(gap,(int,float)) and __import__('math').isfinite(gap):gaps[(reason,obj)]=min(gaps.get((reason,obj),float('inf')),gap)
  for trace in sorted((folder/'raw').glob('teacher-*.jsonl*')):
   if trace.suffix=='.zst' and trace.with_suffix('').exists():continue
   for row in counter.rows(trace.with_suffix('') if trace.suffix=='.zst' else trace):
    for reason,obj,gap in counter.reasons(row):
     hist[(reason,obj)]+=1
     if isinstance(gap,(int,float)) and __import__('math').isfinite(gap):gaps[(reason,obj)]=min(gaps.get((reason,obj),float('inf')),gap)
 n=summary['planned_N'];N=len(complete);success=sum(w['recount']['success'] is True for w in complete)
 result=dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),simulation_host='gcp3',analysis_host='gcp2_CPU',source_sha=summary['source_sha'],raw=str(run),first30=first,live_snapshot_progress=progress,snapshot_SHA_equal_N=len(manifest['files']),snapshot_skipped=manifest['skipped'],source_files_changed_during_read=[k for k,v in manifest['files'].items() if v['changed_during_read']],phase_distribution=[dict(phases=dict(k),N=v) for k,v in phases.most_common()],worlds=worlds,completed_recounts=complete,read_errors=counter.READ_ERRORS,reason_distribution=[dict(reason_category=k[0],blocked_object=k[1],min_gap_m=gaps.get(k),record_occurrences=v) for k,v in hist.most_common()],funnel=[dict(stage='requested',passed_cumulative_N=n,rejected_N=0),dict(stage='initialized',passed_cumulative_N=summary['started_N'],rejected_N=0),dict(stage='completed_teacher_trial',passed_cumulative_N=N,rejected_N=0,pending_N=n-N),dict(stage='physical_success',passed_cumulative_N=success,rejected_N=N-success)],scope='live per-file prefix, no full40 gate verdict; reasons are record occurrences, not unique candidate IDs; partial trailing JSONL rows remain identified in read_errors')
 a.out.mkdir(parents=True,exist_ok=False);(a.out/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(dict(completed=N,recounted_success=success,phase_distribution=result['phase_distribution'],top_reasons=result['reason_distribution'][:5],read_errors=counter.READ_ERRORS)))
finally:
 assert json.loads(lease.read_text())['pid']==os.getpid();lease.unlink()
