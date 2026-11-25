"""Verify published Solo assets and assemble an isolated inference package."""
import hashlib
import json
import os
from pathlib import Path
import shutil
from zipfile import ZipFile

ROOT = Path(os.environ.get('UGRP_SOLO_ROOT', Path(__file__).resolve().parents[1]))
ASSETS = {
    'solo-pipeline-code.zip': '79cb2365880cbca73a80c53f39fbcbc9df570c920f2df79695e0cfb1d5406575',
    'solo-act-model-gseg-step4000.zip': '74b1213b07fcc3ec5cc286be3c44a310ebe2fea2d80ae2057c0b290977a4fea7',
}


def main():
    runtime = ROOT / 'runtime'
    runtime.mkdir(exist_ok=True)
    for name, digest in ASSETS.items():
        archive = ROOT / name
        if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Published asset checksum mismatch: {name}')
        with ZipFile(archive) as bundle:
            for entry in bundle.infolist():
                if entry.is_dir():
                    continue
                relative = Path(entry.filename)
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('Unsafe ZIP member')
                destination = runtime / relative
                data = bundle.read(entry)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists() and destination.read_bytes() != data:
                    raise ValueError(f'Existing source differs: {destination}')
                destination.write_bytes(data)
    package = runtime / 'solo_pipeline'
    (package / 'harness' / '__init__.py').write_text('', encoding='utf-8')
    for dependency in (Path(__file__).resolve().parents[1] / 'dependencies').glob('*.py'):
        shutil.copyfile(dependency, package / 'harness' / dependency.name)
    actor = runtime / 'actor'
    for name, digest in json.loads((actor / 'SHA256.json').read_bytes()).items():
        if hashlib.sha256((actor / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Actor file checksum mismatch: {name}')
    meta = json.loads((actor / 'adapter.json').read_bytes())
    if meta.get('image_frontend') != 'seg5_v1' or meta['provenance']['step'] != 4000:
        raise ValueError('Expected the published seg5_v1 step4000 model')
    contract = package / 'harness' / 'grasp_act_contract.py'
    if hashlib.sha256(contract.read_bytes()).hexdigest() != meta['contract_sha256']:
        raise ValueError('Model and source contract differ')
    print('Published Solo code, step4000 model and contract verified')


if __name__ == '__main__':
    main()
