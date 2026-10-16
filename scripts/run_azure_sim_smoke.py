"""Finite S3 scene/physics/three-camera installation check, no controller or model."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from harness import zone_s3_contract as contract
from scripts.run_final_environment_checks import check_source, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-source-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sha = check_source(args.expected_source_sha)
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    bundle = contract.bundle(sha, seed=601)
    write(out / 'bundle.json', bundle)
    summary = {'status': 'HOST_ERROR', 'source_sha': sha, 'model_calls': 0,
        'physical_success': None, 'scope': 'S3 scene reset, hold, 0.5 SIM seconds and three own RGB cameras',
        'gl': os.environ.get('MUJOCO_GL'), 'loadavg': list(os.getloadavg())}
    backend = None
    started = time.monotonic()
    try:
        from sim.zone_s3_host import PhysicsBackend
        backend = PhysicsBackend(bundle, out, seed=601)
        reset = backend.reset(bundle['reset_cap_s'])
        initial = backend.now
        for rid in ('r1', 'r2', 'r3'):
            backend.issue(rid, {'kind': 'hold'})
        list(backend.capture().values())
        backend.eval_sample()
        backend.advance_to(initial + .5)
        list(backend.capture().values())
        backend.eval_sample()
        images = sorted(out.glob('robots/*/rgb/*.jpg'))
        if len(images) != 6 or abs(backend.now - initial - .5) > 1e-6:
            raise RuntimeError('Missing RGB frames or incorrect physics progression')
        summary.update(status='PASS', reset_sim_s=reset, step_sim_s=backend.now-initial,
            camera_frames=len(images), image_sha256={str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in images})
    except Exception as exc:
        summary['error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        if backend is not None:
            backend.close()
        summary['wall_s'] = time.monotonic() - started
        write(out / 'summary.json', summary)
        print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
