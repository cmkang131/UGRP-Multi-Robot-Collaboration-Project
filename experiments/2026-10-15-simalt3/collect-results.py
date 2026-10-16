from pathlib import Path
import csv,datetime as dt,hashlib,json,os,signal,subprocess,tarfile,time
root=Path('/home/ugrp/ugrp-sim/runs/simalt3')
write=lambda p,d:p.write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
run_names=['cpu-n1','warp-n1','cpu316-n1']+[f'warp-n{n}-forward' for n in [16,64,128,256]]+[f'warp-n{n}-forward-rgb' for n in [1,16,64,128,256]]
reports={}
for name in run_names:
 p=root/name/'result.json';r=json.loads(p.read_text())
 if r['status'] not in ['complete','rejected','cap_end','HOST_ERROR']:raise RuntimeError('not terminal: '+name)
 reports[name]=r
# Stop only this task's telemetry process after its last measurement has ended.
monitor=json.loads((root/'gpu-monitor.json').read_text());pid=monitor['pid']
proc=Path(f'/proc/{pid}/cmdline')
if proc.exists():
 cmd=proc.read_bytes().replace(b'\0',b' ').decode()
 if 'nvidia-smi' not in cmd or '--query-gpu=timestamp,memory.used,memory.total,utilization.gpu' not in cmd:raise RuntimeError('telemetry PID ownership mismatch')
 os.kill(pid,signal.SIGTERM);time.sleep(.2)
rows=[]
for row in csv.reader((root/'gpu-memory.csv').read_text().splitlines()):
 try:
  timestamp=dt.datetime.strptime(row[0].strip(),'%Y/%m/%d %H:%M:%S.%f').replace(tzinfo=dt.timezone.utc).timestamp()
  rows.append((timestamp,int(row[1]),int(row[2]),int(row[3])))
 except (ValueError,IndexError):continue
memory={}
for name,r in reports.items():
 end=(root/name/'result.json').stat().st_mtime;start=end-r['wall_s']
 samples=[x for x in rows if start<=x[0]<=end]
 memory[name]={'sample_hz':1,'sampled_peak_MiB':max((x[1] for x in samples),default=None),'samples':len(samples),'nominal_window_utc':[dt.datetime.fromtimestamp(t,dt.timezone.utc).isoformat() for t in [start,end]],'basis':'result file mtime minus measured run wall; sampled, not allocator peak'}
 write(root/name/'RUN_META.json',{'class':'dev','pr':524,'branch':'claude/simalt-pilot','sha':r['sha'],'script_sha256':r['script_sha256'],'batch':'simalt3','name':name,'nworld':r['nworld'],'training':False})
