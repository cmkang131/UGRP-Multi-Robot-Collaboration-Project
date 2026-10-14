"""Dataset admission and path/hash checks, independent of optional torch."""
from __future__ import annotations
import hashlib,json,subprocess
from pathlib import Path
from harness.grasp_act_contract import validate_observation,training_windows


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path,*,lines=False):
    path=Path(path)
    if not path.exists():path=Path(str(path)+'.zst')
    raw=path.read_bytes()
    if path.suffix=='.zst':raw=subprocess.check_output(['zstd','-qdc'],input=raw)
    return [json.loads(x) for x in raw.splitlines() if x.strip()] if lines else json.loads(raw)


def owned_image(root,ref):
    root=Path(root).resolve();path=root/ref['path']
    if not path.resolve().is_relative_to(root) or path.is_symlink():raise ValueError('RGB path escaped dataset')
    if sha(path)!=ref['sha256']:raise ValueError('RGB hash mismatch')
    return path


def read_episode(root):
    root=Path(root);meta=read(root/'episode.json')
    if meta['teacher_admitted'] is not True:raise ValueError('successful teacher gate required')
    sequences={}
    for rid in meta['robots']:
        obs=read(root/f'student-{rid}.jsonl',lines=True);labels=read(root/f'labels-{rid}.jsonl',lines=True)
        if not obs or obs[0]['robot_id']!=rid:raise ValueError('wrong actor file')
        for x in obs:
            validate_observation(x)
            for ref in x['rgb']:owned_image(root,ref)
        windows=training_windows(obs,labels)
        if not any(x['done'] for x in labels):raise ValueError('successful sequence lacks termination label')
        sequences[rid]=(obs,labels,windows)
    return meta,sequences


def validate_splits(entries):
    """Both actors/recoveries of one start stay together. Map holdout is disjoint."""
    owners={};hashes={};maps={};out={}
    for split,rows in entries.items():
        out[split]=[];maps[split]=set()
        for root in rows:
            meta,seq=read_episode(root);start=meta['start_state_id'];digest=meta['initial_state_sha256']
            if start in owners and owners[start]!=split:raise ValueError('start-state split leakage')
            if digest in hashes and hashes[digest]!=split:raise ValueError('duplicate initial state across splits')
            owners[start]=split;hashes[digest]=split;maps[split].add(meta['map_id']);out[split].append((root,meta,seq))
    if maps.get('heldout_map',set()) & set().union(*(v for k,v in maps.items() if k!='heldout_map')):
        raise ValueError('held-out map occurs in other splits')
    return out
