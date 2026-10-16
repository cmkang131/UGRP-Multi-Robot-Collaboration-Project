"""Generate predeclared native ACT starts and exact references on owned L4 CPU.

Compiling references uses the existing scene's setup settling; no teacher
rollout, dataset camera, optimizer update or final40 observation is performed.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from act16w_runtime import frozen_source, require_gcp2, sha256

ROOT = Path(__file__).resolve().parents[1]
B = Path('/home/ugrp/ugrp-sim')
Q = B/'src/f0db6b1abb842ea65b71c433738210254f300a7c'
T = B/'src/warp1-teacher-snapshot-6f057f7e'
C = B/'runs/simalt3/c-env/bin/python'


def write(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enabled', action='store_true')
    parser.add_argument('--split', choices=('gate', 'record'), required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not args.enabled:
        parser.error('explicit opt-in required')
    host = require_gcp2(training=True)
    source = frozen_source(ROOT)
    args.out.mkdir(parents=True, exist_ok=False)
    protocol = ROOT/'experiments/2026-10-16-act16w/resume3/protocol.json'
    seeds = json.loads(protocol.read_text())[args.split+'_seeds']
    if len(seeds) != 40 or len(set(seeds)) != 40:
        raise ValueError('exact registered40 starts required')
    lease = B/'leases'/('act16w-native-prepare-'+args.split+'.json')
    report = dict(status='running', complete=False, source_sha=source, host=host,
                  contact_profile='warp_native_contact_v1', protocol_sha256=sha256(protocol),
                  split=args.split, teacher_rollouts=0, training_rgb=False, final40_accessed=False)
    with lease.open('x') as stream:
        json.dump(dict(task='act16w-native-prepare', pid=os.getpid(), concurrency=0,
                       start=datetime.now(timezone.utc).isoformat(), expected_end='40 finite setup references'), stream)
    try:
        code = '''import json,sys
from collections import Counter
sys.path.insert(0,sys.argv[1])
from scripts.make_solo_teacher_plan import episode
from harness.grasp_act_seed_splits import check_range
seeds=json.loads(sys.argv[3]);counts=Counter();rows=[]
for i,seed in enumerate(seeds):
 check_range('train',seed,1)
 kind=('cyan','red','green','yellow')[i%4]
 p=episode(counts[kind],kind,seed,'train');counts[kind]+=1
 p.update(episode_id='act16w-native-'+str(seed),batch='act16w-native-v1',pr=539,
          negative_probe=False,gate_eligible=False,training_eligible=False)
 rows.append(p)
open(sys.argv[2],'x').write(json.dumps({'episodes':rows},indent=2)+'\\n')
'''
        subprocess.run([str(C), '-c', code, str(T), str(args.out/'plans.json'), json.dumps(seeds)], check=True)
        def one(index):
            folder = args.out/f'case-{index:02d}'
            command = [str(C), '-u', str(ROOT/'scripts/act16w_native_run.py'), '--enabled', '--mode', 'teacher', '--',
                       '--physics-backend', 'c_pilot_v1', '--teacher-source', str(T),
                       '--plan', str(args.out/'plans.json'), '--episode', str(index), '--scene-v5-v1',
                       '--native-sleep-policy-compat-v1', '--export-compiled-only',
                       '--vm-hourly-usd', '1.096', '--out', str(folder)]
            write(args.out/f'case-{index:02d}-argv.json', command)
            with (args.out/f'case-{index:02d}.log').open('x') as log:
                subprocess.run(command, cwd=Q, check=True, stdout=log, stderr=subprocess.STDOUT,
                    env={**os.environ, 'MUJOCO_GL': 'osmesa', 'LP_NUM_THREADS': '1',
                         'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
            import xml.etree.ElementTree as ET
            xml = folder/'world-000/scene.xml'
            option = ET.fromstring(xml.read_bytes()).find('option').attrib
            if option['noslip_iterations'] != '0' or option['impratio'] != '5':
                raise ValueError('native reference XML contact mismatch')
            return dict(index=index, seed=seeds[index], xml_sha256=sha256(xml),
                        actuator=str(folder/'compiled-312.json'), geometry=str(folder/'compiled-geometry312.npz'),
                        scene_xml=str(xml))
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(one, range(40)))
        write(args.out/'inventory.json', rows)
        write(args.out/'per-world-references.json', {r['xml_sha256']: {k: r[k] for k in ('actuator', 'geometry')} for r in rows})
        sys.path.insert(0, str(Q/'scripts'))
        from warp_act_core import model_key
        groups = {}
        for row in rows:
            key = model_key(Path(row['scene_xml']).read_text())
            groups.setdefault(key, []).append(row['index'])
        write(args.out/'model-groups.json', dict(groups=[dict(model_key=k, indices=v) for k,v in groups.items()]))
        report.update(status='complete', complete=True, N=40, model_groups=len(groups),
                      distribution=dict(Counter(json.loads((args.out/'plans.json').read_text())['episodes'][i]['kind'] for i in range(40))))
    except BaseException as error:
        report.update(status='HOST_ERROR', error=repr(error))
        raise
    finally:
        write(args.out/'summary.json', report)
        if lease.exists() and json.loads(lease.read_text()).get('pid') == os.getpid():
            lease.unlink()


if __name__ == '__main__':
    main()
