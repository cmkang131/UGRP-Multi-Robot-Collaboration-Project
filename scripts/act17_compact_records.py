"""Lossless closed-record storage: identical image hardlinks and verified zstd JSON.

Every image path and byte remains available. Original producer manifests retain
their original-byte hashes. No JPEG decode/re-encode, physics or control change.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import sha256,require_gcp2,frozen_source
from act17_open_loop import read


def original_sha256(path):
    path=Path(path)
    if path.exists():return sha256(path)
    archive=Path(str(path)+'.zst');digest=hashlib.sha256()
    process=subprocess.Popen(['zstd','-dc',str(archive)],stdout=subprocess.PIPE)
    while block:=process.stdout.read(1024**2):digest.update(block)
    if process.wait():raise ValueError('archive decompression failed')
    return digest.hexdigest()


def allocated_bytes(root):
    seen=set();total=0
    for path in root.rglob('*'):
        if not path.is_file():continue
        s=path.stat();key=(s.st_dev,s.st_ino)
        if key not in seen:seen.add(key);total+=s.st_blocks*512
    return total


def compact(root,out):
    before=allocated_bytes(root);links=[];compressed=[];known={}
    manifests=[root/name/'summary.json' for name in ['capture','controller']
        if (root/name/'summary.json').exists() or Path(str(root/name/'summary.json')+'.zst').exists()]
    def verify():
        count=0
        for path in manifests:
            for name,digest in read(path)['sha256'].items():
                if original_sha256(path.parent/name)!=digest:raise ValueError('producer manifest changed')
                count+=1
        return count
    verified=verify()
    for path in sorted(root.rglob('*')):
        if path.suffix.lower() not in ['.jpg','.jpeg','.png'] or not path.is_file():continue
        s=path.stat();key=(s.st_size,sha256(path));source=known.get(key)
        if source is None:known[key]=path;continue
        if source.stat().st_ino==s.st_ino and source.stat().st_dev==s.st_dev:continue
        temporary=path.with_name(path.name+'.act17-link-tmp')
        os.link(source,temporary);os.replace(temporary,path)
        if sha256(path)!=key[1]:raise ValueError('identical image dedup changed bytes')
        links.append(dict(path=str(path),source=str(source),bytes=s.st_size,sha256=key[1]))
    for path in sorted(root.rglob('*')):
        if path.suffix not in ['.json','.jsonl'] or not path.is_file() or path.stat().st_size<=65536 or path==out:continue
        if any(parent.name in ['actor','act'] for parent in path.parents):continue
        digest=sha256(path);size=path.stat().st_size;archive=Path(str(path)+'.zst')
        if not archive.exists():subprocess.run(['zstd','-q','-3','-k',str(path)],check=True)
        proc=subprocess.Popen(['zstd','-dc',str(archive)],stdout=subprocess.PIPE);h=hashlib.sha256();n=0
        while block:=proc.stdout.read(1024**2):h.update(block);n+=len(block)
        if proc.wait() or n!=size or h.hexdigest()!=digest:raise ValueError('full decompressed SHA/length differs')
        compressed.append(dict(original=str(path),bytes=size,sha256=digest,archive=str(archive),archive_bytes=archive.stat().st_size,archive_sha256=sha256(archive)))
        # Journal precedes plaintext removal, as AGENTS disk policy requires.
        out.write_text(json.dumps(dict(status='compressing',image_hardlinks=links,compression=compressed),indent=2)+'\n')
        path.unlink()
    if verify()!=verified:raise ValueError('manifest verification count changed')
    report=dict(status='complete',complete=True,source_sha=frozen_source(Path(__file__).resolve().parents[1]),
        root=str(root),producer_manifest_files_verified=verified,allocated_bytes_before=before,allocated_bytes_after=allocated_bytes(root),
        image_paths_bytes_unchanged=True,image_hardlinks=links,compression=compressed,physics_steps=0,rendered_frames=0)
    out.write_text(json.dumps(report,indent=2)+'\n')
    if out.stat().st_size>65536:
        subprocess.run(['zstd','-q','-3','-k',str(out)],check=True)
        original=sha256(out);temporary=out.with_name(out.name+'.roundtrip')
        with temporary.open('xb') as stream:subprocess.run(['zstd','-dc',str(out)+'.zst'],stdout=stream,check=True)
        if sha256(temporary)!=original:raise ValueError('receipt roundtrip failed')
        temporary.unlink();out.unlink()
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();require_gcp2(training=True);frozen_source(Path(__file__).resolve().parents[1])
    report=compact(a.root,a.out)
    print(json.dumps({k:report[k] for k in ['complete','producer_manifest_files_verified','allocated_bytes_before','allocated_bytes_after']}))


if __name__=='__main__':main()
