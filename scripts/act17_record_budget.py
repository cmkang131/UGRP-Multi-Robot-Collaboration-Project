"""Finite recording+model disk reservation from the completed actual pilot."""
import argparse
import json
import math
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256
from act17_data import read
from act17_compact_records import allocated_bytes
from act17_v7 import ROOT,B


def unique_bytes(paths):
    seen=set();total=0
    for root in paths:
        for path in ([root] if root.is_file() else root.rglob('*')):
            if not path.is_file():continue
            s=path.stat();key=(s.st_dev,s.st_ino)
            if key not in seen:seen.add(key);total+=s.st_blocks*512
    return total


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['pilot','preflight','protocol','out']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--pending-recordings',type=int,help='actual unfinished starts; active starts retain the whole90SIM reservation')
    a=p.parse_args();host=require_gcp2(training=True);source=frozen_source(ROOT);protocol=read(a.protocol);pilot=read(a.pilot/'gate-recount.json')
    if not pilot['complete'] or pilot['n']!=4 or not read(a.preflight/'summary.json')['complete']:raise ValueError('successful closed4 pilot and actual preparation required')
    rows=[]
    for group in a.pilot.glob('group-*'):
        progress=read(group/'controller/progress.json');folders=[p for p in (group/'controller').glob('world-*') if p.is_dir()]
        perworld=[]
        for world in folders:
            i=int(world.name.split('-')[-1]);paths=[world,group/'capture'/world.name,group/'controller'/(world.name+'-states.npz')]
            size=unique_bytes(paths);perworld.append(size);plan=read(world/'plan.json')
            rows.append(dict(seed=plan['seed'],bytes=size,SIM_s=progress['ticks'][i]*.1,raw=str(world)))
        overhead=max(0,allocated_bytes(group)-sum(perworld))/len(folders)
        for row in rows[-len(folders):]:row['bytes']+=overhead;row['bytes_per_SIM']=row['bytes']/row['SIM_s']
    maximum=max(r['bytes_per_SIM'] for r in rows)
    initial_remaining=len(protocol['record_seeds'])-4
    remaining=initial_remaining if a.pending_recordings is None else a.pending_recordings
    if not 0<=remaining<=initial_remaining:raise ValueError('pending count outside preregistered remaining starts')
    recording=math.ceil(maximum*90*remaining)
    preparation_dataset=allocated_bytes(a.preflight/'pilot-dataset');dataset=math.ceil(preparation_dataset/sum(r['SIM_s'] for r in rows)*90*len(protocol['record_seeds']))
    registry=read(ROOT/'configs/model_artifacts.json');baseline=next(r for r in registry['artifacts'] if r['id']=='act16w-native-v1-a-step10000-20261016')
    weight_bytes=next(f['bytes'] for f in baseline['files'] if f['path']=='act/model.safetensors')
    # Three original finals and three retained public verification copies.
    # Upload is streamed, but anonymous fetch temporarily holds one ZIP too.
    models=2*len(protocol['candidates'])*weight_bytes
    archive=max(weight_bytes,baseline['archive']['bytes'])
    free=shutil.disk_usage(B).free;floor=8*1024**3;reserved=recording+dataset+models+archive;shortfall=max(0,floor+reserved-free)
    report=dict(source_sha=source,host=host,status='PASS' if not shortfall else 'BLOCKED_DISK',complete=True,
        basis='completed pilot P100 allocated bytes/SIM x unchanged90SIM cap x declared unfinished starts; exact same-architecture weight bytes; JPEG hardlinks preserve all bytes/paths',
        rows=rows,remaining_recordings=remaining,free_bytes=free,floor_bytes=floor,recording_reservation_bytes=recording,
        dataset_reservation_bytes=dataset,model_reservation_bytes=models,old_model_weight_bytes=weight_bytes,
        archive_disk_reservation_bytes=archive,archive_basis='upload ZIP is streamed; one transient public-download ZIP forecast from observed baseline archive/raw weight max; recheck exact new ZIP receipts before public fetch; staging hardlinks',
        model_copy_basis='one original plus one retained public verification copy per registered candidate',
        total_reservation_bytes=reserved,projected_free_bytes=free-reserved,shortfall_bytes=shortfall,
        minimum_additional_GiB=math.ceil(shortfall/1024**3),future_live_raw_buffer_not_included=True,
        pilot_receipt=dict(path=str(a.pilot/'gate-recount.json'),sha256=sha256(a.pilot/'gate-recount.json')),
        preflight_receipt=dict(path=str(a.preflight/'summary.json'),sha256=sha256(a.preflight/'summary.json')),reproduce=sys.argv)
    with a.out.open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps({k:report[k] for k in ['status','free_bytes','total_reservation_bytes','projected_free_bytes','shortfall_bytes','minimum_additional_GiB']}))


if __name__=='__main__':main()
