"""Finite gcp2-only postprocessor: wait for closed student result, audit, replay.

Never changes policy/physics, retries experiments, or launches a GUI.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('run','actor-audit','playback-tool','playback-out','python','out'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--deadline-utc',required=True)
    a=p.parse_args()
    if sys.platform!='linux':p.error('gcp2 only; no Mac rendering')
    deadline=datetime.datetime.fromisoformat(a.deadline_utc.replace('Z','+00:00')).timestamp()
    report=dict(status='running',run=str(a.run),scope='one DEV ACT15 case; not held-out cohort or teacher gate',
                postprocessor_sha256=digest(__file__))
    lease=Path('/home/ugrp/ugrp-sim/leases/warp3-student-full.json')
    try:
        while time.time()<deadline:
            try:
                result=json.loads((a.run/'summary.json').read_text())
                if result.get('status')!='running':break
            except (FileNotFoundError,json.JSONDecodeError):pass
            time.sleep(5)
        else:raise TimeoutError('finite postprocessing resource deadline; result not closed')
        if lease.exists():
            d=json.loads(lease.read_text())
            if d.get('task')!='warp3-student-full':raise RuntimeError('own lease lost')
            d.update(pid=os.getpid(),stage='closed student raw audit + evaluation-only ffmpeg replay',concurrency=0)
            lease.write_text(json.dumps(d,indent=2)+'\n')
        completed=result.get('status')=='complete' and 'student_scores' in result
        scores=result.get('student_scores',[])
        world_results=[json.loads(x.read_text()) for x in (a.run/'owner').glob('world-*/result.json')]
        report.update(api_completed=completed,raw_status=result.get('status'),
            physical_n=sum(x['physical_success'] for x in scores),physical_N=len(scores) if completed else 0,
            cap_end=sum(x.get('cap_end',False) for x in world_results),
            HOST_ERROR=int(result.get('status')=='HOST_ERROR'),student_scores=scores,
            actual_policy_steps=len(result.get('actions',[])),summary_sha256=digest(a.run/'summary.json'))
        manifest={str(x.relative_to(a.run)):digest(x) for x in a.run.rglob('*') if x.is_file()}
        raw_manifest=a.out.with_name(a.out.stem+'-raw-manifest.json')
        raw_manifest.write_text(json.dumps(manifest,indent=2)+'\n')
        bad=[name for name,sha in manifest.items() if digest(a.run/name)!=sha]
        if bad:raise RuntimeError('closed raw changed during audit: '+repr(bad))
        report.update(raw_manifest=str(raw_manifest),raw_manifest_sha256=digest(raw_manifest),
                      raw_hash_files=len(manifest),raw_hash_mismatch=0)
        original=json.loads(a.actor_audit.read_text());actor=Path(original['actor_source'])
        if any(digest(actor/name)!=sha for name,sha in original['critical_modules'].items()):
            raise RuntimeError('actor source changed during evaluation')
        if any(digest(Path(original['checkpoint'])/name)!=info['sha256']
               for name,info in original['checkpoint_files'].items()):
            raise RuntimeError('ACT15 artifact changed during evaluation')
        report['actor_source_and_artifacts_unchanged']=True
        from PIL import Image
        review=sorted((a.run/'owner/world-000/review-own').glob('*.jpg'))
        ring=sorted((a.run/'owner/world-000/last10s').glob('*.jpg'))
        dimensions=set()
        for path in review+ring:
            with Image.open(path) as im:dimensions.add(im.size)
        if dimensions!={(640,480)}:raise RuntimeError('native camera dimensions changed')
        report.update(review_2hz_frames=len(review),terminal_10hz_frames=len(ring),native_dimensions=[640,480])
        cmd=[str(a.python),str(a.playback_tool),'--run',str(a.run/'owner'),'--world','0','--out',str(a.playback_out)]
        subprocess.run(cmd,check=True,timeout=max(1,deadline-time.time()))
        meta=json.loads((a.playback_out/'playback-meta.json').read_text())
        report.update(status='complete',playback=str(a.playback_out),playback_meta_sha256=digest(a.playback_out/'playback-meta.json'),
                      playback_video_bytes=meta['video_bytes'],direct_visual_review='pending on Mac file reader; no GUI')
    except BaseException as error:
        report.update(status='HOST_ERROR',postprocess_error=repr(error),traceback=traceback.format_exc())
        raise
    finally:
        a.out.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
