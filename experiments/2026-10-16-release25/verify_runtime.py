"""gcp2-only metadata audit. No physics, rendering, credentials or controller input."""
from pathlib import Path
import collections
import hashlib
import importlib.metadata
import json
import platform
import subprocess

ROOT=Path('/home/ugrp/ugrp-sim')
OPS=ROOT/'ops-reviews/release25'


def read(path):
    return json.loads(path.read_bytes() if path.exists() else subprocess.check_output(['zstd','-qdc',str(path)+'.zst']))


def version(name):
    try:return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:return None


rows=[];sources=[]
for config in ('short-config.json','short-r2-config.json','gate-config.json'):
    cfg=read(OPS/config);sha=cfg['source_sha'];src=ROOT/'src'/sha
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=src,text=True).strip()
    status=subprocess.check_output(['git','status','--porcelain'],cwd=src,text=True)
    alternate=(src/'.git/objects/info/alternates').read_text().strip()
    assert head==sha and not status
    assert alternate==str(ROOT/'git-shared.git/objects')
    sources.append(dict(config=config,source_sha=sha,head=head,clean=True,alternate=alternate))
    for run in cfg['runs']:
        raw=ROOT/'runs'/run['name']/'raw';p=raw/'result.json'
        if not p.exists() and not Path(str(p)+'.zst').exists():
            rows.append(dict(config=config,run=run['name'],expected_sha=sha,
                actual_sha=None,source_match=None,result_exists=False,
                status='HOST_ERROR' if raw.exists() else 'not_started',raw=str(raw)))
            continue
        d=read(p);actual=p if p.exists() else Path(str(p)+'.zst')
        rows.append(dict(config=config,run=run['name'],expected_sha=sha,actual_sha=d.get('source_sha'),
            source_match=d.get('source_sha')==sha,status=d.get('status'),
            result_stored_sha256=hashlib.sha256(actual.read_bytes()).hexdigest(),
            mode=d.get('release_sweep_wall_aware'),weld=d.get('weld'),
            recording_mode=d.get('recording_mode'),student_execution=d.get('student_execution'),
            input_audit={k:d.get('input_audit',{}).get(k) for k in
                         ('invisible_measurements','held_world_reads','control_top_camera_reads')},
            raw=str(raw)))
value=dict(host=platform.node(),python=platform.python_version(),
    packages={p:version(p) for p in ('mujoco','numpy','opencv-python','opencv-python-headless','Pillow')},
    cpu=next(l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),
    sources=sources,runs=rows,all_sources_pinned=bool(rows) and all(x['source_match'] is True for x in rows),
    categories=dict(collections.Counter(x['status'] for x in rows)),
    scope='Current gcp2 environment and stored metadata. Short rounds and gate are separate; no success rates pooled.',
    reproduce=str(Path(__file__).resolve()))
(OPS/'runtime-verification.json').write_text(json.dumps(value,indent=2)+'\n')
print(json.dumps({k:v for k,v in value.items() if k not in ('sources','runs')}))
