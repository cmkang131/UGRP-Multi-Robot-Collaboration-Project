"""gcp2 finite scene-contrast comparison; reuse frozen 88-pose/3-encoding audit."""
import argparse
import os
from pathlib import Path
import platform
from scripts import probe_scene_tex3 as probe
from sim.scene_contrast_v4 import PROFILES


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source-sha', required=True)
    p.add_argument('--materials', nargs='+', choices=list(PROFILES)+list(probe.MATERIALS), required=True)
    p.add_argument('--qualities', nargs='+', choices=probe.quality.PROFILES, default=['native'])
    p.add_argument('--execute', action='store_true')
    a = p.parse_args()
    if not a.execute or platform.system() != 'Linux' or not platform.node().startswith('ugrp-sim-gcp2'):
        p.error('explicit gcp2 execution required; Mac rendering forbidden')
    probe.old.validate_source(a.source_sha)
    probe.old.setup_proof(Path('/home/ugrp/ugrp-sim/scenetex2-setup-proof.md'))
    os.chdir(probe.ROOT)
    a.poses = a.resume_from = a.resume_materials = None
    probe.run(a)


if __name__ == '__main__':
    main()
