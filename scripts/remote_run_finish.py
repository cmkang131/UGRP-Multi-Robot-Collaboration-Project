"""Preserve this command's standard workflow records beside its raw output."""
import argparse
from pathlib import Path
import re
import shutil


def collect(source: Path, run: Path):
    allowed = (source / 'outputs/simulation-runs').resolve()
    records = set(re.findall(r'^Simulation record: (.+/manifest\.json)$',
                             (run / 'log.txt').read_text(), re.MULTILINE))
    copied = []
    for name in sorted(records):
        manifest = Path(name).resolve()
        if not manifest.is_relative_to(allowed) or manifest.name != 'manifest.json':
            raise ValueError('Workflow record outside the committed source record directory')
        target = run / 'management' / manifest.parent.name
        if target.exists():
            raise ValueError('Refuse to overwrite existing management evidence')
        shutil.copytree(manifest.parent, target, symlinks=True)
        copied.append(manifest.parent.name)
    return copied


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    print('Preserved management records:', ','.join(collect(args.source, args.run)))


if __name__ == '__main__':
    main()
