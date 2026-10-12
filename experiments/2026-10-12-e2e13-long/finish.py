"""Finalize only this finite batch, then verify full raw on ARM."""
import json,sys,time,subprocess,hashlib,traceback,fcntl
from pathlib import Path
sys.path.insert(0,'/usr/local/lib/ugrp-storage')
from scripts.azure_shutdown import load_native_environment,archive_one,write_json,run_processes
from scripts.compress_json_traces import compress_run
load_native_environment();root=Path.home()/'ugrp-sim';names=sys.argv[1:];done={};deadline=time.time()+7.75*3600
receipt=root/('e2e13-long-archive-'+names[0]+'.json')
# Hold the existing archive lock until evaluation/text export/compression are final.
# Auto-archive stays enabled and can safely win the race after lock release.
locks=root/'lifecycle/archive-locks';locks.mkdir(parents=True,exist_ok=True)
held={};prepared={}
for name in names:
 held[name]=(locks/(name+'.lock')).open('a');fcntl.flock(held[name],fcntl.LOCK_EX)
write_json(root/'e2e13-long-finalizer-ready.json',dict(names=names))
while len(done)<len(names) and time.time()<deadline:
 for name in names:
  run=root/'runs'/name
  if name in done or not (run/'EXIT').exists() or not (run/'final-health.json').exists():continue
  if run_processes(run):continue
  try:
   if name not in prepared:
    source=root/'src'/(run/'SOURCE_SHA').read_text().strip()
    if not (run/'postrun-evaluation/evaluation.json').exists():
     subprocess.run([str(source/'.venv-sim/bin/python'),str(source/'experiments/2026-10-11-e2e11-stall-odometry/evaluate.py'),str(run),'--output',str(run/'postrun-evaluation')],cwd=source,check=True)
    if not (run/'summary.json').exists() and not (run/'summary.json.zst').exists():
     hp=json.load((run/'final-health.json').open());rp=run/'raw/result.json'
     result=json.load(rp.open()) if rp.exists() else {}
     summary=dict(id=name,batch=name.split('-')[2].upper(),seed=int(name.split('-s')[1].split('-')[0]),
        source_sha=(run/'SOURCE_SHA').read_text().strip(),exit=int((run/'EXIT').read_text()),status=result.get('status','HOST_ERROR'),
        simulation_started=bool(hp['progress'].get('frames')),result_missing=not rp.exists(),result=result,
        initial_check=json.load((run/'initial-health.json').open()) if (run/'initial-health.json').exists() else None,
        final_health=hp,raw=str(run),raw_bytes=sum(p.stat().st_size for p in run.rglob('*') if p.is_file()),
        evaluation_only=True,feedback_to_controller=False,
        **{k:bool(result.get(k)) for k in ('LLM_operated','own_map_completed','start_to_finish_transport','E2E_success')})
     write_json(run/'summary.json',summary)
     subprocess.run(['python3',str(root/'e2e13-long-export-lite.py'),str(run)],check=True)
    summary_path=run/'summary.json'
    summary_bytes=summary_path.read_bytes() if summary_path.exists() else subprocess.check_output(['zstd','-dc',str(run/'summary.json.zst')])
    summary_sha=hashlib.sha256(summary_bytes).hexdigest()
    compression=compress_run(run,True)
    if 'skipped' in compression:continue
    prepared[name]=dict(summary_sha256=summary_sha,compression=compression)
    fcntl.flock(held[name],fcntl.LOCK_UN);held[name].close()
   archive_one(root,run)
   marker=json.load((root/'lifecycle/archives'/(name+'.json')).open())
   assert marker['verified'] and marker['native_verification']['hash_matches']==marker['native_verification']['files']
   done[name]=dict(run=name,**prepared[name],archive_marker_sha256=hashlib.sha256((root/'lifecycle/archives'/(name+'.json')).read_bytes()).hexdigest(),
       proof=marker['native_verification'],archive_bytes=sum(x['bytes'] for x in marker['inventory'].values()))
   write_json(receipt,done);print(json.dumps(done[name]),flush=True)
  except Exception as e:
   print(json.dumps(dict(run=name,error=type(e).__name__,message=str(e))),flush=True)
 time.sleep(5)
print(json.dumps(dict(completed=len(done),expected=len(names))),flush=True)
