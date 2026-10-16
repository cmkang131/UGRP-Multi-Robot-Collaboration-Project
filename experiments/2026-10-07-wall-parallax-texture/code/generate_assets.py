"""Build the preregistered tape table/raster without rendering or physics."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from sim.wall_texture import generate_assets, walls_from_xml, sha

if __name__ == '__main__':
    source = Path('/Users/changmin/projects/ugrp/outputs/wall-parallax-strafe-v1/strafe-north-host-retry1/scene.xml')
    destination = Path(__file__).resolve().parents[1] / 'assets'
    generate_assets(walls_from_xml(source.read_text()), destination)
    provenance = dict(source_scene=str(source), source_scene_sha256=sha(source),
                      purpose='environment design only; no input to the detector or odometry',
                      physical_photo_verified=False, user_decision_date='2026-10-07')
    (destination / 'source.json').write_text(json.dumps(provenance, indent=2) + '\n')
