"""Link complete independent R1 arms without copying original frame data."""
import argparse
from pathlib import Path
from scripts.summarize_scene_tex3 import read, write, sha


def combine(inputs, output):
    output.mkdir(parents=True, exist_ok=False)
    rows, sources, models = [], [], []
    for root in inputs:
        summary = read(root/'summary.json')
        if summary['status'] != 'MEASURED' or summary['frames'] != summary['planned_frames']:
            raise ValueError('incomplete arm: '+str(root))
        manifest = read(root/'SHA256SUMS.json')
        for name, expected in manifest.items():
            if sha(root/name) != expected:
                raise ValueError('source hash mismatch: '+str(root/name))
        rows.extend(read(root/'index.json'))
        models.extend(read(root/'models.json'))
        sources.append({'path': str(root), 'summary_sha256': sha(root/'summary.json'), 'verified_files': len(manifest)})
        for source in root.iterdir():
            if '--' in source.name:
                target = output/source.name
                if target.exists():
                    raise ValueError('overlapping arms: '+source.name)
                target.symlink_to(source.resolve())
    keys = [(r['case'], r['material'], r['quality']) for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError('duplicate cases')
    write(output/'index.json', rows)
    write(output/'models.json', models)
    write(output/'summary.json', {**summary, 'frames': len(rows), 'sources': sources,
                                 'reproduction_command': ['combine_scene_tex3', *map(str, inputs)]})
    write(output/'SHA256SUMS.json', {p.name: sha(p) for p in output.iterdir() if p.is_file()})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs', nargs='+', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    combine(a.inputs, a.output)
