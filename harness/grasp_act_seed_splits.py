"""Registered seed ranges per split and metadata-only split checks.

Gate seeds (71000-71039, 72000-72039, 73000-73039, release 74000-74039) are
never training data. Train/development/held-out ranges do not overlap. The
held-out checks read only each episode's episode.json (map id, start id),
never held-out samples, so model selection stays blind to final holdouts.
"""
from __future__ import annotations
import json,re
from pathlib import Path

REGISTRY=Path(__file__).resolve().parents[1]/'configs'/'grasp_act_seed_splits.json'
TRAINING_SPLITS=('train','development','heldout_start','heldout_map')


def registry(path=REGISTRY):
    data=json.loads(Path(path).read_text());spans=[]
    for split,ranges in data['ranges'].items():
        for lo,hi in ranges:
            if not (isinstance(lo,int) and isinstance(hi,int) and lo<=hi):raise ValueError('bad seed range '+split)
            spans.append((lo,hi,split))
    spans.sort()
    for (a0,a1,sa),(b0,b1,sb) in zip(spans,spans[1:]):
        if b0<=a1:raise ValueError(f'seed ranges overlap: {sa} and {sb}')
    return data


def split_of(seed,data=None):
    data=data or registry()
    for split,ranges in data['ranges'].items():
        if any(lo<=seed<=hi for lo,hi in ranges):return split
    return None


def check_range(split,start,count,data=None):
    data=data or registry()
    if split not in data['ranges']:raise ValueError('unregistered split '+split)
    for seed in range(start,start+count):
        if split_of(seed,data)!=split:raise ValueError(f'seed {seed} is not in registered {split} range')


def seed_of(meta):
    if isinstance(meta.get('seed'),int):return meta['seed']
    m=re.search(r'(\d+)$',str(meta.get('episode_id','')))
    if not m:raise ValueError('episode seed unavailable')
    return int(m.group(1))


def check_dataset_splits(data_json,base):
    """Metadata-only checks over every declared split, including holdouts.

    Requires a non-empty 'heldout_map' declaration so the map holdout check
    actually runs. Returns a summary for the training report."""
    reg=registry();base=Path(base);seen={};maps={};summary={}
    if not data_json.get('heldout_map'):raise ValueError('dataset must declare a non-empty heldout_map split')
    for split in TRAINING_SPLITS:
        rows=data_json.get(split,[]);maps[split]=set();summary[split]={'episodes':len(rows)}
        for rel in rows:
            meta=json.loads((base/rel/'episode.json').read_text());seed=seed_of(meta)
            owner=split_of(seed,reg)
            if owner!=split:raise ValueError(f'{rel}: seed {seed} belongs to {owner}, declared {split}')
            if seed in seen:raise ValueError(f'seed {seed} appears twice ({seen[seed]}, {split})')
            seen[seed]=split;maps[split].add(meta['map_id'])
        summary[split]['maps']=sorted(maps[split])
    fitted=maps['train']|maps['development']
    if maps['heldout_map']&fitted:raise ValueError('held-out map occurs in train/development')
    if set(reg['heldout_maps'])&fitted:raise ValueError('registered held-out map occurs in train/development')
    if not set(reg['heldout_maps'])&maps['heldout_map']:raise ValueError('heldout_map split lacks a registered held-out map')
    summary['heldout_map_check']='passed (metadata only; samples not opened)'
    return summary
