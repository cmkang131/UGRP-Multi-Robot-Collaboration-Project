"""Transfer released evaluation files through RAM after the estimation seal.

No RGB, commands, qpos or ground-truth payload is stored on the Mac. Only the
release manifest and checksum receipt are local. The original manifest stays
immutable and its SHA must be linked by this release.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


def transfer(manifest, expected, seal, destination, receipt):
    payload=Path(manifest).read_bytes()
    if hashlib.sha256(payload).hexdigest()!=expected:raise ValueError('release_manifest_sha_mismatch')
    data=json.loads(payload)
    if data['comparison_prediction_scale_seal_sha256']!=hashlib.sha256(Path(seal).read_bytes()).hexdigest():
        raise ValueError('comparison_estimation_scale_seal_mismatch')
    if data['parent_manifest_sha256']!='de9addf5a7c268db99b0b8c7198e435a5adf90713bda7a718b4e6a7aec34e7d5':
        raise ValueError('wrong_recording_parent')
    selected=[f for f in data['files'] if f['path'] in (data['camera_evaluation_only'],data['estimated_cameras'])
        or f['path'].endswith('/analysis-r2/trajectory.json') or f['path'].endswith('/analysis-r2/prediction-seal.json')]
    if len(selected)!=4:raise ValueError('four_released_evaluation_files_required')
    for f in selected:
        p=Path(f['path'])
        if '..' in p.parts or not p.is_relative_to('/home/ugrp/ugrp-sim/runs/mapbuild5'):
            raise ValueError('unexpected_evaluation_path')
    dest=Path(destination)
    if not dest.is_absolute() or '..' in dest.parts:raise ValueError('invalid_destination')
    source=subprocess.Popen(['ssh','gcp5','tar -cf - -C / --null -T -'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    sink=subprocess.Popen(['ssh','gcp4','mkdir '+shlex.quote(str(dest))+' && tar -xf - -C '+shlex.quote(str(dest))],stdin=source.stdout)
    source.stdout.close()
    source.stdin.write(b'\0'.join(f['path'].lstrip('/').encode() for f in selected)+b'\0');source.stdin.close()
    rc=source.wait();sink.wait()
    if rc or sink.returncode:raise RuntimeError('evaluation_pipe_transfer_failed')
    code='import json,sys,hashlib,pathlib; d=json.load(sys.stdin); root=pathlib.Path('+repr(str(dest))+'); bad=[f["path"] for f in d if hashlib.sha256((root/f["path"].lstrip("/")).read_bytes()).hexdigest()!=f["sha256"]]; print(json.dumps(dict(files=len(d),mismatches=bad))); assert not bad'
    verification=json.loads(subprocess.check_output(['ssh','gcp4','python3 -c '+shlex.quote(code)],input=json.dumps(selected).encode()))
    result=dict(release_manifest_sha256=expected,transferred_utc=datetime.now(timezone.utc).isoformat(),
        comparison_seal_sha256=data['comparison_prediction_scale_seal_sha256'],files=selected,
        destination=str(dest),verification=verification,mac_frame_files=0,mac_truth_payload_files=0,
        via='gcp5 -> Mac RAM pipe -> gcp4; post-estimation evaluation only')
    with Path(receipt).open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('manifest','manifest-sha256','seal','destination','receipt'):p.add_argument('--'+name,required=True)
    a=p.parse_args();print(json.dumps(transfer(a.manifest,a.manifest_sha256,a.seal,a.destination,a.receipt),indent=2))
