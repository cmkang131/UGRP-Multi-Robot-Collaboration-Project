"""Build the small BSD upstream header bridge; no ROS, IMU or physics dependency."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def build(output):
    from harness.rovio_feature_statistics import VENDOR
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    provenance = json.loads((VENDOR/'provenance.json').read_text())
    for name, expected in provenance['unmodified'].items():
        if hashlib.sha256((VENDOR/name).read_bytes()).hexdigest() != expected:
            raise ValueError('UPSTREAM_ROVIO_SOURCE_CHANGED: '+name)
    command = ['c++', '-std=c++11', '-O2', '-shared', '-fPIC',
               str(VENDOR/'statistics_c_api.cpp'), '-o', str(output)]
    subprocess.run(command, check=True)
    return dict(command=command, upstream=provenance,
                binary_sha256=hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output)), flush=True)
