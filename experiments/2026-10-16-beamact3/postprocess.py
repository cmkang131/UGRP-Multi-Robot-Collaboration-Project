"""GCP2 raw integrity and finite playback for a completed A/B arm; no physics."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from harness.grasp_act_data import read_json,read_rows,sha256,write_json
from scripts.beamact1_runtime import require_gcp2
from scripts.grasp_act_training_guard import ROOT,source_sha


def existing(p):return p if p.exists() else p.with_name(p.name+'.zst')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--arm',choices=('A','B'),required=True)
    a=p.parse_args();require_gcp2(training=False);source=source_sha()
    base=Path('/home/ugrp/ugrp-sim');root=base/'ops-reviews/beamact3'/a.arm;batch=root/'heldout20-v1'
    summary=read_json(batch/'summary.json')
    if not summary['complete']:raise ValueError('do not mark incomplete student batch complete')
    lease=base/f'leases/beamact3-{a.arm}-postprocess.json'
    with lease.open('x') as f:json.dump(dict(task='beamact3-'+a.arm+'-postprocess',pid=os.getpid(),
        start=datetime.now(timezone.utc).isoformat(),expected_end='finite raw hashes and playback',concurrency=0),f)
    try:
        runs=[]
        for r in summary['runs']:
            run=Path(r['raw']);index=existing(run/'SHA256.json');inventory=read_json(index)
            for rel,expected in inventory.items():
                if sha256(run/rel)!=expected:raise ValueError('raw hash mismatch '+str(run/rel))
            refs=0
            for obs in read_rows(existing(run/'student-inputs.jsonl')):
                for frame in obs['rgb']:
                    assert frame['robot_id']==obs['robot_id'] and frame['path'].startswith('rgb/'+obs['robot_id']+'/')
                    assert inventory[frame['path']]==frame['sha256'];refs+=1
            runs.append(dict(seed=r['seed'],files=len(inventory),bytes=sum((run/f).stat().st_size for f in inventory),
                rgb_refs=refs,inventory_sha256=sha256(index),raw=str(run)))
        assert len(runs)==20
        write_json(root/'integrity.json',dict(verified=True,source_sha=source,arm=a.arm,runs=runs,
            total_files=sum(x['files'] for x in runs),total_bytes=sum(x['bytes'] for x in runs),rgb_refs=sum(x['rgb_refs'] for x in runs),
            scope='all raw inventory files and all own RGB references; raw command/protocol/input/funnel recount is summary.json'))
        # Select deterministically from completed raw outcomes; this selects
        # review examples only, never training data, model, or acceptance rules.
        failed=[r for r in summary['runs'] if not r['physical_success']][:2]
        successful=[r for r in summary['runs'] if r['physical_success']][:1]
        selected=failed+successful
        script=ROOT/'experiments/2026-10-16-beamact2/playback.py'
        for row in selected:
            dest=root/'playback'/f'seed-{row["seed"]}'
            subprocess.run([sys.executable,str(script),'--run',row['raw'],'--output',str(dest)],check=True)
        # At least6 full-resolution own-camera failure frames per arm. These
        # are review evidence, not a substitute for all2Hz/tail10Hz strips.
        frame_rows=[];frames=root/'failure-frames';frames.mkdir()
        import shutil
        for row in failed:
            run=Path(row['raw']);review=read_json(existing(run/'review/manifest.json'))
            for index in sorted(set((0,len(review)//2,len(review)-1))):
                item=review[index]
                for rid in ('r1','r2'):
                    src=run/'review'/item['own'][rid]
                    dest=frames/f'{row["seed"]}-{rid}-{index:04d}.jpg';shutil.copyfile(src,dest)
                    frame_rows.append(dict(seed=row['seed'],robot=rid,t=item['sim_s'],file=dest.name,
                        sha256=sha256(dest),source=str(src)))
        write_json(frames/'frames.json',frame_rows)
        write_json(root/'playback-selection.json',dict(arm=a.arm,student_failure_seeds=[r['seed'] for r in failed],
            student_success_seeds=[r['seed'] for r in successful],failure_frames=len(frame_rows),
            teacher_reference_if_no_student_success='existing beampair8 teacher8328003 playback; separate cohort, never numerator',
            full_hz=2,tail_hz=10,video_speed=3,viewed=False,
            scope='generated and ffprobe verified; direct frame-strip inspection remains required'))
        print(json.dumps(dict(arm=a.arm,integrity_verified=True,student_n=summary['n'],selected=[r['seed'] for r in selected],failure_frames=len(frame_rows))),flush=True)
    finally:lease.unlink()


if __name__=='__main__':main()
