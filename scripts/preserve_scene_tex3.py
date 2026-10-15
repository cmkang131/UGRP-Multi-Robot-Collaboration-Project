"""Hash all own completed/partial camera artifacts on gcp2, without deletion."""
from collections import defaultdict
import argparse
import json
from pathlib import Path
import platform
from scripts.summarize_scene_tex3 import read, write, sha


def main(target):
    base = Path('/home/ugrp/ugrp-sim/runs')
    target.mkdir(exist_ok=False)
    paths = [base/'scenetex3-r1-cb8ba009', base/'scenetex3-r1b-41bcc86a']
    for name in ('scenetex3-r1', 'scenetex3-r1-resumed', 'scenetex3-r2', 'scenetex3-r3'):
        paths.extend(p for p in (base/name).iterdir() if p.is_dir())
    paths.extend(base/n for n in ('scenetex3-r1-analysis', 'scenetex3-r2-analysis', 'scenetex3-r3-analysis', 'scenetex3-r3-selfmap-signal'))
    records = []
    for i, root in enumerate(paths):
        if (root/'meta.json').exists() and not (root/'POSTRUN_METADATA.json').exists():
            meta = read(root/'meta.json')
            write(root/'POSTRUN_METADATA.json', {'class': 'dev', 'pr': 527, 'branch': 'claude/scene-tex2',
                'sha': meta['source_sha'], 'batch': root.parent.name, 'arm': root.name,
                'note': 'post-run classification; original completion/manifests preserved'})
        files = {str(p.relative_to(root)): sha(p) for p in root.rglob('*') if p.is_file()}
        manifest = write(target/f'files-{i:02d}.json', files)
        old = root/'SHA256SUMS.json'
        bad = []
        if old.exists() or old.with_name(old.name+'.zst').exists():
            bad = [p for p, expected in read(old).items() if files.get(p) != expected]
        summary = read(root/'summary.json') if (root/'summary.json').exists() else {}
        complete = summary.get('status') == 'MEASURED' and summary.get('planned_frames') is not None and summary.get('frames') == summary['planned_frames']
        records.append({'path': str(root), 'files': len(files), 'bytes': sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),
            'manifest': str(manifest), 'manifest_sha256': sha(manifest), 'existing_manifest_mismatches': bad,
            'source_declared_status': summary.get('status', 'PARTIAL_OR_ANALYSIS'),
            'complete_probe_for_gate': complete})
    models = read(base/'scenetex3-r3/native/models.json')+read(base/'scenetex3-r3/wall_no_mip_v1/models.json')
    by_map = defaultdict(list)
    for row in models:
        by_map[row['map']].append(row)
    parity = {m: {'model_variants': len(rows), 'physics_identical': len({r['physics_sha256'] for r in rows}) == 1,
                  'camera_identical': len({r['camera_sha256'] for r in rows}) == 1,
                  'no_shadow': all(not any(r['light_castshadow']) for r in rows)} for m, rows in by_map.items()}
    write(target/'summary.json', {'records': records, 'model_parity': parity,
        'bad_files': sum(len(r['existing_manifest_mismatches']) for r in records), 'script_sha256': sha(Path(__file__)),
        'scope': 'all current saved own raw/derived files; partial runs are NOT complete; persistent gcp2 disk, no deletion'})
    print(json.dumps({'roots': len(records), 'bad_files': sum(len(r['existing_manifest_mismatches']) for r in records), 'parity': parity}))


if __name__ == '__main__':
    if not platform.node().startswith('ugrp-sim-gcp2'):
        raise SystemExit('gcp2 only')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    main(p.parse_args().output)
