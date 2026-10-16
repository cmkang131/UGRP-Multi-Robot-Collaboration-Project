"""Persistent tar transport; native full-file SHA verification on both hosts.

Only generated transport copies are removed. Azure raw and published ARM raw
are retained. Mac receives manifests, never media or the tar stream.
"""
import hashlib
import inspect
import json
import re


def remaining_run_bytes(root):
    """Reserve queued groups and all active sibling groups before new writes."""
    from pathlib import Path
    import json
    peak=768*2**20
    groups={}
    over_peak=[]
    for group in Path(root).glob('egojump-63*-*-r*'):
        if not group.is_dir() or (group/'EXIT').exists():continue
        try:
            jobs=json.loads((group/'data/batch-status.json').read_text())
        except (FileNotFoundError,json.JSONDecodeError):
            groups[group.name]=3*peak
            continue
        if len(jobs)!=3:
            groups[group.name]=3*peak
            continue
        remaining=0
        for job in jobs:
            if 'exit_code' in job:continue
            used=sum(p.stat().st_size for p in Path(job['root']).rglob('*') if p.is_file())
            if used>peak:over_peak.append(job['root'])
            remaining+=max(0,peak-used)
        groups[group.name]=remaining
    return dict(bytes=sum(groups.values()),groups=groups,over_peak=over_peak)


def inventory(folder):
    import os
    import hashlib
    from pathlib import Path
    result={}
    for directory,dirs,names in os.walk(folder):
        dirs.sort()
        for name in sorted(names):
            p=Path(directory)/name;k=p.relative_to(folder).as_posix()
            if p.is_symlink():result[k]={'symlink':os.readlink(p)}
            elif p.is_file():
                before=p.stat()
                with p.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
                after=p.stat()
                if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                    raise RuntimeError('FILE_CHANGED_WHILE_HASHING')
                result[k]={'bytes':after.st_size,'sha256':sha}
        for name in dirs[:]:
            p=Path(directory)/name
            if p.is_symlink():result[p.relative_to(folder).as_posix()]={'symlink':os.readlink(p)};dirs.remove(name)
    return result


def run(remote,host,payload,body):
    prefix='import os,sys,json,hashlib,subprocess,shutil\nfrom pathlib import Path\n'
    script=prefix+inspect.getsource(inventory)+inspect.getsource(remaining_run_bytes)+'\nx=json.loads('+repr(json.dumps(payload))+')\n'+body
    command='taskset -c 0-11 python3 -' if host=='azure' else 'python3 -'
    r=remote.ssh(host,command,input=script,capture_output=True,text=True,timeout=900)
    return json.loads(r.stdout)