write(root/'measurements.json',{'reports':reports,'memory':memory,'expected_jobs':len(run_names),'completed_jobs':sum(r['status']=='complete' for r in reports.values()),'HOST_ERROR':sum(r['HOST_ERROR'] for r in reports.values()),'cap_end':sum(bool(r['cap_end']) for r in reports.values()),'failed_runs':sum(r['failure'] for r in reports.values()),'rejected_equivalence_is_separate':True,'source_batches':{'25bf9995':'C3.12 reference + Warp N1 suite','737f5a0e':'C3.16 control + physics-only N16/64/128/256','01cd2a9c':'batch RGB N1/16/64/128/256; physics unchanged, camera transform sync and logging added'}})
audit=json.loads((root/'audit/result.json').read_text())
write(root/'audit-summary.json',{k:v for k,v in audit.items() if k not in ['fresh','before_put_data','traceback']})
commands={'kernel':['uname','-a'],'cpu':['lscpu','--json'],'disk':['df','-B1','/'],'gpu':['nvidia-smi'],'compute_apps':['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv,noheader'],'idle_timer':['systemctl','is-active','ugrp-idle-guard.timer']}
env={}
for k,cmd in commands.items():
 p=subprocess.run(cmd,capture_output=True,text=True);env[k]={'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
env['credential_path_presence']={p:str((Path.home()/p).exists()) for p in ['.config/gcloud/credentials.db','.kaggle/kaggle.json','.codex/auth.json','.claude/.credentials.json','.boto']}
env['idle_guard_sha256']=sha(Path('/usr/local/sbin/ugrp-idle-guard'))
env['teacher_archive_sha256']=sha(root/'runtime/teacher-6f057f7e.tar.gz')
env['source_teacher_sha']='6f057f7e97c1a3aec9e8c398b8d9068e27b25df8'
env['collection_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
write(root/'environment-final.json',env)
# New VM evidence only: lossless JSON compression explicitly required by disk policy.
# Decompress and verify full content before removing an uncompressed representation.
excluded_dirs={'c-env','warp-env'}
def raw_files():
 for p in root.rglob('*'):
  rel=p.relative_to(root)
  if not p.is_file() or rel.parts[0] in excluded_dirs or rel.parts[:2]==('runtime','source') or '__pycache__' in rel.parts:continue
  yield p
compression=[]
for p in list(raw_files()):
 if p.suffix not in ['.json','.jsonl'] or p.stat().st_size<=65536:continue
 digest=sha(p);target=p.with_suffix(p.suffix+'.zst')
 subprocess.run(['zstd','-q','-3','-f',str(p),'-o',str(target)],check=True)
 restored=subprocess.check_output(['zstd','-q','-d','-c',str(target)])
 if hashlib.sha256(restored).hexdigest()!=digest:raise RuntimeError('compression mismatch: '+str(p))
 compression.append({'original':str(p.relative_to(root)),'stored':str(target.relative_to(root)),'uncompressed_sha256':digest,'compressed_sha256':sha(target),'uncompressed_bytes':p.stat().st_size,'compressed_bytes':target.stat().st_size,'restored_full_hash_verified':True})
 p.unlink()
write(root/'compression-map.json',compression)
self_exclude={'SHA256SUMS','raw-verification.json','lite-results.tar.gz','lite-delivery.json'}
files=sorted(p for p in raw_files() if p.name not in self_exclude)
entries={str(p.relative_to(root)):sha(p) for p in files}
(root/'SHA256SUMS').write_text(''.join(f'{v}  {k}\n' for k,v in entries.items()))
fail=[k for k,v in entries.items() if sha(root/k)!=v]
write(root/'raw-verification.json',{'checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),'files':len(entries),'mismatches':fail,'bytes':sum((root/k).stat().st_size for k in entries),'exclusions':['installed c-env/warp-env','expanded frozen teacher source covered by archive hash','__pycache__','self-referential manifest/verification/delivery files'],'raw_root':str(root),'storage':'persistent L4 boot disk; full raw not copied to Mac','all_raw_SHA256_pass':not fail})
if fail:raise RuntimeError('raw verification mismatch')
lite=[root/n for n in ['measurements.json','audit-summary.json','environment-final.json','compression-map.json','SHA256SUMS','raw-verification.json','comparison.json','comparison-cpu316.json','contact-distribution.json','partial-alpha-geoms.json','RUN_META.json','fixture/fixture.json','c-freeze.txt','warp-freeze.txt']]
for name in run_names:
 lite.extend(root/name/n for n in ['result.json','rejection_table.json','RUN_META.json'])
with tarfile.open(root/'lite-results.tar.gz','w:gz') as tar:
 for p in lite:
  if not p.exists():
   compressed=p.with_suffix(p.suffix+'.zst')
   if not compressed.exists():raise RuntimeError('lite file missing: '+str(p))
   p=compressed
  tar.add(p,arcname=str(p.relative_to(root)))
write(root/'lite-delivery.json',{'path':str(root/'lite-results.tar.gz'),'bytes':(root/'lite-results.tar.gz').stat().st_size,'sha256':sha(root/'lite-results.tar.gz'),'files':len(lite),'raw_verification':json.loads((root/'raw-verification.json').read_text())})
print((root/'lite-delivery.json').read_text())
