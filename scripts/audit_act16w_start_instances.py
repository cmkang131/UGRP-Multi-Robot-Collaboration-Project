"""Recreate canonical starts only; verify native JPEGs before counting instances.

No actor command or policy call. Qualified Owner warm-up is discarded before
the canonical start. Reuse the original per-batch grouping and exact plans.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from act16w_runtime import require_gcp2, frozen_source, sha256
from act16w_eval_rpc import EvaluationClient

B = Path('/home/ugrp/ugrp-sim')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if not args.enabled:
        p.error('explicit evaluation-only start audit required')
    host = require_gcp2(training=True)
    source = frozen_source(Path(__file__).resolve().parents[1])
    references = B/'runs/act16w-resume2-record-references'
    plans = json.loads((references/'plans.json').read_text())['episodes']
    inventory = json.loads((references/'inventory.json').read_text())
    units = [(f'pilot-{seed}', [next(i for i, row in enumerate(plans) if row['seed']==seed)],
              B/f'runs/act16w-resume2-pilot-{seed}') for seed in (86821, 86822)]
    for group in range(4):
        raw = B/f'runs/act16w-resume2-data-r2/group-{group:02d}'
        units.append((f'group-{group:02d}', json.loads((raw/'launch.json').read_text())['world_indices'], raw))
    args.out.mkdir(parents=True, exist_ok=False)
    now = datetime.now(timezone.utc)
    lease = B/'leases/act16w-start-instance-audit.json'
    with lease.open('x') as stream:
        json.dump(dict(task='act16w-start-instance-audit',pid=os.getpid(),start=now.isoformat(),
            expected_end=(now+timedelta(minutes=10)).isoformat(),concurrency=0),stream)
    started, rows, receipts, client = time.monotonic(), [], [], None
    report = dict(status='running',source_sha=source,host=host,actor_commands=0,
                  policy_inference=False,task_success_claim=False,rows=rows)
    try:
        for name, indices, raw in units:
            capacity = json.loads((B/'runs/act16w-capacity-receipt.json').read_text())
            if datetime.fromisoformat(capacity['valid_until_utc']) < datetime.now(timezone.utc):
                raise ValueError('capacity receipt expired')
            foreign = int(capacity['foreign_cpu_worlds'])
            foreign += sum(int(json.loads(path.read_text()).get('concurrency',0))
                           for path in (B/'leases').glob('*.json') if path!=lease)
            if foreign+len(indices)>40:
                raise ValueError('global40-world budget')
            lease.write_text(json.dumps(dict(task='act16w-start-instance-audit',pid=os.getpid(),
                start=now.isoformat(),expected_end=(now+timedelta(minutes=10)).isoformat(),concurrency=len(indices))))
            first = inventory[indices[0]]
            client = EvaluationClient(python=B/'runs/simalt3/warp-env/bin/python',
                qualified_source=B/'src/f0db6b1abb842ea65b71c433738210254f300a7c',
                teacher_source=B/'src/warp1-teacher-snapshot-6f057f7e',
                qualification=B/'runs/warp3/teacher-gate-qualification-r1.json',
                references=references/'per-world-references.json',compiled_reference=first['actuator'],
                compiled_geometry=first['geometry'],out=args.out/name,nworld=len(indices),enabled=True)
            client.reset([plans[i] for i in indices])
            visibility = json.loads((args.out/name/'owner/initial-same-kind-visibility.json').read_text())
            for world, index in enumerate(indices):
                original = raw/'capture'/f'world-{world:03d}/capture/000000.jpg'
                observation, jpegs = client.read_actor(world)
                recreated_hash = hashlib.sha256(jpegs[-1]).hexdigest()
                original_hash = sha256(original)
                if recreated_hash != original_hash:
                    raise ValueError(f'canonical native start JPEG mismatch seed{plans[index]["seed"]}')
                row = dict(visibility['rows'][world], original_start_RGB=str(original),
                           original_start_RGB_sha256=original_hash, exact_native_start_match=True)
                rows.append(row)
            client.close('start_frame_audit_only'); client=None
            path=args.out/name/'owner/initial-same-kind-visibility.json'
            receipts.append(dict(path=str(path),sha256=sha256(path)))
            (args.out/'progress.json').write_text(json.dumps(dict(verified_starts=len(rows),actor_commands=0))+'\n')
        if len(rows)!=40 or len({row['seed'] for row in rows})!=40:
            raise ValueError('exact unique recording40 starts required')
        report.update(status='complete',N=40,pixel_2plus_n=sum(row['pixel_visible_count']>=2 for row in rows),
            qualified_probe_2plus_n=sum(row['qualified_visible_count']>=2 for row in rows),
            receipts=receipts,scope='recording40 starts; exact original native JPEG hashes matched; native segmentation/fisheye pixels, evaluation only; no student outcome')
    except BaseException as error:
        report.update(status='HOST_ERROR',error=repr(error),N_verified=len(rows))
        raise
    finally:
        try:
            if client is not None:
                try: client.close('start_frame_audit_only')
                except BaseException as error: report['close_error']=repr(error)
            report['wall_s']=time.monotonic()-started
            (args.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        finally:
            if lease.exists() and json.loads(lease.read_text()).get('pid')==os.getpid():
                lease.unlink()
    print(json.dumps({key:value for key,value in report.items() if key not in ('rows','receipts')}))


if __name__=='__main__':
    main()
