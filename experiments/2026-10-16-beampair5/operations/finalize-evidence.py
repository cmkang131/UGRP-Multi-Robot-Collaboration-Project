"""Only own beampair5 evidence; lossless JSON compression and ownership record."""
import pathlib,json,hashlib,subprocess,os,datetime
r=pathlib.Path('/home/ugrp/ugrp-sim');ops=r/'ops-reviews/beampair5';rawroot=r/'runs/beampair5-r1-1ead2bb9'
manifest=[]
for root in (ops,rawroot):
 for p in sorted(root.rglob('*')):
  if not p.is_file() or p.suffix not in ('.json','.jsonl') or p.stat().st_size<=65536:continue
  h=hashlib.sha256(p.read_bytes()).hexdigest();dest=pathlib.Path(str(p)+'.zst')
  if not dest.exists():subprocess.run(['zstd','-q','--keep',str(p)],check=True)
  assert hashlib.sha256(subprocess.check_output(['zstd','-qdc',str(dest)])).hexdigest()==h
  manifest.append(dict(original=str(p),compressed=str(dest),decoded_bytes=p.stat().st_size,decoded_sha256=h,compressed_bytes=dest.stat().st_size,sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
  p.unlink()
(ops/'compression-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
# Ignore this read-only finalizer process when listing owned work still running.
procs=[]
for p in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
 try:
  command=p.read_bytes().replace(b'\0',b' ').decode();exe=command.split(' ')[0]
 except (FileNotFoundError,PermissionError):continue
 if any(v in exe for v in ('python','mujoco','ffmpeg')):procs.append(dict(pid=int(p.parent.name),command=command))
leases={p.name:p.read_text() for p in (r/'leases').iterdir() if p.name!='beampair5.json'}
record=dict(task='beampair5',timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),pid=os.getpid(),other_leases=leases,processes=procs,stop_VM=False,reason='other leases exist; leave VM running; only release own lease after retrieval verification')
(ops/'host-final-before-release.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(dict(compressed_N=len(manifest),other_leases=list(leases),VM_stop=False)))
