"""gcp2 CPU preview of an unfinished prefix; never a success/failure verdict."""
import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path('/home/ugrp/ugrp-sim')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--snapshot', type=Path, required=True)
    p.add_argument('--receive', action='store_true')
    a = p.parse_args()
    assert a.snapshot.is_absolute() and a.snapshot.parent == ROOT / 'runs'
    lease = ROOT / 'leases/warp8-prefix-playback.json'
    assert not lease.exists()
    now = dt.datetime.now(dt.timezone.utc)
    lease.write_text(json.dumps(dict(task='warp8-prefix-playback', pid=os.getpid(), started_at=now.isoformat(),
        expected_end=(now+dt.timedelta(minutes=15)).isoformat(), purpose='CPU-only kinematic preview; no physics/model')))
    try:
        if a.receive:
            a.snapshot.mkdir(exist_ok=False)
            with tarfile.open(fileobj=sys.stdin.buffer, mode='r|gz') as archive:
                for member in archive:
                    assert member.name.startswith('beam40-r1/')
                    archive.extract(member, a.snapshot, filter='data')
            return
        import numpy as np
        import mujoco
        original = a.snapshot / 'beam40-r1'
        source_summary = json.loads((original/'summary.json').read_text())
        for world_id in (0, 1):
            world = original / f'world-{world_id:03d}'
            rows = []
            for line in (world/'raw/eval-only.jsonl').read_text().splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # Preserve original bytes; only complete rows enter this preview.
            index = {round(r['t']*10):r for r in rows}
            origin = rows[0]['t']
            # Drop RGB times whose exact saved evaluator row is not yet flushed.
            # Source snapshot stays immutable; derived inputs use symlinks.
            derived = a.snapshot / f'derived-world-{world_id:03d}'
            folder = derived / 'world-000'
            (folder/'review-2hz').mkdir(parents=True, exist_ok=False)
            (folder/'raw').symlink_to(world/'raw', target_is_directory=True)
            for rid in ('r1','r2'):
                out = folder/'review-2hz'/rid
                out.mkdir()
                for image in sorted((world/'review-2hz'/rid).glob('*.jpg')):
                    if round((origin+int(image.stem)/10)*10) in index:
                        (out/image.name).symlink_to(image)
            model = mujoco.MjModel.from_xml_string((world/'raw/scene.xml').read_text())
            np.savez_compressed(derived/'world-000-states.npz', ticks=list(index),
                qpos=[r['joints'] for r in index.values()], qvel=np.zeros((len(index),model.nv)))
            # qvel is unused by mj_kinematics and rendering. No C step is called.
            summary = dict(source_summary, native_initialization_only_sim_s=[origin])
            (derived/'summary.json').write_text(json.dumps(summary))
            (folder/'tail-10hz.json').write_text('[]')
            asset = ROOT / 'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247'
            playback = ROOT/'ops-reviews/warp8/playback'/a.snapshot.name/f'world-{world_id:03d}'
            subprocess.run([str(ROOT/'ugrp/.venv-sim/bin/python'),
                str(ROOT/'ops-reviews/warp6/make_playback.py'), '--run',str(derived),
                '--out',str(playback),'--asset-root',str(asset)], check=True,
                cwd=asset, env={**os.environ,'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
            meta = playback/'playback-meta.json'
            info = json.loads(meta.read_text())
            info.update(scope='unfinished prefix sanity preview, not failure/success or root-cause evidence; no physics step',
                original_world=world_id, source_snapshot=str(original), simulation_host='gcp3', analysis_host='gcp2_CPU',
                reconstruction='exact evaluator joints/qpos at matching times; qvel=0 unused by renderer',
                terminal_10hz_scope='not included in this nonterminal preview; native recording rings remain on gcp3')
            meta.write_text(json.dumps(info,indent=2)+'\n')
            print(str(playback),flush=True)
    finally:
        assert json.loads(lease.read_text())['pid'] == os.getpid()
        lease.unlink()


if __name__ == '__main__':
    main()