def archive(remote,name,job=None):
    if not re.fullmatch(r'egojump-63\d{3}-[0-9a-f]{8}-r\d+',name):raise ValueError('OWN_GROUP_NAME')
    if job is not None and not re.fullmatch(r'63\d{3}-(off|cluster|innovation)',job):raise ValueError('OWN_JOB_NAME')
    destination='shutdown-'+name if job is None else name+'-'+job
    x=dict(name=name,job=job,destination=destination)
    prepared=run(remote,'azure',x,'''
sys.path.insert(0,"/usr/local/lib/ugrp-storage")
from scripts.azure_shutdown import run_processes,source_state
root=Path.home()/"ugrp-sim";group=root/"runs"/x["name"]
source=group if x["job"] is None else group/"data"/x["job"]
where=(root/"lifecycle/archives"/(x["name"]+".json") if x["job"] is None else group/"per-run-archives"/(x["job"]+".json"))
known=None
if where.exists():known=json.loads(where.read_text())
elif where.with_suffix(where.suffix+".zst").exists():known=json.loads(subprocess.check_output(["zstd","-qdc",str(where)+".zst"]))
if known and known.get("verified") and Path(known["path"]).is_dir() and known["inventory"]==inventory(source) and (x["job"] is not None or known.get("source_state")==source_state(source)):
    print(json.dumps(dict(cached=known)));raise SystemExit(0)
if source.is_symlink() or not (source/"EXIT").exists() or run_processes(source):raise RuntimeError("COMPLETED_OWN_SOURCE_REQUIRED")
subprocess.run([sys.executable,"/usr/local/lib/ugrp-storage/scripts/compress_json_traces.py",str(source),"--execute"],check=True,capture_output=True)
hashes=inventory(source);state=source_state(source);size=sum(v.get("bytes",0) for v in hashes.values())
reservation=remaining_run_bytes(root/"runs")
remaining=reservation["bytes"]
estimate=size+64*2**20
if shutil.disk_usage(source).free-estimate-remaining-1024*2**20<8*2**30:raise RuntimeError("TRANSPORT_X86_BUDGET")
if shutil.disk_usage(root/"arm").free-2*estimate-3*768*2**20<25*2**30:raise RuntimeError("TRANSPORT_ARM_BUDGET")
transit=root/"archive-transit";transit.mkdir(exist_ok=True)
pack=transit/(x["destination"]+".tar.zst")
if pack.exists():raise RuntimeError("UNFINISHED_TRANSPORT_PRESERVED")
subprocess.run(["tar","-I","zstd -T1 -3","-cf",str(pack),"-C",str(source),"."],check=True,capture_output=True)
with pack.open("rb") as f:packed_sha=hashlib.file_digest(f,"sha256").hexdigest()
if inventory(source)!=hashes or source_state(source)!=state:raise RuntimeError("SOURCE_CHANGED_DURING_PACK")
transfer=root/"arm"/(".transport-"+x["destination"]+"-"+packed_sha[:12]+".tar.zst")
if transfer.exists():raise RuntimeError("UNFINISHED_ARM_TRANSPORT_PRESERVED")
shutil.copyfile(pack,transfer)
with transfer.open("rb") as f:os.fsync(f.fileno())
print(json.dumps(dict(inventory=hashes,source_state=state,source=str(source),bytes=size,pack=str(pack),transfer=transfer.name,pack_sha256=packed_sha,pack_bytes=pack.stat().st_size)))
''')
    if 'cached' in prepared:return prepared['cached']
    proof=run(remote,'oracle-codex',dict(x,prepared=prepared),'''
root=Path.home()/"ugrp-archive/runs";p=x["prepared"];pack=root/p["transfer"]
with pack.open("rb") as f:actual=hashlib.file_digest(f,"sha256").hexdigest()
if actual!=p["pack_sha256"]:raise RuntimeError("TRANSPORT_SHA_MISMATCH")
target=root/x["destination"]
if not target.exists():
    incoming=root/(".incoming-pack-"+x["destination"]+"-"+actual[:12])
    incoming.mkdir(exist_ok=False)
    subprocess.run(["tar","--zstd","--no-same-owner","-xf",str(pack),"-C",str(incoming)],check=True,capture_output=True)
    if inventory(incoming)!=p["inventory"]:raise RuntimeError("NATIVE_ARM_FULL_SHA_MISMATCH")
    incoming.rename(target)
if inventory(target)!=p["inventory"]:raise RuntimeError("PUBLISHED_ARM_FULL_SHA_MISMATCH")
print(json.dumps(dict(verified=True,native_arm_path=str(target),files=len(p["inventory"]),inventory_sha256=hashlib.sha256(json.dumps(p["inventory"],sort_keys=True).encode()).hexdigest())))
''')
    marker=run(remote,'azure',dict(x,prepared=prepared,proof=proof),'''
sys.path.insert(0,"/usr/local/lib/ugrp-storage")
from scripts.azure_shutdown import source_state,run_processes,write_json,archived
root=Path.home()/"ugrp-sim";p=x["prepared"];source=Path(p["source"])
if run_processes(source) or source_state(source)!=p["source_state"] or inventory(source)!=p["inventory"]:raise RuntimeError("SOURCE_CHANGED_BEFORE_PUBLICATION")
marker=dict(verified=True,path=str(root/"arm"/x["destination"]),source=str(source),inventory=p["inventory"],source_state=p["source_state"],bytes=p["bytes"],native_verification=x["proof"],transport=dict(sha256=p["pack_sha256"],bytes=p["pack_bytes"],removed_after_verification=True),preserved_local=True)
Path(p["pack"]).unlink();(root/"arm"/p["transfer"]).unlink()
where=(root/"lifecycle/archives"/(x["name"]+".json") if x["job"] is None else root/"runs"/x["name"]/"per-run-archives"/(x["job"]+".json"))
write_json(where,marker)
if x["job"] is None and not archived(root,source):raise RuntimeError("LIFECYCLE_MARKER_REJECTED")
print(json.dumps(marker))
''')
    return marker
