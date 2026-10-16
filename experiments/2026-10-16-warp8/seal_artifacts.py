"""Seal stopped warp8 artifacts only; no simulator, renderer, GPU or cloud calls."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import socket
import subprocess


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def index(root, tags=None):
    def selected(path):
        rel = path.relative_to(root)
        return (tags is None or rel.parts[0] in tags or
                (len(rel.parts) == 1 and any(path.name.startswith(tag + '.') for tag in tags)))
    return {str(p):dict(bytes=p.stat().st_size, sha256=sha(p))
            for p in sorted(root.rglob('*')) if p.is_file() and selected(p)}


def compress(path):
    size, digest = path.stat().st_size, sha(path)
    archive = path.with_name(path.name + '.zst')
    assert not archive.exists()
    subprocess.run(['zstd','-q','-3','-T1','-o',str(archive),str(path)], check=True)
    child = subprocess.Popen(['zstd','-qdc',str(archive)], stdout=subprocess.PIPE)
    hasher, decoded_bytes = hashlib.sha256(), 0
    while True:
        block = child.stdout.read(1024*1024)
        if not block:
            break
        hasher.update(block)
        decoded_bytes += len(block)
    child.stdout.close()
    assert child.wait() == 0 and hasher.hexdigest() == digest and decoded_bytes == size
    result = dict(original=str(path), decoded_bytes=size, decoded_sha256=digest,
        archive=str(archive), archive_bytes=archive.stat().st_size,
        archive_sha256=sha(archive), decoded_sha_verified=True)
    # Project-approved byte-exact compression, not evidence pruning.
    path.unlink()
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path('/home/ugrp/ugrp-sim/runs/warp8'))
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--tags', help='seal only these terminal attempts; preserve other cohorts')
    a = p.parse_args()
    assert socket.gethostname().split('.')[0] == 'ugrp-act-l4-gcp3'
    assert a.root.resolve() == Path('/home/ugrp/ugrp-sim/runs/warp8')
    assert a.out.resolve() != a.root.resolve() and a.root not in a.out.parents
    a.out.mkdir(parents=True, exist_ok=True)
    assert not any((a.out/name).exists() for name in
        ('compression-manifest.json','compression-manifest.json.zst')), 'already sealed; preserve the prior mapping'
    commands = sorted(a.root.glob('*.command.json'))
    tags = a.tags.split(',') if a.tags else None
    if tags is not None:
        assert len(tags) == len(set(tags)) and all(Path(tag).name == tag and tag not in ('.','..') for tag in tags)
        commands = [p for p in commands if p.name.removesuffix('.command.json') in tags]
        assert len(commands) == len(tags)
    assert commands
    receipts = []
    # Finish all assertions before any byte-exact replacement is attempted.
    for command in commands:
        name = command.name.removesuffix('.command.json')
        receipt = json.loads((a.root/(name+'.receipt.json')).read_text())
        assert isinstance(receipt['exit_code'], int) and receipt['end_utc']
        proc = Path('/proc')/str(receipt['pid'])/'cmdline'
        assert not proc.exists() or str(a.root/name).encode() not in proc.read_bytes().split(b'\0')
        receipts.append(dict(name=name, **receipt))
    before = index(a.root, tags)
    declared = dict(checked_N=0, missing=[], mismatch=[], finalizer_absent=[])
    for command in commands:
        name = command.name.removesuffix('.command.json')
        run = a.root/name
        manifest = run/'artifact-sha256.json'
        if not manifest.exists():
            declared['finalizer_absent'].append(name)
            continue
        for relative, item in json.loads(manifest.read_text()).items():
            actual = before.get(str(run/relative))
            if actual is None:
                declared['missing'].append(str(run/relative))
            elif actual != item:
                declared['mismatch'].append(str(run/relative))
            else:
                declared['checked_N'] += 1
    assert not declared['missing'] and not declared['mismatch'], declared
    def write(name, value):
        path = a.out/name
        path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
        return path
    before_file = write('raw-uncompressed-sha256.json', before)
    compressed = []
    # AGENTS.md disk rule: finished JSON/JSONL larger than64 KiB is compressed
    # losslessly, and every decoded byte is verified before replacing plaintext.
    for name in sorted(before):
        path = Path(name)
        if path.is_file() and path.suffix in ('.json','.jsonl') and path.stat().st_size > 65536:
            compressed.append(compress(path))
    after = index(a.root, tags)
    second = index(a.root, tags)
    assert after == second, 'artifact changed during sealing'
    after_file = write('raw-sha256.json', after)
    index_archives = [compress(path) for path in (before_file,after_file) if path.stat().st_size > 65536]
    compression_file = write('compression-manifest.json', dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        root=str(a.root), files=compressed, index_archives=index_archives))
    if compression_file.stat().st_size > 65536:
        write('compression-index-archive.json', compress(compression_file))
    verification = dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(), root=str(a.root),
        attempts=len(commands), selected_tags=tags, receipts=receipts, declared_manifest_verification=declared,
        before_file_N=len(before), before_bytes=sum(v['bytes'] for v in before.values()),
        after_file_N=len(after), after_bytes=sum(v['bytes'] for v in after.values()),
        all_current_file_hashes_recomputed_equal=True, compressed_N=len(compressed),
        decoded_SHA_verified_N=len(compressed), originals_preserved_as_lossless_archives=True,
        raw_location='gcp3 persistent disk; this is not an off-host full backup')
    write('integrity-verification.json', verification)
    print(json.dumps({k:v for k,v in verification.items() if k not in ('receipts','declared_manifest_verification')}))


if __name__ == '__main__':
    main()
