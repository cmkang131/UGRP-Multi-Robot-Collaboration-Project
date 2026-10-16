from pathlib import Path
import subprocess,json,hashlib,os
repo=Path('/Users/changmin/projects/ugrp-wt/warp-act');out=Path('/tmp/ugrp-warp3-offline-seed');out.mkdir(exist_ok=False)
refs={'controller':'f0db6b1abb842ea65b71c433738210254f300a7c','teacher':'6f057f7e97c1a3aec9e8c398b8d9068e27b25df8','warm':'2b99e00d82f1f9a15769a9e41d4e599969571c9d'}
def git(*args,**kwargs):return subprocess.check_output(['git','-C',str(repo),*args],**kwargs)
ids=set(git('rev-list','--objects','--filter=blob:none','--no-object-names',*refs.values(),text=True).split())
needed_blobs=set()
for sha in refs.values():
 for row in git('ls-tree','-r','-z',sha).split(b'\0'):
  if not row:continue
  meta,path=row.split(b'\t',1);mode,kind,oid=meta.decode().split()
  if kind=='blob':needed_blobs.add(oid)
ids.update(needed_blobs)
object_list='\n'.join(sorted(ids))+'\n'
info=subprocess.run(['git','-C',str(repo),'cat-file','--batch-check=%(objecttype) %(objectsize)'],input=object_list,text=True,capture_output=True,check=True).stdout
counts={};bytes_total=0
for row in info.splitlines():
 kind,size=row.split();counts[kind]=counts.get(kind,0)+1;bytes_total+=int(size)
print(json.dumps(dict(objects=counts,uncompressed_bytes=bytes_total,selected_tree_blobs=len(needed_blobs))),flush=True)
pack=out/'objects.pack'
with pack.open('xb') as output:
 subprocess.run(['git','-C',str(repo),'pack-objects','--stdout','--compression=1','--threads=2'],input=object_list.encode(),stdout=output,check=True)
manifest=dict(refs=refs,object_counts=counts,selected_tree_blobs=len(needed_blobs),uncompressed_bytes=bytes_total,pack_bytes=pack.stat().st_size,pack_sha256=hashlib.sha256(pack.read_bytes()).hexdigest(),scope='all reachable commit/tree metadata but blobs only from the three required trees; no historical blobs or local credentials')
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest),flush=True)
