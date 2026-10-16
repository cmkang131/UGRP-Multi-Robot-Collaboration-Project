"""Seal this task's stopped artifacts; no simulator or GPU calls."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    assert a.root.resolve() == Path('/home/ugrp/ugrp-sim/runs/warp6')
    if (a.out/'compression-manifest.json').exists():
        raise FileExistsError('already sealed; preserve the original compression mapping')
    receipts = list(a.root.glob('*.receipt.json'))
    commands = list(a.root.glob('*.command.json'))
    assert len(receipts) == len(commands) == 8, 'all eight attempts must have terminal receipts'
    for command in commands:
        receipt = json.loads(command.with_name(command.name.replace('.command.', '.receipt.')).read_text())
        assert receipt['status'] in ('exited', 'HOST_ERROR')
        assert isinstance(receipt['exit_code'], int) and receipt['end_utc']
        proc = Path('/proc') / str(receipt['pid'])
        if proc.exists():
            cmdline = (proc / 'cmdline').read_bytes().replace(b'\0', b' ')
            assert b'run_warp_flow_teacher' not in cmdline, cmdline
    a.out.mkdir(parents=True, exist_ok=True)
    compressed = []
    # Project storage rule: lossless zstd for finished JSON/JSONL >64 KiB.
    # Read back every decoded byte before replacing our original with its archive.
    for path in sorted(a.root.rglob('*')):
        if not path.is_file() or path.suffix not in ('.json', '.jsonl') or path.stat().st_size <= 65536:
            continue
        size, digest = path.stat().st_size, sha(path)
        dest = path.with_name(path.name + '.zst')
        subprocess.run(['zstd', '-q', '-3', '-T1', '-o', str(dest), str(path)], check=True)
        decoded = subprocess.check_output(['zstd', '-d', '-c', str(dest)])
        assert len(decoded) == size and hashlib.sha256(decoded).hexdigest() == digest
        compressed.append(dict(original=str(path), decoded_bytes=size, decoded_sha256=digest,
            archive=str(dest), archive_bytes=dest.stat().st_size, archive_sha256=sha(dest),
            decoded_sha_verified=True))
        path.unlink()
    (a.out/'compression-manifest.json').write_text(json.dumps(dict(
        utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        root=str(a.root), replacement='lossless zstd, decompressed SHA256 verified', files=compressed), indent=2)+'\n')
    print(json.dumps(dict(compressed_N=len(compressed), raw_root=str(a.root))))


if __name__ == '__main__':
    main()
