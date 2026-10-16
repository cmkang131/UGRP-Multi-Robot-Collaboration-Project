"""Export immutable owner bytes; no checkout edits or dependency rewriting."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

MAPBUILD = 'c7477b1f64910f498b52e1697488c28b2c4569e1'
VISION = subprocess.check_output(['git', 'rev-parse', '5974a181'], text=True).strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mapbuild', default=MAPBUILD, help='Pinned owner commit; exported bytes are unchanged')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    a = p.parse_args()
    mapbuild = subprocess.check_output(['git', 'rev-parse', a.mapbuild], text=True).strip()
    files = {}
    extras = ('experiments/2026-10-05-ego-wall-map-probe/code/',
              'experiments/2026-09-26-markerless-probe/',
              'experiments/2026-09-26-vision-loc/',
              'experiments/2026-09-26-zone-m1-owncam/',
              'experiments/2026-10-16-reloc16/colour-calibration.json',
              'sim/assets/scene_contrast_v5/manifest.json')
    for source in (VISION, mapbuild):
        names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', source], text=True).splitlines()
        for name in names:
            selected = ((name.startswith(('harness/', 'sim/', 'scripts/')) and name.endswith('.py')) or
                        name.startswith('harness/data/') or
                        (name.startswith(extras) and name.endswith(('.py', '.json'))))
            if selected:
                data = subprocess.check_output(['git', 'show', source+':'+name])
                files[name] = (data, source)
    with tarfile.open(a.output, 'x:gz') as archive:
        for name, (data, _) in sorted(files.items()):
            info = tarfile.TarInfo(name); info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    manifest = dict(schema='ugrp.warp8e.selfmap_owner_bytes.v1', mapbuild_sha=mapbuild,
        vision_supplement_sha=VISION, unchanged_owner_modules=True,
        supplement_reason='mapbuild6 uses the pinned renderer597 vision supplement; modules absent from mapbuild only',
        files={n: dict(source=s, sha256=hashlib.sha256(d).hexdigest(), bytes=len(d)) for n,(d,s) in sorted(files.items())},
        archive_sha256=hashlib.sha256(a.output.read_bytes()).hexdigest())
    a.manifest.write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(dict(files=len(files), archive_bytes=a.output.stat().st_size,
                         archive_sha256=manifest['archive_sha256'])))


if __name__ == '__main__': main()
