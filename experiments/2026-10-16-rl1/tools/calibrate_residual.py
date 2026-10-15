"""GCP2 CPU-only residual scale calibration from existing ACT16a raw.

No physics, inference, training, or GT-to-actor connection. Shadow labels are
calibration evidence only, never executed demonstrations for an RL replay.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(2**20), b''):
            h.update(block)
    return h.hexdigest()


def rows(root, name, sources):
    path = root/name
    if not path.exists():
        path = path.with_suffix(path.suffix+'.zst')
    sources.append({'path': str(path), 'sha256': digest(path), 'bytes': path.stat().st_size})
    if path.suffix == '.zst':
        p = subprocess.run(['zstd', '-dc', str(path)], check=True, capture_output=True)
        content = p.stdout.decode()
    else:
        content = path.read_text()
    return [json.loads(line) for line in content.splitlines() if line.strip()]


def encode(command):
    return (list(command['wheels'])+[v/.15 for v in command['duration_s']]+
            [(command['pwm'][str(s)]-1500)/1000 for s in (1, 3, 4, 5, 6)])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if platform.system() != 'Linux':
        raise RuntimeError('analysis requires Linux gcp2; Mac analysis disabled')
    from urllib.request import Request, urlopen
    def meta(key):
        with urlopen(Request('http://169.254.169.254/computeMetadata/v1/'+key,
                            headers={'Metadata-Flavor': 'Google'}), timeout=3) as r:
            return r.read().decode().split('/')[-1]
    host = {k: meta(v) for k, v in {'project':'project/project-id',
            'instance':'instance/name','machine':'instance/machine-type'}.items()}
    if host != {'project':'ugrp-sim-b-1014','instance':'ugrp-sim-gcp2','machine':'n4-highcpu-64'}:
        raise RuntimeError('unapproved host')
    import numpy as np
    lease = Path('/home/ugrp/ugrp-sim/leases/rl1.json')
    token = {'task':'rl1','pid':os.getpid(),'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
             'expected_end_utc':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=10)).isoformat(),
             'purpose':'ACT16a residual scale calibration; no physics/GPU'}
    with lease.open('x') as f:
        json.dump(token, f)
    try:
        args.output.mkdir(parents=True, exist_ok=False)
        sources = []
        errors = []
        raw_errors = []
        refresh = 0
        for run in json.loads(args.runs.read_text()):
            root = Path(run['raw'])
            commands = rows(root, 'commands.jsonl', sources)
            labels = rows(root, 'shadow-labels.jsonl', sources)
            observations = rows(root, 'student-inputs.jsonl', sources)
            predictions = rows(root, 'chunk-predictions.jsonl', sources)
            if len(commands) != len(labels) or len(labels) != len(observations):
                raise ValueError('causal row count mismatch')
            chunks = {v['sample_id']:v['chunk'] for v in predictions}
            pending = []
            for command, label, observation in zip(commands, labels, observations):
                if observation['sample_id'] in chunks:
                    pending = list(chunks[observation['sample_id']])
                    refresh += 1
                selected = pending.pop(0) if pending else None
                if not label['label_valid'] or label['teacher_command'] is None:
                    continue
                expert = np.asarray(encode(label['teacher_command']))
                errors.append(abs(expert-np.asarray(encode(command['command']))))
                if selected is not None:
                    raw_errors.append(abs(expert-np.asarray(selected[:13])))
        a = np.asarray(raw_errors)
        if not len(a):
            raise ValueError('no raw ACT-to-expert paired samples')
        scales = [float(np.median(v[v>0])) if np.any(v>0) else 0. for v in a.T]
        # Existing contract ranges bound final decoded commands. These are
        # empirical per-channel correction medians, not new success criteria.
        record = {'schema':'ugrp.rl1.residual-calibration.v1','host':host,
                  'valid_decoded_rows':len(errors),'valid_raw_rows':len(raw_errors),
                  'refresh_count':refresh,'basis':'nonzero absolute expert-minus-raw-base median per channel',
                  'channels':['wheel0','wheel1','wheel2','wheel3','pulse0','pulse1','pulse2','pulse3',
                              'pwm1','pwm3','pwm4','pwm5','pwm6','done'],
                  'residual_limits':scales+[0.],
                  'done_basis':'shadow labels have no causal completion target; frozen at zero',
                  'raw_abs_error_percentiles':{str(q):np.quantile(a,q,axis=0).tolist() for q in (.5,.9,.95)},
                  'label_scope':'shadow calibration only, not executed demo replay',
                  'sources':sources,'script_sha256':digest(Path(__file__)),
                  'training_runs':0,'physics_runs':0,'gpu_seconds':0}
        (args.output/'residual-calibration.json').write_text(json.dumps(record,indent=2)+'\n')
        print(json.dumps({k:v for k,v in record.items() if k!='sources'},indent=2))
    finally:
        # Remove only the lease created by this PID. Preserve another owner.
        if lease.exists() and json.loads(lease.read_text()).get('pid') == os.getpid():
            lease.unlink()


if __name__ == '__main__':
    main()
